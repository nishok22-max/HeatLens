#!/usr/bin/env python
"""
scripts/09_build_chat_index.py — Phase 5G

Build the model2vec dense retrieval index over HeatLens's own documents
and save it to data/processed/chat_index.pkl.

Run this once after changing any document in docs/ or web/data/:

    .venv/bin/python scripts/09_build_chat_index.py

The agent rebuilds the index in memory if the pkl is missing, so this script
is optional but recommended for fast startup in production.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heatstress.chat.retriever import DenseRetriever

def main():
    print("Building chat index...")
    t0 = time.perf_counter()

    retriever = DenseRetriever()
    retriever.build()

    n = len(retriever._passages)
    print(f"  Indexed {n} passages in {time.perf_counter() - t0:.1f}s")

    retriever.save()
    print(f"  Saved to data/processed/chat_index.pkl")

    # Quick sanity check.
    results = retriever.retrieve("What is UTCI and why does it matter?", k=3)
    print("\nSanity check — top 3 passages for 'What is UTCI and why does it matter?':")
    for r in results:
        print(f"  [{r.source}] score={r.score:.3f}  {r.text[:80]}...")

    print("\nDone.")


if __name__ == "__main__":
    main()
