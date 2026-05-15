"""평가 스키마 — 코드 검증 항목과 LLM 판단 항목 명확 분리."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"   # 경고: 통과이지만 주의 필요


# ── 코드 검증 항목 (결정적, 규칙 기반) ────────────────────────────────────────

@dataclass
class CodeCheck:
    name: str
    status: CheckStatus
    detail: str = ""
    expected: Any = None
    actual: Any = None

    @property
    def passed(self) -> bool:
        return self.status in (CheckStatus.PASS, CheckStatus.WARN)


@dataclass
class CodeValidationResult:
    checks: list[CodeCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CodeCheck]:
        return [c for c in self.checks if c.status == CheckStatus.FAIL]

    @property
    def warnings(self) -> list[CodeCheck]:
        return [c for c in self.checks if c.status == CheckStatus.WARN]

    @property
    def score(self) -> float:
        if not self.checks:
            return 1.0
        return sum(1 for c in self.checks if c.passed) / len(self.checks)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 3),
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail,
                 "expected": c.expected, "actual": c.actual}
                for c in self.checks
            ],
        }


# ── LLM 판단 항목 (확률적, 의미 기반) ────────────────────────────────────────

@dataclass
class LLMCheck:
    name: str
    score: float          # 0.0 ~ 1.0
    reason: str = ""
    threshold: float = 0.6
    extra: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold


@dataclass
class LLMValidationResult:
    checks: list[LLMCheck] = field(default_factory=list)
    raw_response: str = ""

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[LLMCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def score(self) -> float:
        if not self.checks:
            return 1.0
        return sum(c.score for c in self.checks) / len(self.checks)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 3),
            "checks": [
                {"name": c.name, "score": round(c.score, 3), "threshold": c.threshold,
                 "passed": c.passed, "reason": c.reason, **c.extra}
                for c in self.checks
            ],
        }


# ── 통합 검증 보고서 ──────────────────────────────────────────────────────────

@dataclass
class ValidationReport:
    code: CodeValidationResult = field(default_factory=CodeValidationResult)
    llm: LLMValidationResult = field(default_factory=LLMValidationResult)
    attempt: int = 1

    @property
    def passed(self) -> bool:
        return self.code.passed and self.llm.passed

    @property
    def code_passed(self) -> bool:
        return self.code.passed

    @property
    def llm_passed(self) -> bool:
        return self.llm.passed

    @property
    def overall_score(self) -> float:
        return (self.code.score + self.llm.score) / 2

    def failure_summary(self) -> str:
        parts: list[str] = []
        for c in self.code.failures:
            parts.append(f"[코드] {c.name}: {c.detail}")
        for c in self.llm.failures:
            parts.append(f"[LLM] {c.name}({c.score:.2f}<{c.threshold}): {c.reason}")
        return "\n".join(parts) if parts else ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "overall_score": round(self.overall_score, 3),
            "attempt": self.attempt,
            "code_validation": self.code.to_dict(),
            "llm_validation": self.llm.to_dict(),
        }


# ── 에이전트 진행 이벤트 ──────────────────────────────────────────────────────

@dataclass
class AgentProgress:
    stage: str          # "rag" | "generate" | "validate" | "retry" | "done" | "error"
    agent: str          # "RAGAgent" | "CurriculumAgent" | "ValidatorAgent" | "Orchestrator"
    message: str = ""
    data: Any = None    # 단계별 중간 결과


# ── 오케스트레이터 최종 결과 ──────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    curriculum: dict[str, Any] | None = None
    validation: ValidationReport | None = None
    rag_chunks: list[dict] = field(default_factory=list)
    attempts: int = 0
    reply: str = ""
    success: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "attempts": self.attempts,
            "reply": self.reply,
            "curriculum": self.curriculum,
            "validation": self.validation.to_dict() if self.validation else None,
            "rag_chunks_count": len(self.rag_chunks),
        }
