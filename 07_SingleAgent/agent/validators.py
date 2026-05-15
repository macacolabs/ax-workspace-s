"""커리큘럼 구조 검증 — 규칙 기반."""
from __future__ import annotations

from dataclasses import dataclass, field

AX_GROUPS: dict[str, list[str]] = {
    "그룹A": ["균형형", "이해형"],
    "그룹B": ["과신형", "실행형"],
    "그룹C": ["판단형", "조심형"],
}
_HOUR_TOL = 0.5


@dataclass
class RuleResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ValidationResult:
    passed: bool
    rules: list[RuleResult] = field(default_factory=list)

    @property
    def failures(self) -> list[RuleResult]:
        return [r for r in self.rules if not r.passed]

    @property
    def summary(self) -> str:
        total = len(self.rules)
        ok = sum(1 for r in self.rules if r.passed)
        fail_msgs = "; ".join(r.detail for r in self.failures)
        return f"{ok}/{total} 규칙 통과" + (f" | 실패: {fail_msgs}" if fail_msgs else "")


class CurriculumValidator:
    def validate(self, req: dict, curriculum: dict) -> ValidationResult:
        rules: list[RuleResult] = []
        overview = curriculum.get("overview", {})

        days = req.get("days", overview.get("days", 0))
        hpd = req.get("hours_per_day", overview.get("hours_per_day", 0))
        expected_total = days * hpd

        ov_total = overview.get("total_hours", 0)
        ov_days = overview.get("days", 0)
        ov_hpd = overview.get("hours_per_day", 0)

        rules.append(RuleResult(
            "total_hours_match",
            abs(ov_total - expected_total) <= _HOUR_TOL,
            f"total_hours={ov_total} != {days}*{hpd}={expected_total}",
        ))
        rules.append(RuleResult(
            "days_match",
            ov_days == days,
            f"overview.days={ov_days} != input.days={days}",
        ))
        rules.append(RuleResult(
            "hours_per_day_match",
            abs(ov_hpd - hpd) <= _HOUR_TOL,
            f"overview.hours_per_day={ov_hpd} != input={hpd}",
        ))

        theory_sessions = curriculum.get("theory_sessions", [])
        practice_sessions = curriculum.get("practice_sessions", {})

        theory_hours = sum(s.get("duration_hours", 0) for s in theory_sessions)

        ax_counts: dict[str, int] = req.get("ax_counts", {})

        for grp, types in AX_GROUPS.items():
            grp_count = sum(ax_counts.get(t, 0) for t in types)
            grp_sessions = practice_sessions.get(grp, [])
            practice_hours = sum(s.get("duration_hours", 0) for s in grp_sessions)

            if grp_count > 0:
                rules.append(RuleResult(
                    f"group_present_{grp}",
                    len(grp_sessions) > 0,
                    f"{grp} count={grp_count}>0 이지만 practice_sessions에 없음",
                ))
                if grp_sessions:
                    rules.append(RuleResult(
                        f"hours_sum_{grp}",
                        abs(theory_hours + practice_hours - ov_total) <= _HOUR_TOL,
                        f"theory({theory_hours:.1f})+practice_{grp}({practice_hours:.1f})={theory_hours+practice_hours:.1f} != total({ov_total})",
                    ))
            else:
                rules.append(RuleResult(
                    f"group_absent_{grp}",
                    len(grp_sessions) == 0,
                    f"{grp} count=0 이지만 practice_sessions에 존재",
                ))

        if theory_sessions:
            orders = [s.get("order", 0) for s in theory_sessions]
            rules.append(RuleResult(
                "theory_order_monotonic",
                all(orders[i] < orders[i + 1] for i in range(len(orders) - 1)),
                f"이론 세션 order 단조증가 아님: {orders}",
            ))
            rules.append(RuleResult(
                "theory_duration_positive",
                all(s.get("duration_hours", 0) > 0 for s in theory_sessions),
                "이론 세션 중 duration_hours <= 0 존재",
            ))

        for grp, sessions in practice_sessions.items():
            if not sessions:
                continue
            orders = [s.get("order", 0) for s in sessions]
            rules.append(RuleResult(
                f"practice_order_{grp}",
                all(orders[i] < orders[i + 1] for i in range(len(orders) - 1)),
                f"{grp} 실습 세션 order 단조증가 아님: {orders}",
            ))
            rules.append(RuleResult(
                f"practice_duration_{grp}",
                all(s.get("duration_hours", 0) > 0 for s in sessions),
                f"{grp} 실습 세션 중 duration_hours <= 0 존재",
            ))

        passed = all(r.passed for r in rules)
        return ValidationResult(passed=passed, rules=rules)
