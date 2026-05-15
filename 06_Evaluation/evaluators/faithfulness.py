"""Faithfulness evaluation: generated curriculum grounded in retrieved context.

Checks whether AX Compass type descriptions and rationale in the curriculum
are supported by the retrieved document chunks, not hallucinated.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

_PROMPT = """\
아래는 AX Compass 문서에서 검색된 근거 텍스트와 AI가 생성한 커리큘럼입니다.

[근거 텍스트]
{context}

[생성된 커리큘럼 (JSON)]
{curriculum}

평가 기준:
1. 커리큘럼에서 AX Compass 유형(균형형·이해형·과신형·실행형·판단형·조심형)을 언급할 때
   해당 설명이 근거 텍스트에 기반한 내용인지 확인하세요.
2. 근거 없이 만들어낸 AX 유형 설명이나 특성이 있으면 감점하세요.
3. 커리큘럼 일정·시간 배분·그룹 구성 등 형식적 항목은 평가하지 마세요.

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "score": 0~100,
  "grounded_claims": ["근거 있는 AX 언급 예시 (최대 3개)"],
  "ungrounded_claims": ["근거 없는 AX 언급 예시 (최대 3개)"],
  "reason": "한 줄 평가 이유"
}}"""


@dataclass
class FaithfulnessResult:
    score: float                    # 0-1
    grounded_claims: list[str]
    ungrounded_claims: list[str]
    reason: str
    context_chunks_used: int
    error: str | None = None


class FaithfulnessEvaluator:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self.available = False
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            self.available = True
        except Exception:
            pass

    def evaluate(self, curriculum: dict, hits: list[dict]) -> FaithfulnessResult:
        if not self.available:
            return FaithfulnessResult(
                score=0.0, grounded_claims=[], ungrounded_claims=[],
                reason="OpenAI unavailable", context_chunks_used=0,
                error="openai not installed",
            )

        top_hits = hits[:8]
        context_parts = []
        for i, h in enumerate(top_hits, start=1):
            section = h.get("metadata", {}).get("section", "")
            text = h.get("text", "")[:400]
            context_parts.append(f"[청크{i}] {section}\n{text}")
        context = "\n\n".join(context_parts)

        # Only pass AX-relevant fields to keep the prompt concise
        curriculum_subset = {
            "overview": curriculum.get("overview", {}),
            "practice_sessions_rationale": {
                grp: [
                    {
                        "title": s.get("title"),
                        "ax_type_rationale": s.get("ax_type_rationale"),
                    }
                    for s in sessions
                ]
                for grp, sessions in curriculum.get("practice_sessions", {}).items()
            },
        }

        prompt = _PROMPT.format(
            context=context,
            curriculum=json.dumps(curriculum_subset, ensure_ascii=False, indent=2),
        )

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            return FaithfulnessResult(
                score=float(data.get("score", 0)) / 100.0,
                grounded_claims=data.get("grounded_claims", []),
                ungrounded_claims=data.get("ungrounded_claims", []),
                reason=data.get("reason", ""),
                context_chunks_used=len(top_hits),
            )
        except Exception as e:
            return FaithfulnessResult(
                score=0.0, grounded_claims=[], ungrounded_claims=[],
                reason="", context_chunks_used=len(top_hits), error=str(e),
            )
