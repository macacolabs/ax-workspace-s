"""Retrieval evaluation: Precision@k and MRR.

Relevance is determined by keyword matching — each hit is "relevant" if its
text or section heading contains any of the expected `relevant_sections`
keywords supplied in the test case. This is a proxy for human relevance
judgments; replace with exact chunk-ID matching when annotated data exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HitDetail:
    rank: int
    chunk_id: str
    section: str
    text_preview: str       # first 120 chars
    retrieval: str          # "semantic" | "bm25" | "both"
    rrf_score: float
    rerank_score: float | None
    is_relevant: bool


@dataclass
class RetrievalResult:
    query: str
    k: int
    relevant_sections: list[str]
    hits: list[HitDetail]
    precision_at_k: float   # relevant_hits / k
    mrr: float              # 1 / rank_of_first_relevant  (0 if none)
    avg_rerank_score: float | None
    num_relevant: int


class RetrievalEvaluator:
    def __init__(self, indexer: Any) -> None:
        self._indexer = indexer

    def _is_relevant(self, hit: dict, keywords: list[str]) -> bool:
        haystack = (
            hit.get("text", "")
            + " "
            + hit.get("metadata", {}).get("section", "")
        ).lower()
        return any(kw.lower() in haystack for kw in keywords)

    def evaluate(
        self,
        query: str,
        relevant_sections: list[str],
        k: int = 6,
        doc_types: list[str] | None = None,
    ) -> RetrievalResult:
        raw_hits = self._indexer.query(query, doc_types=doc_types, k=k)

        hit_details: list[HitDetail] = []
        first_relevant_rank: int | None = None
        num_relevant = 0
        rerank_scores: list[float] = []

        for i, h in enumerate(raw_hits, start=1):
            relevant = self._is_relevant(h, relevant_sections)
            if relevant:
                num_relevant += 1
                if first_relevant_rank is None:
                    first_relevant_rank = i
            rs = h.get("rerank_score")
            if rs is not None:
                rerank_scores.append(float(rs))
            hit_details.append(HitDetail(
                rank=i,
                chunk_id=h.get("id", ""),
                section=h.get("metadata", {}).get("section", ""),
                text_preview=h.get("text", "")[:120],
                retrieval=h.get("retrieval", ""),
                rrf_score=float(h.get("rrf_score", 0.0)),
                rerank_score=float(rs) if rs is not None else None,
                is_relevant=relevant,
            ))

        precision = num_relevant / len(raw_hits) if raw_hits else 0.0
        mrr = (1.0 / first_relevant_rank) if first_relevant_rank else 0.0
        avg_rs = sum(rerank_scores) / len(rerank_scores) if rerank_scores else None

        return RetrievalResult(
            query=query,
            k=k,
            relevant_sections=relevant_sections,
            hits=hit_details,
            precision_at_k=precision,
            mrr=mrr,
            avg_rerank_score=avg_rs,
            num_relevant=num_relevant,
        )
