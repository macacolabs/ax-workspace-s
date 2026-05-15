"""Rule-based evaluation: structural correctness of generated curricula.

All checks are pure Python — no LLM calls. Validates:
- Hour/day consistency
- Group presence vs. AX Compass head-count
- Session order monotonicity
- Duration positivity
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_AX_GROUPS: dict[str, list[str]] = {
    "그룹A": ["균형형", "이해형"],
    "그룹B": ["과신형", "실행형"],
    "그룹C": ["판단형", "조심형"],
}
_HOUR_TOLERANCE = 0.5   # allow ±30 min rounding


@dataclass
class RuleCheckResult:
    name: str
    passed: bool
    message: str
    expected: Any = None
    actual: Any = None


@dataclass
class RuleBasedResult:
    checks: list[RuleCheckResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        return sum(1 for c in self.checks if c.passed) / len(self.checks) if self.checks else 1.0

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def total_count(self) -> int:
        return len(self.checks)


class RuleBasedEvaluator:
    def evaluate(self, requirements: dict, curriculum: dict) -> RuleBasedResult:
        checks: list[RuleCheckResult] = []
        checks.extend(self._check_time_consistency(requirements, curriculum))
        checks.extend(self._check_group_consistency(requirements, curriculum))
        checks.extend(self._check_session_order(curriculum))
        checks.extend(self._check_duration_validity(curriculum))
        return RuleBasedResult(checks=checks)

    # ── Time consistency ──────────────────────────────────────────────────────

    def _check_time_consistency(
        self, req: dict, cur: dict
    ) -> list[RuleCheckResult]:
        results = []
        days = float(req.get("days", 0))
        hpd = float(req.get("hours_per_day", 0))
        expected_total = days * hpd

        overview = cur.get("overview", {})
        actual_total = float(overview.get("total_hours", 0))

        results.append(RuleCheckResult(
            name="total_hours_match",
            passed=abs(actual_total - expected_total) < _HOUR_TOLERANCE,
            message=f"overview.total_hours == days*hours_per_day ({expected_total}h)",
            expected=expected_total,
            actual=actual_total,
        ))
        results.append(RuleCheckResult(
            name="days_match",
            passed=overview.get("days") == int(days),
            message=f"overview.days == {int(days)}",
            expected=int(days),
            actual=overview.get("days"),
        ))
        results.append(RuleCheckResult(
            name="hours_per_day_match",
            passed=abs(float(overview.get("hours_per_day", 0)) - hpd) < _HOUR_TOLERANCE,
            message=f"overview.hours_per_day == {hpd}",
            expected=hpd,
            actual=overview.get("hours_per_day"),
        ))

        theory_hours = sum(
            float(s.get("duration_hours", 0))
            for s in cur.get("theory_sessions", [])
        )
        for grp, sessions in cur.get("practice_sessions", {}).items():
            practice_hours = sum(float(s.get("duration_hours", 0)) for s in sessions)
            total = theory_hours + practice_hours
            results.append(RuleCheckResult(
                name=f"hours_sum_{grp}",
                passed=abs(total - expected_total) <= _HOUR_TOLERANCE,
                message=f"{grp}: theory({theory_hours}h) + practice({practice_hours}h) = {total}h (expect {expected_total}h)",
                expected=expected_total,
                actual=total,
            ))

        return results

    # ── Group consistency ─────────────────────────────────────────────────────

    def _check_group_consistency(
        self, req: dict, cur: dict
    ) -> list[RuleCheckResult]:
        results = []
        ax_counts: dict[str, int] = req.get("ax_counts", {})
        practice = cur.get("practice_sessions", {})

        for grp, types in _AX_GROUPS.items():
            group_count = sum(ax_counts.get(t, 0) for t in types)
            has_sessions = grp in practice and len(practice[grp]) > 0

            if group_count > 0:
                results.append(RuleCheckResult(
                    name=f"group_present_{grp}",
                    passed=has_sessions,
                    message=f"{grp} ({'+'.join(types)}, {group_count}명) 실습 세션 존재",
                    expected=True,
                    actual=has_sessions,
                ))
            else:
                results.append(RuleCheckResult(
                    name=f"group_absent_{grp}",
                    passed=not has_sessions,
                    message=f"{grp} (0명) 실습 세션 없어야 함",
                    expected=False,
                    actual=has_sessions,
                ))

        return results

    # ── Session ordering ──────────────────────────────────────────────────────

    def _check_session_order(self, cur: dict) -> list[RuleCheckResult]:
        results = []

        theory_orders = [s.get("order", 0) for s in cur.get("theory_sessions", [])]
        if len(theory_orders) > 1:
            monotonic = all(
                theory_orders[i] < theory_orders[i + 1]
                for i in range(len(theory_orders) - 1)
            )
            results.append(RuleCheckResult(
                name="theory_order_monotonic",
                passed=monotonic,
                message="이론 세션 order 단조 증가",
                actual=theory_orders,
            ))

        for grp, sessions in cur.get("practice_sessions", {}).items():
            orders = [s.get("order", 0) for s in sessions]
            if len(orders) > 1:
                monotonic = all(
                    orders[i] < orders[i + 1] for i in range(len(orders) - 1)
                )
                results.append(RuleCheckResult(
                    name=f"practice_order_{grp}",
                    passed=monotonic,
                    message=f"{grp} 실습 세션 order 단조 증가",
                    actual=orders,
                ))

        return results

    # ── Duration validity ─────────────────────────────────────────────────────

    def _check_duration_validity(self, cur: dict) -> list[RuleCheckResult]:
        results = []

        invalid_theory = [
            s.get("title", f"idx{i}")
            for i, s in enumerate(cur.get("theory_sessions", []))
            if float(s.get("duration_hours", 0)) <= 0
        ]
        results.append(RuleCheckResult(
            name="theory_duration_positive",
            passed=len(invalid_theory) == 0,
            message="모든 이론 세션 duration_hours > 0",
            actual=invalid_theory or "all valid",
        ))

        for grp, sessions in cur.get("practice_sessions", {}).items():
            invalid = [
                s.get("title", f"idx{i}")
                for i, s in enumerate(sessions)
                if float(s.get("duration_hours", 0)) <= 0
            ]
            results.append(RuleCheckResult(
                name=f"practice_duration_{grp}",
                passed=len(invalid) == 0,
                message=f"{grp} 모든 실습 세션 duration_hours > 0",
                actual=invalid or "all valid",
            ))

        return results
