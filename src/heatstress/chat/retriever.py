"""
Dense retriever over HeatLens's own documents.

Uses model2vec (potion-base-8M, ~30 MB static weights, no GPU, no internet)
to embed project documentation so the agent can answer "why" and "how"
questions from the architecture/decisions/PRD documents.

Nothing — neither the query nor any document passage — leaves the machine.

INDEX BUILD:
  The index is built lazily on first call and held in memory.  For production
  use (or if startup latency matters), run scripts/09_build_chat_index.py to
  pre-build and cache the index to disk at data/processed/chat_index.pkl.

ADDING DOCUMENTS:
  Add paths to DOC_PATHS below.  The chunker respects heading boundaries and
  a max-char limit, so long files are split automatically.
"""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

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
    # Find heading positions.
    splits = [m.start() for m in _HEADING_RE.finditer(text)]
    if not splits:
        splits = [0]
    splits.append(len(text))

    passages: list[Passage] = []
    chunk_id = 0
    for i in range(len(splits) - 1):
        section = text[splits[i]:splits[i + 1]].strip()
        # Further split long sections.
        while len(section) > _MAX_CHUNK_CHARS:
            # Try to split at a paragraph boundary.
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
        # Trim very long values.
        if len(text) > _MAX_CHUNK_CHARS:
            text = text[:_MAX_CHUNK_CHARS] + "..."
        passages.append(Passage(text, source, i))
    return passages


def _load_passages(paths: list[Path]) -> list[Passage]:
    all_passages: list[Passage] = []
    for path in paths:
        if not path.exists():
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
# Index
# ---------------------------------------------------------------------------

@dataclass
class RetrievedPassage:
    text: str
    source: str
    score: float


class DenseRetriever:
    """In-memory dense retriever backed by model2vec embeddings.

    Initialise once; calling ``retrieve`` is fast (a dot product over the
    pre-computed passage embeddings).
    """

    def __init__(self, doc_paths: list[Path] | None = None):
        self._paths = doc_paths or DOC_PATHS
        self._model = None
        self._passages: list[Passage] = []
        self._embeddings = None   # numpy array, shape (n_passages, dim)
        self._ready = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> None:
        """Build (or rebuild) the index in memory."""
        try:
            from model2vec import StaticModel
            import numpy as np
        except ImportError:
            raise ImportError(
                "model2vec is not installed. Run: pip install model2vec"
            )

        self._model = StaticModel.from_pretrained("minishlab/potion-base-8M")
        self._passages = _load_passages(self._paths)

        if not self._passages:
            self._ready = False
            return

        texts = [p.text for p in self._passages]
        raw = self._model.encode(texts, show_progress_bar=False)

        import numpy as np
        emb = np.array(raw, dtype="float32")
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._embeddings = emb / norms
        self._ready = True

    def save(self, path: Path | None = None) -> None:
        """Save the built index to disk for fast startup."""
        if not self._ready:
            raise RuntimeError("Call build() first.")
        dest = path or _INDEX_PATH
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            pickle.dump(
                {"passages": self._passages, "embeddings": self._embeddings},
                fh,
                protocol=4,
            )

    def load(self, path: Path | None = None) -> bool:
        """Load a pre-built index from disk. Returns True on success."""
        try:
            from model2vec import StaticModel
        except ImportError:
            return False
        src = path or _INDEX_PATH
        if not src.exists():
            return False
        try:
            with open(src, "rb") as fh:
                data = pickle.load(fh)
            self._passages = data["passages"]
            self._embeddings = data["embeddings"]
            self._model = StaticModel.from_pretrained("minishlab/potion-base-8M")
            self._ready = True
            return True
        except Exception:
            return False

    def ensure_ready(self) -> None:
        """Build if not already ready (lazy init)."""
        if not self._ready:
            if not self.load():
                self.build()

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedPassage]:
        """Return the top-k passages most relevant to ``query``."""
        self.ensure_ready()
        if not self._ready or self._embeddings is None:
            return []

        import numpy as np

        q_emb = self._model.encode([query], show_progress_bar=False)
        q = np.array(q_emb[0], dtype="float32")
        norm = float(np.linalg.norm(q))
        if norm > 0:
            q = q / norm

        scores = self._embeddings @ q   # cosine similarity
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
