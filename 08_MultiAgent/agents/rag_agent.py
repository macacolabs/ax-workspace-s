"""RAGAgent — AX Compass 자료 검색 전문 에이전트."""
from __future__ import annotations

import sys
from pathlib import Path

_WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_WORKSPACE / "05_Advanced_RAG_indexing_contextual"))
from indexing_pipeline import AdvancedRAGIndexer

from .base import BaseAgent


class RAGAgent(BaseAgent):
    name = "RAGAgent"

    def __init__(
        self,
        api_key: str,
        chroma_dir: Path,
        data_dir: Path,
        model: str = "gpt-4o-mini",
    ) -> None:
        super().__init__(api_key, model)
        self._indexer = AdvancedRAGIndexer(
            api_key=api_key,
            chroma_dir=chroma_dir,
            data_dir=data_dir,
            rerank=True,
        )

    def search(self, query: str, k: int = 6) -> list[dict]:
        try:
            return self._indexer.query(query, k=k)
        except Exception as e:
            return [{"text": f"검색 오류: {e}", "metadata": {}, "id": "error"}]

    def search_multi(self, queries: list[str], k: int = 6) -> list[dict]:
        """여러 쿼리로 검색 후 중복 제거."""
        seen: set[str] = set()
        results: list[dict] = []
        for q in queries:
            for chunk in self.search(q, k=k):
                cid = chunk.get("id", "")
                if cid and cid not in seen:
                    seen.add(cid)
                    results.append(chunk)
                elif not cid:
                    results.append(chunk)
        return results

    def build_context(self, chunks: list[dict], max_chars: int = 4000) -> str:
        parts: list[str] = []
        total = 0
        for i, c in enumerate(chunks, 1):
            meta = c.get("metadata", {})
            heading = meta.get("heading", "")
            src = meta.get("source", "")
            score = c.get("rerank_score") or c.get("rrf_score") or 0
            header = f"[{i}] {src}" + (f" / {heading}" if heading else "") + f" (score={score:.3f})"
            body = c.get("text", "")
            block = f"{header}\n{body}"
            if total + len(block) > max_chars:
                break
            parts.append(block)
            total += len(block)
        return "\n\n".join(parts)
