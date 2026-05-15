"""OrchestratorAgent — 전문 에이전트 파이프라인 조율."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .base import BaseAgent, load_prompt
from .rag_agent import RAGAgent
from .curriculum_agent import CurriculumGeneratorAgent
from .validator_agent import ValidatorAgent
from ..evaluation.schema import AgentProgress, OrchestratorResult, ValidationReport

_MAX_REGEN = 3
_RAG_QUERIES = [
    "AX Compass 유형별 특성과 교육 전략",
    "그룹별 실습 구성 방법 균형형 이해형 과신형 실행형 판단형 조심형",
]


class OrchestratorAgent(BaseAgent):
    name = "Orchestrator"

    def __init__(
        self,
        api_key: str,
        chroma_dir: Path,
        data_dir: Path,
        model: str = "gpt-4o-mini",
        on_progress: Callable[[AgentProgress], None] | None = None,
    ) -> None:
        super().__init__(api_key, model)
        self._system_prompt = load_prompt("orchestrator.txt")
        self._on_progress = on_progress

        self._rag = RAGAgent(api_key, chroma_dir, data_dir, model)
        self._generator = CurriculumGeneratorAgent(api_key, model)
        self._validator = ValidatorAgent(api_key, model)

    def run(self, requirements: dict[str, Any]) -> OrchestratorResult:
        self._emit(AgentProgress("rag", "RAGAgent", "AX Compass 자료 검색 중..."))

        # Step 1: RAG 검색
        goal = requirements.get("goal", "")
        audience = requirements.get("audience", "")
        extra_query = f"{goal} {audience} AI 교육"
        queries = _RAG_QUERIES + ([extra_query] if extra_query.strip() else [])
        rag_chunks = self._rag.search_multi(queries, k=6)
        rag_context = self._rag.build_context(rag_chunks)

        self._emit(AgentProgress(
            "rag_done", "RAGAgent",
            f"{len(rag_chunks)}개 청크 검색 완료",
            data={"chunks_count": len(rag_chunks)},
        ))

        # Step 2: 생성 → 검증 루프
        curriculum: dict[str, Any] | None = None
        last_report: ValidationReport | None = None
        failure_feedback = ""

        for attempt in range(1, _MAX_REGEN + 1):
            self._emit(AgentProgress(
                "generate", "CurriculumGeneratorAgent",
                f"커리큘럼 생성 중... (시도 {attempt}/{_MAX_REGEN})",
            ))

            try:
                curriculum = self._generator.generate(
                    requirements=requirements,
                    rag_context=rag_context,
                    failure_feedback=failure_feedback,
                )
            except Exception as e:
                self._emit(AgentProgress("error", "CurriculumGeneratorAgent", f"생성 실패: {e}"))
                return OrchestratorResult(
                    rag_chunks=rag_chunks,
                    attempts=attempt,
                    reply=f"커리큘럼 생성 중 오류가 발생했습니다: {e}",
                )

            self._emit(AgentProgress(
                "generated", "CurriculumGeneratorAgent",
                "커리큘럼 초안 완성",
                data=curriculum.get("overview", {}),
            ))

            # Step 3: 검증
            self._emit(AgentProgress("validate", "ValidatorAgent", "규칙 검증 + LLM 판단 중..."))

            last_report = self._validator.validate(
                curriculum=curriculum,
                requirements=requirements,
                rag_chunks=rag_chunks,
                attempt=attempt,
            )

            self._emit(AgentProgress(
                "validated", "ValidatorAgent",
                f"검증 {'통과' if last_report.passed else '실패'} "
                f"(코드:{last_report.code.score:.2f} LLM:{last_report.llm.score:.2f})",
                data=last_report.to_dict(),
            ))

            if last_report.passed:
                break

            if attempt < _MAX_REGEN:
                failure_feedback = last_report.failure_summary()
                self._emit(AgentProgress(
                    "retry", "Orchestrator",
                    f"검증 실패 항목 수정 후 재생성 ({attempt+1}/{_MAX_REGEN})\n{failure_feedback}",
                ))

        # Step 4: 최종 응답 생성
        reply = self._synthesize_reply(requirements, curriculum, last_report)

        success = curriculum is not None and (last_report.passed if last_report else False)
        self._emit(AgentProgress("done", "Orchestrator", reply))

        return OrchestratorResult(
            curriculum=curriculum,
            validation=last_report,
            rag_chunks=rag_chunks,
            attempts=attempt,
            reply=reply,
            success=success,
        )

    def _synthesize_reply(
        self,
        requirements: dict,
        curriculum: dict | None,
        report: ValidationReport | None,
    ) -> str:
        if curriculum is None:
            return "커리큘럼 생성에 실패했습니다. 요구사항을 확인하고 다시 시도해주세요."

        ov = curriculum.get("overview", {})
        status = "통과" if (report and report.passed) else "일부 경고 있음"
        code_score = f"{report.code.score:.0%}" if report else "N/A"
        llm_score = f"{report.llm.score:.0%}" if report else "N/A"

        context = f"""커리큘럼 생성 완료.

회사: {ov.get('company','')} | 대상: {ov.get('audience','')}
총 교육 시간: {ov.get('total_hours','')}h ({ov.get('days','')}일 × {ov.get('hours_per_day','')}h)
이론 세션: {len(curriculum.get('theory_sessions',[]))}개
실습 그룹: {', '.join(g for g,s in curriculum.get('practice_sessions',{}).items() if s)}
검증 상태: {status} (코드={code_score}, LLM={llm_score})

위 결과를 사용자에게 친근하게 200자 이내로 요약해주세요."""

        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": context},
        ]
        return self._chat(messages, temperature=0.5)

    def _emit(self, progress: AgentProgress) -> None:
        if self._on_progress:
            self._on_progress(progress)
