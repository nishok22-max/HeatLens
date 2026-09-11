"""
Dense retriever over HeatLens's own documents.

PRIMARY:  model2vec (potion-base-8M, ~30 MB static, no GPU, no inference
          server). Index builds in seconds; nothing leaves the machine.

FALLBACK: TF-IDF keyword retrieval implemented with only numpy (already
          installed). Activated automatically when model2vec is unavailable
          or when the HuggingFace download fails/times out. Provides good
          recall for factual queries over structured text.

The caller always gets a list[RetrievedPassage] regardless of which backend
is active, so the agent loop and the API are decoupled from this choice.

INDEX BUILD:
  Run scripts/09_build_chat_index.py to pre-build and save the dense index
  to data/processed/chat_index.pkl. If the file is missing, the retriever
  builds in memory on first call (dense if the model downloads successfully,
  TF-IDF otherwise).

ADDING DOCUMENTS:
  Add paths to DOC_PATHS below.
"""

from __future__ import annotations

import json
import logging
import math
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# retriever.py lives at: <root>/src/heatstress/chat/retriever.py
#   parents[0] = chat/, parents[1] = heatstress/, parents[2] = src/, parents[3] = root
_ROOT = Path(__file__).resolve().parents[3]
_DOCS_DIR = _ROOT / "docs"
_DATA_DIR = _ROOT / "web" / "data"
_INDEX_PATH = _ROOT / "data" / "processed" / "chat_index.pkl"

DOC_PATHS: list[Path] = [
    _DOCS_DIR / "ARCHITECTURE.md",
    _DOCS_DIR / "DECISIONS.md",
    _DOCS_DIR / "IMPLEMENTATION_PLAN.md",
    _DOCS_DIR / "PRD.md",
    _DATA_DIR / "meta.json",
    _DATA_DIR / "insights.json",
]

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_MAX_CHUNK_CHARS = 800
_HEADING_RE = re.compile(r"^#{1,3} .+", re.MULTILINE)


@dataclass
class Passage:
    text: str
    source: str   # filename
    chunk_id: int


def _chunk_markdown(text: str, source: str) -> list[Passage]:
    """Split a markdown document on headings, then by max char length."""
    splits = [m.start() for m in _HEADING_RE.finditer(text)]
    if not splits:
        splits = [0]
    splits.append(len(text))

    passages: list[Passage] = []
    chunk_id = 0
    for i in range(len(splits) - 1):
        section = text[splits[i]:splits[i + 1]].strip()
        while len(section) > _MAX_CHUNK_CHARS:
            cut = section.rfind("\n\n", 0, _MAX_CHUNK_CHARS)
            if cut == -1:
                cut = _MAX_CHUNK_CHARS
            passages.append(Passage(section[:cut].strip(), source, chunk_id))
            chunk_id += 1
            section = section[cut:].strip()
        if section:
            passages.append(Passage(section, source, chunk_id))
            chunk_id += 1

    return passages


def _chunk_json(obj: dict, source: str) -> list[Passage]:
    """Turn a JSON payload into passages by top-level key."""
    passages: list[Passage] = []
    for i, (key, value) in enumerate(obj.items()):
        text = f"{key}: {json.dumps(value, default=str)}"
        if len(text) > _MAX_CHUNK_CHARS:
            text = text[:_MAX_CHUNK_CHARS] + "..."
        passages.append(Passage(text, source, i))
    return passages


def _load_passages(paths: list[Path]) -> list[Passage]:
    all_passages: list[Passage] = []
    for path in paths:
        if not path.exists():
            log.debug("Retriever: skipping missing document %s", path)
            continue
        source = path.name
        raw = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            try:
                obj = json.loads(raw)
                all_passages.extend(_chunk_json(obj, source))
            except json.JSONDecodeError:
                all_passages.append(Passage(raw[:_MAX_CHUNK_CHARS], source, 0))
        else:
            all_passages.extend(_chunk_markdown(raw, source))
    return all_passages


# ---------------------------------------------------------------------------
# TF-IDF fallback (numpy only)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenise(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class TFIDFIndex:
    """Minimal TF-IDF retriever built on numpy and stdlib only.

    Good enough for keyword-heavy factual queries over structured text.
    Activated when model2vec cannot be loaded.
    """

    def __init__(self, passages: list[Passage]):
        import numpy as np
        self._passages = passages
        # Build vocabulary
        vocab: dict[str, int] = {}
        doc_tokens: list[list[str]] = []
        for p in passages:
            tokens = _tokenise(p.text)
            doc_tokens.append(tokens)
            for t in set(tokens):
                if t not in vocab:
                    vocab[t] = len(vocab)
        self._vocab = vocab
        n_docs = len(passages)
        n_terms = len(vocab)

        # TF matrix (sparse via lists of (doc, term, tf))
        matrix = np.zeros((n_docs, n_terms), dtype="float32")
        for d_idx, tokens in enumerate(doc_tokens):
            counts: dict[str, int] = {}
            for t in tokens:
                counts[t] = counts.get(t, 0) + 1
            total = len(tokens) or 1
            for t, cnt in counts.items():
                matrix[d_idx, vocab[t]] = cnt / total

        # IDF
        df = (matrix > 0).sum(axis=0) + 1   # +1 smoothing
        idf = np.log((n_docs + 1) / df)
        self._tfidf = matrix * idf   # (n_docs, n_terms)

        # L2-normalise rows
        norms = np.linalg.norm(self._tfidf, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._tfidf /= norms

    def query(self, text: str, k: int = 4) -> list[tuple[float, Passage]]:
        import numpy as np
        tokens = _tokenise(text)
        q = np.zeros(len(self._vocab), dtype="float32")
        for t in tokens:
            if t in self._vocab:
                q[self._vocab[t]] += 1.0
        norm = float(np.linalg.norm(q))
        if norm > 0:
            q /= norm
        scores = self._tfidf @ q
        top_k = min(k, len(self._passages))
        idx = scores.argsort()[::-1][:top_k]
        return [(float(scores[i]), self._passages[i]) for i in idx]


# ---------------------------------------------------------------------------
# Retrieved passage
# ---------------------------------------------------------------------------

@dataclass
class RetrievedPassage:
    text: str
    source: str
    score: float


# ---------------------------------------------------------------------------
# Main retriever class
# ---------------------------------------------------------------------------

class DenseRetriever:
    """Retriever with automatic dense→TF-IDF fallback.

    1. Tries to load model2vec (potion-base-8M) for dense retrieval.
    2. If model2vec is unavailable or the download fails, falls back to
       TF-IDF (numpy only, always available).

    The ``backend`` property tells you which is active after build().
    """

    def __init__(self, doc_paths: list[Path] | None = None):
        self._paths = doc_paths or DOC_PATHS
        self._model = None
        self._passages: list[Passage] = []
        self._embeddings = None      # numpy array — dense backend
        self._tfidf_index: TFIDFIndex | None = None   # fallback backend
        self._ready = False
        self._backend: str = "none"  # "dense" | "tfidf" | "none"

    @property
    def backend(self) -> str:
        return self._backend

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> None:
        """Build the index in memory, falling back to TF-IDF if needed."""
        self._passages = _load_passages(self._paths)
        if not self._passages:
            log.warning("Retriever: no passages loaded — check DOC_PATHS")
            return

        # Try dense first.
        if self._try_build_dense():
            return
        # Fall back to TF-IDF.
        self._build_tfidf()

    def _try_build_dense(self) -> bool:
        """Attempt to build the dense index. Returns True on success."""
        try:
            from model2vec import StaticModel
            import numpy as np

            log.info("Retriever: loading model2vec (potion-base-8M)…")
            self._model = StaticModel.from_pretrained("minishlab/potion-base-8M")

            texts = [p.text for p in self._passages]
            raw = self._model.encode(texts, show_progress_bar=False)
            emb = np.array(raw, dtype="float32")
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._embeddings = emb / norms
            self._backend = "dense"
            self._ready = True
            log.info("Retriever: dense index ready (%d passages)", len(self._passages))
            return True

        except Exception as exc:
            log.warning(
                "Retriever: model2vec unavailable (%s). "
                "Falling back to TF-IDF keyword retrieval.",
                exc,
            )
            return False

    def _build_tfidf(self) -> None:
        """Build TF-IDF index (numpy only, always succeeds)."""
        self._tfidf_index = TFIDFIndex(self._passages)
        self._backend = "tfidf"
        self._ready = True
        log.info(
            "Retriever: TF-IDF index ready (%d passages, %d terms)",
            len(self._passages),
            len(self._tfidf_index._vocab),
        )

    def save(self, path: Path | None = None) -> None:
        """Save the built index to disk for fast startup."""
        if not self._ready:
            raise RuntimeError("Call build() first.")
        dest = path or _INDEX_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload: dict = {
            "passages": self._passages,
            "backend": self._backend,
        }
        if self._backend == "dense":
            payload["embeddings"] = self._embeddings
        elif self._backend == "tfidf":
            payload["tfidf_index"] = self._tfidf_index
        with open(dest, "wb") as fh:
            pickle.dump(payload, fh, protocol=4)
        log.info("Retriever: index saved to %s (%s backend)", dest, self._backend)

    def load(self, path: Path | None = None) -> bool:
        """Load a pre-built index from disk. Returns True on success."""
        src = path or _INDEX_PATH
        if not src.exists():
            return False
        try:
            with open(src, "rb") as fh:
                data = pickle.load(fh)
            self._passages = data["passages"]
            self._backend = data.get("backend", "dense")

            if self._backend == "dense" and "embeddings" in data:
                # Also need to load the model for query encoding.
                try:
                    from model2vec import StaticModel
                    self._model = StaticModel.from_pretrained("minishlab/potion-base-8M")
                    self._embeddings = data["embeddings"]
                    self._ready = True
                    return True
                except Exception:
                    # Model unavailable — downgrade to TF-IDF.
                    log.warning("Retriever: model unavailable at load time, rebuilding TF-IDF")
                    self._build_tfidf()
                    return True

            elif self._backend == "tfidf" and "tfidf_index" in data:
                self._tfidf_index = data["tfidf_index"]
                self._ready = True
                return True

        except Exception as exc:
            log.warning("Retriever: failed to load index: %s", exc)
        return False

    def ensure_ready(self) -> None:
        """Build if not already ready (lazy init)."""
        if not self._ready:
            if not self.load():
                self.build()

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedPassage]:
        """Return the top-k passages most relevant to ``query``."""
        self.ensure_ready()
        if not self._ready:
            return []

        if self._backend == "dense" and self._embeddings is not None:
            return self._retrieve_dense(query, k)
        elif self._backend == "tfidf" and self._tfidf_index is not None:
            return self._retrieve_tfidf(query, k)
        return []

    def _retrieve_dense(self, query: str, k: int) -> list[RetrievedPassage]:
        import numpy as np
        q_emb = self._model.encode([query], show_progress_bar=False)
        q = np.array(q_emb[0], dtype="float32")
        norm = float(np.linalg.norm(q))
        if norm > 0:
            q /= norm
        scores = self._embeddings @ q
        top_k = int(min(k, len(self._passages)))
        idx = scores.argsort()[::-1][:top_k]
        return [
            RetrievedPassage(
                text=self._passages[i].text,
                source=self._passages[i].source,
                score=float(scores[i]),
            )
            for i in idx
        ]

    def _retrieve_tfidf(self, query: str, k: int) -> list[RetrievedPassage]:
        results = self._tfidf_index.query(query, k=k)
        return [
            RetrievedPassage(text=p.text, source=p.source, score=score)
            for score, p in results
        ]


# ---------------------------------------------------------------------------
# Module-level singleton (lazy)
# ---------------------------------------------------------------------------

_RETRIEVER: DenseRetriever | None = None


def get_retriever() -> DenseRetriever:
    """Return the shared module-level retriever, building it on first call."""
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = DenseRetriever()
    return _RETRIEVER
