"""Report generation: JSON and Markdown output from EvaluationReport."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any


def _to_serializable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_serializable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_serializable(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    return obj


class ReportGenerator:
    def save_json(self, report: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _to_serializable(report)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON  -> {path}")

    def save_markdown(self, report: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        md = self._build_markdown(report)
        path.write_text(md, encoding="utf-8")
        print(f"MD    -> {path}")

    # ── Markdown builder ──────────────────────────────────────────────────────

    def _build_markdown(self, report: Any) -> str:
        lines: list[str] = []
        s = report.summary

        lines += [
            "# AX RAG 평가 리포트",
            "",
            f"**평가일시:** {report.evaluated_at}",
            f"**테스트셋 버전:** {report.testset_version}",
            "",
            "## 요약 점수",
            "",
            "| 메트릭 | 점수 |",
            "| --- | --- |",
            f"| Precision@k (avg) | {s.avg_precision_at_k:.3f} |",
            f"| MRR (avg) | {s.avg_mrr:.3f} |",
        ]
        if s.avg_faithfulness is not None:
            lines.append(f"| Faithfulness (avg) | {s.avg_faithfulness:.3f} |")
        if s.avg_requirement_coverage is not None:
            lines.append(f"| Requirement Coverage (avg) | {s.avg_requirement_coverage:.3f} |")
        if s.avg_rule_score is not None:
            lines.append(f"| Rule Score (avg) | {s.avg_rule_score:.3f} |")

        lines += [
            "",
            f"총 케이스: **{s.total_cases}** "
            f"(검색 평가: {s.retrieval_cases}, 커리큘럼 평가: {s.curriculum_cases})",
            "",
            "---",
            "",
            "## 케이스별 결과",
            "",
        ]

        for cr in report.cases:
            lines += [
                f"### {cr.case_id}",
                "",
                f"**설명:** {cr.description}",
                f"**소요시간:** {cr.elapsed_s:.1f}s",
                "",
            ]

            if cr.retrieval_results:
                lines += [
                    "#### Retrieval (Precision@k / MRR)",
                    "",
                    "| 쿼리 | P@k | MRR | Relevant/k | Avg Rerank |",
                    "| --- | ---: | ---: | ---: | ---: |",
                ]
                for rr in cr.retrieval_results:
                    avg_rs = f"{rr.avg_rerank_score:.3f}" if rr.avg_rerank_score is not None else "-"
                    q = rr.query[:55]
                    lines.append(
                        f"| {q} | {rr.precision_at_k:.3f} | {rr.mrr:.3f}"
                        f" | {rr.num_relevant}/{rr.k} | {avg_rs} |"
                    )

                lines += ["", "**Hit 상세 (첫 쿼리)**", ""]
                first_rr = cr.retrieval_results[0]
                lines += [
                    "| Rank | Section | Retrieval | RRF | Rerank | Relevant |",
                    "| ---: | --- | --- | ---: | ---: | --- |",
                ]
                for h in first_rr.hits:
                    rs = f"{h.rerank_score:.3f}" if h.rerank_score is not None else "-"
                    rel = "O" if h.is_relevant else ""
                    sec = h.section[:40]
                    lines.append(
                        f"| {h.rank} | {sec} | {h.retrieval} | {h.rrf_score:.4f} | {rs} | {rel} |"
                    )
                lines.append("")

            if cr.faithfulness is not None:
                f = cr.faithfulness
                score_str = f"{f.score:.3f}" if not f.error else f"ERROR: {f.error}"
                lines += [
                    "#### Faithfulness",
                    "",
                    f"| 점수 | 이유 |",
                    f"| ---: | --- |",
                    f"| {score_str} | {f.reason} |",
                ]
                if f.ungrounded_claims:
                    claims = " / ".join(f.ungrounded_claims)
                    lines.append(f"\n> 근거 없는 주장: {claims}")
                lines.append("")

            if cr.requirement_coverage is not None:
                rc = cr.requirement_coverage
                if rc.error:
                    lines += ["#### Requirement Coverage", "", f"ERROR: {rc.error}", ""]
                else:
                    lines += [
                        "#### Requirement Coverage",
                        "",
                        "| 차원 | 점수 |",
                        "| --- | ---: |",
                        f"| 목표 부합도 | {rc.goal_alignment:.3f} |",
                        f"| 대상자 적합성 | {rc.audience_appropriateness:.3f} |",
                        f"| 제약 준수 | {rc.constraint_compliance:.3f} |",
                        f"| **종합** | **{rc.overall:.3f}** |",
                    ]
                    if rc.gaps:
                        lines.append(f"\n> 미반영: {' / '.join(rc.gaps)}")
                    if rc.highlights:
                        lines.append(f"\n> 잘 반영: {' / '.join(rc.highlights)}")
                    lines.append("")

            if cr.rule_based is not None:
                rb = cr.rule_based
                lines += [
                    "#### Rule-based",
                    "",
                    f"통과: **{rb.passed_count}/{rb.total_count}** ({rb.score:.1%})",
                    "",
                    "| 규칙 | 결과 | 메시지 |",
                    "| --- | :---: | --- |",
                ]
                for chk in rb.checks:
                    icon = "PASS" if chk.passed else "**FAIL**"
                    lines.append(f"| {chk.name} | {icon} | {chk.message} |")
                lines.append("")

            lines += ["---", ""]

        return "\n".join(lines)
