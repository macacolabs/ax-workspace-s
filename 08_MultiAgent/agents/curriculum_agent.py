"""CurriculumGeneratorAgent — 요구사항 + RAG 컨텍스트로 커리큘럼 JSON 생성."""
from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent, load_prompt


class CurriculumGeneratorAgent(BaseAgent):
    name = "CurriculumGeneratorAgent"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        super().__init__(api_key, model)
        self._system_prompt = load_prompt("curriculum_agent.txt")

    def generate(
        self,
        requirements: dict[str, Any],
        rag_context: str = "",
        failure_feedback: str = "",
    ) -> dict[str, Any]:
        ax_counts: dict[str, int] = requirements.get("ax_counts", {})
        grp_a = ax_counts.get("균형형", 0) + ax_counts.get("이해형", 0)
        grp_b = ax_counts.get("과신형", 0) + ax_counts.get("실행형", 0)
        grp_c = ax_counts.get("판단형", 0) + ax_counts.get("조심형", 0)

        ax_lines = "\n".join(f"  - {t}: {n}명" for t, n in ax_counts.items())
        user_content = f"""요구사항:
회사명: {requirements.get('company', '')}
교육 대상자: {requirements.get('audience', '')}
AI 경험 수준: {requirements.get('ai_experience', '')}
제약 조건: {requirements.get('constraints', '')}
교육 목표: {requirements.get('goal', '')}
교육 일수: {requirements.get('days', 1)}일
일 교육 시간: {requirements.get('hours_per_day', 8)}시간
총 교육 시간: {int(requirements.get('days', 1)) * float(requirements.get('hours_per_day', 8))}시간

AX Compass 유형별 인원:
{ax_lines}

그룹 구성:
- 그룹A (균형형+이해형): {grp_a}명{"" if grp_a > 0 else " → practice_sessions 제외"}
- 그룹B (과신형+실행형): {grp_b}명{"" if grp_b > 0 else " → practice_sessions 제외"}
- 그룹C (판단형+조심형): {grp_c}명{"" if grp_c > 0 else " → practice_sessions 제외"}
"""
        if rag_context:
            user_content += f"\n\nAX Compass 참조 자료:\n{rag_context}"

        if failure_feedback:
            user_content += f"\n\n⚠ 이전 검증 실패 항목 (반드시 수정):\n{failure_feedback}"

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        raw = self._chat(messages, response_format={"type": "json_object"}, temperature=0.7)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
            raise ValueError(f"커리큘럼 JSON 파싱 실패: {raw[:200]}")
