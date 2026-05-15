"""Agent 도구 정의 — RAG, 웹검색, 커리큘럼 생성, 검증."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openai import OpenAI

_WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_WORKSPACE / "05_Advanced_RAG_indexing_contextual"))
from indexing_pipeline import AdvancedRAGIndexer

from .validators import CurriculumValidator

CURRICULUM_SYSTEM_PROMPT = """당신은 20년 경력의 IT·AI 강사이자 교육 스타트업 대표입니다.

다음 JSON 스키마로만 응답하세요. 다른 텍스트 없이 JSON만 출력합니다.

{
  "overview": {
    "company": "string", "department": "string", "audience": "string",
    "topics": ["string"], "total_hours": number, "days": number,
    "hours_per_day": number, "difficulty": "입문|초급|중급|고급",
    "ax_compass_distribution": {
      "그룹A": {"types": ["균형형","이해형"], "count": number},
      "그룹B": {"types": ["과신형","실행형"], "count": number},
      "그룹C": {"types": ["판단형","조심형"], "count": number}
    }
  },
  "theory_sessions": [
    {"order": number, "title": "string", "duration_hours": number,
     "objective": "string", "activities": ["string"], "key_concepts": ["string"]}
  ],
  "practice_sessions": {
    "그룹A": [{"order": number, "title": "string", "duration_hours": number,
               "objective": "string", "activities": ["string"], "ax_type_rationale": "string"}],
    "그룹B": [], "그룹C": []
  },
  "expected_outcomes": ["string"],
  "prerequisites": ["string"]
}

시간 제약 규칙:
- theory_sessions 합 + practice_sessions 단일 그룹 합 = total_hours
- 그룹별 실습 시간 합은 동일 (동시 진행)
- 0명 그룹은 practice_sessions에서 완전 제외
- 이론 40~50%, 실습 50~60% 권장
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "AX Compass PDF에서 관련 청크를 검색합니다. AX 유형별 특성, 교육 전략, 그룹 구성 방법 등을 조회할 때 사용하세요.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리 텍스트"},
                    "k": {"type": "integer", "description": "반환할 결과 수 (기본 6)", "default": 6},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "최신 AI 트렌드, 기업 정보, 특정 도구 사용법을 웹에서 검색합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "max_results": {"type": "integer", "description": "최대 결과 수 (기본 3)", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_curriculum",
            "description": "수집된 요구사항으로 AX Compass 기반 교육 커리큘럼 JSON을 생성합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "audience": {"type": "string"},
                    "ai_experience": {"type": "string"},
                    "constraints": {"type": "string"},
                    "goal": {"type": "string"},
                    "days": {"type": "integer"},
                    "hours_per_day": {"type": "number"},
                    "ax_counts": {
                        "type": "object",
                        "description": '{"균형형": N, "이해형": N, "과신형": N, "실행형": N, "판단형": N, "조심형": N}',
                    },
                    "rag_context": {"type": "string", "description": "RAG 검색으로 얻은 참조 텍스트"},
                },
                "required": ["company", "audience", "goal", "days", "hours_per_day", "ax_counts"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_curriculum",
            "description": "생성된 커리큘럼의 시간 합계, 그룹 구성, 세션 순서 등 구조 규칙을 검증합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "curriculum": {"type": "object", "description": "검증할 커리큘럼 JSON"},
                    "requirements": {
                        "type": "object",
                        "description": "원래 요구사항 (days, hours_per_day, ax_counts 포함)",
                    },
                },
                "required": ["curriculum", "requirements"],
            },
        },
    },
]


class RAGTool:
    def __init__(self, indexer: AdvancedRAGIndexer) -> None:
        self._indexer = indexer

    def search(self, query: str, k: int = 6) -> str:
        try:
            results = self._indexer.query(query, k=k)
        except Exception as e:
            return f"RAG 검색 오류: {e}"
        if not results:
            return "관련 문서를 찾지 못했습니다."
        parts: list[str] = []
        for i, r in enumerate(results, 1):
            meta = r.get("metadata", {})
            src = meta.get("source", "unknown")
            heading = meta.get("heading", "")
            score = r.get("rerank_score") or r.get("rrf_score") or r.get("distance", 0)
            header = f"[{i}] {src}" + (f" / {heading}" if heading else "") + f" (score={score:.3f})"
            parts.append(f"{header}\n{r['text']}")
        return "\n\n".join(parts)


class WebSearchTool:
    def __init__(self, tavily_api_key: str) -> None:
        self._key = tavily_api_key

    def search(self, query: str, max_results: int = 3) -> str:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self._key)
            resp = client.search(query, max_results=max_results)
            results = resp.get("results", [])
            if not results:
                return "검색 결과 없음"
            parts = []
            for r in results:
                parts.append(f"제목: {r.get('title','')}\nURL: {r.get('url','')}\n{r.get('content','')[:400]}")
            return "\n\n---\n\n".join(parts)
        except ImportError:
            return "tavily 패키지가 설치되지 않았습니다. pip install tavily-python"
        except Exception as e:
            return f"웹 검색 오류: {e}"


class CurriculumGeneratorTool:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def generate(
        self,
        company: str,
        audience: str,
        goal: str,
        days: int,
        hours_per_day: float,
        ax_counts: dict[str, int],
        ai_experience: str = "",
        constraints: str = "",
        rag_context: str = "",
    ) -> dict[str, Any]:
        user_content = f"""
회사명: {company}
교육 대상자: {audience}
AI 경험: {ai_experience}
제약 조건: {constraints}
교육 목표: {goal}
교육 일수: {days}일
일 교육 시간: {hours_per_day}시간
총 교육 시간: {days * hours_per_day}시간

AX Compass 유형별 인원:
{json.dumps(ax_counts, ensure_ascii=False, indent=2)}

그룹 구성:
- 그룹A (균형형+이해형): {ax_counts.get('균형형',0)+ax_counts.get('이해형',0)}명
- 그룹B (과신형+실행형): {ax_counts.get('과신형',0)+ax_counts.get('실행형',0)}명
- 그룹C (판단형+조심형): {ax_counts.get('판단형',0)+ax_counts.get('조심형',0)}명
"""
        if rag_context:
            user_content += f"\n\n참조 자료 (AX Compass):\n{rag_context[:3000]}"

        resp = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CURRICULUM_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )
        raw = resp.choices[0].message.content or "{}"
        return json.loads(raw)


class ValidatorTool:
    def __init__(self) -> None:
        self._validator = CurriculumValidator()

    def validate(self, curriculum: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
        result = self._validator.validate(requirements, curriculum)
        return {
            "passed": result.passed,
            "summary": result.summary,
            "failures": [
                {"rule": r.name, "detail": r.detail}
                for r in result.failures
            ],
            "all_rules": [
                {"rule": r.name, "passed": r.passed, "detail": r.detail}
                for r in result.rules
            ],
        }
