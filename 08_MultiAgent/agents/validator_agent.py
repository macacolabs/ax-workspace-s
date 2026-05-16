"""ValidatorAgent — 코드 검증(규칙) + LLM 판단(의미) 2단계 검증."""
from __future__ import annotations

import json
from typing import Any

from .base import BaseAgent, load_prompt
from evaluation.schema import (
    CheckStatus,
    CodeCheck,
    CodeValidationResult,
    LLMCheck,
    LLMValidationResult,
    ValidationReport,
)

_AX_GROUPS: dict[str, list[str]] = {
    "그룹A": ["균형형", "이해형"],
    "그룹B": ["과신형", "실행형"],
    "그룹C": ["판단형", "조심형"],
}
_HOUR_TOL = 0.5
_LLM_THRESHOLD = 0.6


class ValidatorAgent(BaseAgent):
    name = "ValidatorAgent"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        super().__init__(api_key, model)
        self._system_prompt = load_prompt("validator_agent.txt")

    # ── 공개 인터페이스 ────────────────────────────────────────────────────────

    def validate(
        self,
        curriculum: dict[str, Any],
        requirements: dict[str, Any],
        rag_chunks: list[dict],
        attempt: int = 1,
    ) -> ValidationReport:
        code_result = self._run_code_checks(curriculum, requirements)
        llm_result = self._run_llm_checks(curriculum, requirements, rag_chunks)
        return ValidationReport(code=code_result, llm=llm_result, attempt=attempt)

    # ── 코드 검증 (결정적) ────────────────────────────────────────────────────

    def _run_code_checks(
        self, curriculum: dict[str, Any], requirements: dict[str, Any]
    ) -> CodeValidationResult:
        checks: list[CodeCheck] = []
        overview = curriculum.get("overview", {})

        days = int(requirements.get("days", overview.get("days", 0)))
        hpd = float(requirements.get("hours_per_day", overview.get("hours_per_day", 0)))
        expected_total = days * hpd

        ov_total = float(overview.get("total_hours", 0))
        ov_days = int(overview.get("days", 0))
        ov_hpd = float(overview.get("hours_per_day", 0))

        checks.append(CodeCheck(
            "total_hours_match",
            CheckStatus.PASS if abs(ov_total - expected_total) <= _HOUR_TOL else CheckStatus.FAIL,
            f"total_hours={ov_total} vs 기대값={expected_total}",
            expected=expected_total, actual=ov_total,
        ))
        checks.append(CodeCheck(
            "days_match",
            CheckStatus.PASS if ov_days == days else CheckStatus.FAIL,
            f"overview.days={ov_days} vs input.days={days}",
            expected=days, actual=ov_days,
        ))
        checks.append(CodeCheck(
            "hours_per_day_match",
            CheckStatus.PASS if abs(ov_hpd - hpd) <= _HOUR_TOL else CheckStatus.FAIL,
            f"overview.hours_per_day={ov_hpd} vs input={hpd}",
            expected=hpd, actual=ov_hpd,
        ))

        theory_sessions = curriculum.get("theory_sessions", [])
        practice_sessions = curriculum.get("practice_sessions", {})
        theory_hours = sum(s.get("duration_hours", 0) for s in theory_sessions)
        ax_counts: dict[str, int] = requirements.get("ax_counts", {})

        for grp, types in _AX_GROUPS.items():
            grp_count = sum(ax_counts.get(t, 0) for t in types)
            grp_sessions = practice_sessions.get(grp, [])
            practice_hours = sum(s.get("duration_hours", 0) for s in grp_sessions)

            if grp_count > 0:
                checks.append(CodeCheck(
                    f"group_present_{grp}",
                    CheckStatus.PASS if len(grp_sessions) > 0 else CheckStatus.FAIL,
                    f"{grp} count={grp_count}>0이지만 세션 없음",
                    expected=">0 sessions", actual=len(grp_sessions),
                ))
                if grp_sessions:
                    total_check = abs(theory_hours + practice_hours - ov_total) <= _HOUR_TOL
                    checks.append(CodeCheck(
                        f"hours_sum_{grp}",
                        CheckStatus.PASS if total_check else CheckStatus.FAIL,
                        f"이론({theory_hours:.1f}h)+실습_{grp}({practice_hours:.1f}h)={theory_hours+practice_hours:.1f}h vs total={ov_total}h",
                        expected=ov_total, actual=round(theory_hours + practice_hours, 1),
                    ))
            else:
                checks.append(CodeCheck(
                    f"group_absent_{grp}",
                    CheckStatus.PASS if len(grp_sessions) == 0 else CheckStatus.FAIL,
                    f"{grp} count=0인데 세션 {len(grp_sessions)}개 존재",
                    expected=0, actual=len(grp_sessions),
                ))

        if theory_sessions:
            orders = [s.get("order", 0) for s in theory_sessions]
            monotonic = all(orders[i] < orders[i + 1] for i in range(len(orders) - 1))
            checks.append(CodeCheck(
                "theory_order_monotonic",
                CheckStatus.PASS if monotonic else CheckStatus.WARN,
                f"이론 세션 order={orders}",
            ))
            checks.append(CodeCheck(
                "theory_duration_positive",
                CheckStatus.PASS if all(s.get("duration_hours", 0) > 0 for s in theory_sessions) else CheckStatus.FAIL,
                "이론 세션 중 duration_hours<=0 존재",
            ))

        for grp, sessions in practice_sessions.items():
            if not sessions:
                continue
            orders = [s.get("order", 0) for s in sessions]
            if len(orders) > 1:
                monotonic = all(orders[i] < orders[i + 1] for i in range(len(orders) - 1))
                checks.append(CodeCheck(
                    f"practice_order_{grp}",
                    CheckStatus.PASS if monotonic else CheckStatus.WARN,
                    f"{grp} 실습 order={orders}",
                ))
            checks.append(CodeCheck(
                f"practice_duration_{grp}",
                CheckStatus.PASS if all(s.get("duration_hours", 0) > 0 for s in sessions) else CheckStatus.FAIL,
                f"{grp} 실습 세션 중 duration_hours<=0 존재",
            ))

        return CodeValidationResult(checks=checks)

    # ── LLM 판단 (의미 기반) ──────────────────────────────────────────────────

    def _run_llm_checks(
        self,
        curriculum: dict[str, Any],
        requirements: dict[str, Any],
        rag_chunks: list[dict],
    ) -> LLMValidationResult:
        rag_text = "\n\n".join(c.get("text", "")[:300] for c in rag_chunks[:5]) if rag_chunks else "참조 자료 없음"

        user_content = f"""커리큘럼을 평가하세요.

요구사항:
- 교육 목표: {requirements.get('goal', '')}
- 교육 대상자: {requirements.get('audience', '')}
- AI 경험: {requirements.get('ai_experience', '')}
- 제약 조건: {requirements.get('constraints', '')}

커리큘럼 개요:
{json.dumps(curriculum.get('overview', {}), ensure_ascii=False, indent=2)}

이론 세션:
{json.dumps([{"title": s.get("title"), "objective": s.get("objective")} for s in curriculum.get("theory_sessions", [])], ensure_ascii=False, indent=2)}

실습 세션:
{json.dumps({g: [{"title": s.get("title"), "rationale": s.get("ax_type_rationale")} for s in ss] for g, ss in curriculum.get("practice_sessions", {}).items() if ss}, ensure_ascii=False, indent=2)}

기대 성과: {json.dumps(curriculum.get('expected_outcomes', []), ensure_ascii=False)}

AX Compass 참조 자료 (일부):
{rag_text[:1500]}
"""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        raw = self._chat(messages, response_format={"type": "json_object"}, temperature=0.3)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return LLMValidationResult(raw_response=raw)

        checks: list[LLMCheck] = []
        for field_name in ("goal_alignment", "audience_appropriateness", "constraint_compliance", "faithfulness"):
            item = data.get(field_name, {})
            score = float(item.get("score", 0.0))
            reason = item.get("reason", "")
            extra = {}
            if field_name == "faithfulness":
                extra["ungrounded_claims"] = item.get("ungrounded_claims", [])
            checks.append(LLMCheck(
                name=field_name,
                score=score,
                reason=reason,
                threshold=_LLM_THRESHOLD,
                extra=extra,
            ))

        return LLMValidationResult(checks=checks, raw_response=raw)
