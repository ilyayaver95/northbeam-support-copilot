"""retrieval.py — hybrid search over the policy corpus.

Three things it does that a plain top-k cosine search does not:

  Heading-aware chunking. Policy docs are tables and short sections; splitting on
  a fixed character count cuts a threshold away from the band it belongs to.
  Sections are split at headings first, then windowed with overlap only if a
  section is genuinely long, and every window keeps its heading as a prefix.

  Hybrid scoring. BM25 catches the literal terms that matter here — fault codes,
  `sla_response_due`, "advance replacement" — while the embedding catches the
  paraphrase, since a support agent asks "how long till they have to answer",
  not "what is the response target". Either alone loses one of those.

  Adaptive document count. A question about one fee should return one document;
  a question spanning service levels and fault handling should return both.
  The count follows the score spread rather than a hardcoded k.

Returns whole documents (assembled from their best-scoring chunks) rather than
raw chunks, because the answer has to cite a document id.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

POLICIES_DIR = Path(__file__).resolve().parents[1] / "data" / "policies"

CHUNK_CHARS = 700
CHUNK_OVERLAP = 120

# Weight on the semantic score; the remainder goes to BM25. An even split beat
# both extremes on the policy corpus — the docs are dense with literal terms but
# the questions almost never use them.
ALPHA = 0.5
BM25_K1 = 1.5
BM25_B = 0.75

# Keep documents scoring at least this fraction of the top document. Loose on
# purpose: under-retrieving costs more on multi-document questions than a little
# extra context costs elsewhere.
RELATIVE_FLOOR = 0.45
MIN_DOCS = 2
MAX_DOCS = 5

_TOKEN = re.compile(r"[a-z0-9]+")

_embedder: SentenceTransformer | None = None
_chunks: list[dict] | None = None
_stats: dict | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _split_sections(text: str) -> list[str]:
    """Split a markdown document at heading lines."""
    sections: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [s for s in sections if s]


def _window(section: str, heading: str) -> list[str]:
    """Break a long section into overlapping windows, each keeping its heading."""
    if len(section) <= CHUNK_CHARS:
        return [section]
    out, start = [], 0
    while start < len(section):
        piece = section[start:start + CHUNK_CHARS]
        out.append(piece if piece.startswith(heading) else f"{heading}\n{piece}")
        start += CHUNK_CHARS - CHUNK_OVERLAP
    return out


def _build_index() -> None:
    global _chunks, _stats

    chunks: list[dict] = []
    for path in sorted(POLICIES_DIR.glob("*.md")):
        text = path.read_text()
        for section in _split_sections(text):
            heading = section.splitlines()[0] if section else ""
            for piece in _window(section, heading):
                chunks.append({"doc_id": path.name, "text": piece,
                               "tokens": _tokenize(piece)})

    embeddings = _get_embedder().encode([c["text"] for c in chunks],
                                        normalize_embeddings=True)
    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = np.asarray(embedding, dtype=np.float32)

    document_frequency: dict[str, int] = {}
    for chunk in chunks:
        for token in set(chunk["tokens"]):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    _chunks = chunks
    _stats = {
        "df": document_frequency,
        "avgdl": sum(len(c["tokens"]) for c in chunks) / max(1, len(chunks)),
        "n": len(chunks),
    }


def _bm25(query_tokens: list[str], chunk: dict) -> float:
    df, avgdl, n = _stats["df"], _stats["avgdl"], _stats["n"]
    length = len(chunk["tokens"])

    frequencies: dict[str, int] = {}
    for token in chunk["tokens"]:
        frequencies[token] = frequencies.get(token, 0) + 1

    score = 0.0
    for token in query_tokens:
        if token not in frequencies:
            continue
        seen = df.get(token, 0)
        idf = math.log(1 + (n - seen + 0.5) / (seen + 0.5))
        tf = frequencies[token]
        denominator = tf + BM25_K1 * (1 - BM25_B + BM25_B * length / avgdl)
        score += idf * (tf * (BM25_K1 + 1)) / denominator
    return score


def _normalize(values: np.ndarray) -> np.ndarray:
    low, high = float(values.min()), float(values.max())
    if high - low < 1e-9:
        return np.zeros_like(values)
    return (values - low) / (high - low)


def search_policies(query: str, top_k: int | None = None) -> list[dict]:
    """Hybrid keyword + semantic search over the policy documents.

    Use for anything about service levels, response targets, availability bands,
    fault severity, escalation, calibration, maintenance windows, firmware,
    spare parts, RMAs, warranty, onboarding, commissioning, the portal API, or
    what Northbeam does and does not store.

    Args:
        query: what you need to know, in plain language, e.g.
               "how long does a critical fault have for a response".
        top_k: optional lower bound on documents returned. Left alone, the count
               adapts to how tightly the scores cluster.

    Returns:
        A list of {"doc_id", "score", "body"}, most relevant first. Cite the
        doc_id of anything you rely on.
    """
    if _chunks is None:
        _build_index()

    query_tokens = _tokenize(query)
    query_embedding = np.asarray(
        _get_embedder().encode(query, normalize_embeddings=True), dtype=np.float32)

    keyword = np.array([_bm25(query_tokens, c) for c in _chunks], dtype=np.float32)
    semantic = np.array([float(np.dot(query_embedding, c["embedding"]))
                         for c in _chunks], dtype=np.float32)
    blended = ALPHA * _normalize(semantic) + (1 - ALPHA) * _normalize(keyword)

    best_score: dict[str, float] = {}
    per_document: dict[str, list[tuple[float, str]]] = {}
    for chunk, score in zip(_chunks, blended):
        score = float(score)
        per_document.setdefault(chunk["doc_id"], []).append((score, chunk["text"]))
        if score > best_score.get(chunk["doc_id"], -1.0):
            best_score[chunk["doc_id"]] = score

    ranked = sorted(best_score.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return []

    top = ranked[0][1]
    count = sum(1 for _, s in ranked if s >= RELATIVE_FLOOR * top)
    count = max(MIN_DOCS, min(count, MAX_DOCS))
    if top_k:
        count = max(count, min(int(top_k), MAX_DOCS))
    count = min(count, len(ranked))

    results = []
    for doc_id, score in ranked[:count]:
        best_chunks = sorted(per_document[doc_id], reverse=True)[:2]
        results.append({
            "doc_id": doc_id,
            "score": round(score, 4),
            "body": "\n\n".join(text for _, text in best_chunks),
        })
    return results
