"""Requirement Coverage evaluation: how well the curriculum reflects the input requirements.

Combines an LLM judge for semantic dimensions (goal alignment, audience
appropriateness, constraint compliance) with rule-based numeric checks
that are handled by RuleBasedEvaluator.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

_PROMPT = """\
다음은 AI 교육 커리큘럼 설계 요구사항과 생성된 커리큘럼입니다.

[요구사항]
{requirements}

[생성된 커리큘럼 요약 (JSON)]
{curriculum}

각 차원에서 요구사항이 커리큘럼에 얼마나 반영되었는지 0~100으로 평가하세요.

- goal_alignment     : 교육 목표(goal)가 세션 목표·학습 결과에 얼마나 반영되었는가
- audience_appropriateness : 교육 대상자 수준·배경에 맞는 난이도·활동인가
- constraint_compliance    : 도구 제약, 시간 제약, 방식 제약이 준수되었는가

다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "goal_alignment": 0~100,
  "audience_appropriateness": 0~100,
  "constraint_compliance": 0~100,
  "overall": 0~100,
  "gaps": ["반영 안 된 요구사항 (최대 3개)"],
  "highlights": ["잘 반영된 요구사항 (최대 3개)"]
}}"""


@dataclass
class RequirementCoverageResult:
    goal_alignment: float           # 0-1
    audience_appropriateness: float
    constraint_compliance: float
    overall: float
    gaps: list[str]
    highlights: list[str]
    error: str | None = None


class RequirementCoverageEvaluator:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self.available = False
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            self.available = True
        except Exception:
            pass

    def evaluate(self, requirements: dict, curriculum: dict) -> RequirementCoverageResult:
        if not self.available:
            return RequirementCoverageResult(
                goal_alignment=0.0, audience_appropriateness=0.0,
                constraint_compliance=0.0, overall=0.0,
                gaps=[], highlights=[], error="openai not installed",
            )

        req_text = json.dumps(
            {
                "company": requirements.get("company"),
                "audience": requirements.get("audience"),
                "ai_experience": requirements.get("ai_experience"),
                "constraints": requirements.get("constraints"),
                "goal": requirements.get("goal"),
                "days": requirements.get("days"),
                "hours_per_day": requirements.get("hours_per_day"),
            },
            ensure_ascii=False,
            indent=2,
        )

        curriculum_summary = json.dumps(
            {
                "overview": curriculum.get("overview", {}),
                "theory_titles": [
                    s.get("title") for s in curriculum.get("theory_sessions", [])
                ],
                "theory_objectives": [
                    s.get("objective") for s in curriculum.get("theory_sessions", [])
                ],
                "practice_titles": {
                    grp: [s.get("title") for s in sessions]
                    for grp, sessions in curriculum.get("practice_sessions", {}).items()
                },
                "expected_outcomes": curriculum.get("expected_outcomes", []),
                "prerequisites": curriculum.get("prerequisites", []),
            },
            ensure_ascii=False,
            indent=2,
        )

        prompt = _PROMPT.format(requirements=req_text, curriculum=curriculum_summary)

        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content)
            return RequirementCoverageResult(
                goal_alignment=float(data.get("goal_alignment", 0)) / 100.0,
                audience_appropriateness=float(data.get("audience_appropriateness", 0)) / 100.0,
                constraint_compliance=float(data.get("constraint_compliance", 0)) / 100.0,
                overall=float(data.get("overall", 0)) / 100.0,
                gaps=data.get("gaps", []),
                highlights=data.get("highlights", []),
            )
        except Exception as e:
            return RequirementCoverageResult(
                goal_alignment=0.0, audience_appropriateness=0.0,
                constraint_compliance=0.0, overall=0.0,
                gaps=[], highlights=[], error=str(e),
            )
