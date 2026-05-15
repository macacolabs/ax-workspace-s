"""AX RAG Evaluation Runner.

Usage:
    python runner.py --testset testset_template.json
    python runner.py --testset testset_template.json --force-index
    python runner.py --testset my_testset.json --output-dir reports/run01

The runner expects an initialized ChromaDB (run Streamlit indexing first,
or pass --force-index to re-index before evaluation).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from 06_Evaluation/ or workspace root
_BASE = Path(__file__).parent.parent
sys.path.insert(0, str(_BASE / "05_Advanced_RAG_indexing_contextual"))

from indexing_pipeline import AdvancedRAGIndexer

from evaluators.retrieval import RetrievalEvaluator, RetrievalResult
from evaluators.faithfulness import FaithfulnessEvaluator, FaithfulnessResult
from evaluators.requirement_coverage import RequirementCoverageEvaluator, RequirementCoverageResult
from evaluators.rule_based import RuleBasedEvaluator, RuleBasedResult
from report import ReportGenerator


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    case_id: str
    description: str
    retrieval_results: list[RetrievalResult]
    faithfulness: FaithfulnessResult | None
    requirement_coverage: RequirementCoverageResult | None
    rule_based: RuleBasedResult | None
    elapsed_s: float


@dataclass
class Summary:
    total_cases: int
    retrieval_cases: int
    curriculum_cases: int
    avg_precision_at_k: float
    avg_mrr: float
    avg_faithfulness: float | None
    avg_requirement_coverage: float | None
    avg_rule_score: float | None


@dataclass
class EvaluationReport:
    cases: list[CaseResult]
    summary: Summary
    testset_version: str
    evaluated_at: str


# ── Runner ────────────────────────────────────────────────────────────────────

class EvaluationRunner:
    def __init__(
        self,
        api_key: str,
        chroma_dir: Path,
        data_dir: Path,
        output_dir: Path,
        force_index: bool = False,
    ) -> None:
        self._output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        print("Initializing AdvancedRAGIndexer...")
        self._indexer = AdvancedRAGIndexer(
            api_key=api_key,
            chroma_dir=chroma_dir,
            data_dir=data_dir,
            rerank=True,
        )
        if force_index:
            print("Force re-indexing...")
            idx_report = self._indexer.index_directory(force=True)
            print(f"  {idx_report}")

        self._retrieval_eval = RetrievalEvaluator(self._indexer)
        self._faithfulness_eval = FaithfulnessEvaluator(api_key)
        self._req_coverage_eval = RequirementCoverageEvaluator(api_key)
        self._rule_eval = RuleBasedEvaluator()

    def run(self, testset_path: Path) -> EvaluationReport:
        testset = json.loads(testset_path.read_text(encoding="utf-8"))
        cases = testset.get("cases", [])
        print(f"\nRunning evaluation on {len(cases)} test case(s)")

        case_results: list[CaseResult] = []
        for idx, case in enumerate(cases, start=1):
            print(f"\n[{idx}/{len(cases)}] {case['id']} — {case.get('description', '')}")
            result = self._run_case(case)
            case_results.append(result)

        summary = self._summarize(case_results)
        return EvaluationReport(
            cases=case_results,
            summary=summary,
            testset_version=testset.get("version", "1.0"),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _run_case(self, case: dict) -> CaseResult:
        t0 = time.time()
        retrieval_results: list[RetrievalResult] = []
        all_hits: list[dict] = []

        for rq in case.get("retrieval_queries", []):
            q = rq["query"]
            print(f"  Retrieval: {q[:70]}")
            rr = self._retrieval_eval.evaluate(
                query=q,
                relevant_sections=rq.get("relevant_sections", []),
                k=rq.get("k", 6),
            )
            retrieval_results.append(rr)
            # collect raw hits for downstream faithfulness eval
            raw = self._indexer.query(q, k=rq.get("k", 6))
            all_hits.extend(raw)

        curriculum = case.get("generated_curriculum")
        faithfulness_result: FaithfulnessResult | None = None
        req_coverage_result: RequirementCoverageResult | None = None
        rule_result: RuleBasedResult | None = None

        if curriculum:
            req = case.get("input", {})

            print("  Faithfulness...")
            faithfulness_result = self._faithfulness_eval.evaluate(curriculum, all_hits[:8])

            print("  Requirement coverage...")
            req_coverage_result = self._req_coverage_eval.evaluate(req, curriculum)

            print("  Rule checks...")
            rule_result = self._rule_eval.evaluate(req, curriculum)
            print(f"  Rules: {rule_result.passed_count}/{rule_result.total_count} passed")
        else:
            print("  (no generated_curriculum — skipping curriculum evals)")

        return CaseResult(
            case_id=case["id"],
            description=case.get("description", ""),
            retrieval_results=retrieval_results,
            faithfulness=faithfulness_result,
            requirement_coverage=req_coverage_result,
            rule_based=rule_result,
            elapsed_s=time.time() - t0,
        )

    def _summarize(self, results: list[CaseResult]) -> Summary:
        prec_vals: list[float] = []
        mrr_vals: list[float] = []
        faith_vals: list[float] = []
        cov_vals: list[float] = []
        rule_vals: list[float] = []
        retrieval_cases = 0
        curriculum_cases = 0

        for r in results:
            if r.retrieval_results:
                retrieval_cases += 1
                prec_vals.extend(rr.precision_at_k for rr in r.retrieval_results)
                mrr_vals.extend(rr.mrr for rr in r.retrieval_results)
            if r.faithfulness is not None:
                curriculum_cases += 1
                faith_vals.append(r.faithfulness.score)
            if r.requirement_coverage is not None:
                cov_vals.append(r.requirement_coverage.overall)
            if r.rule_based is not None:
                rule_vals.append(r.rule_based.score)

        def _avg(vals: list[float]) -> float | None:
            return sum(vals) / len(vals) if vals else None

        return Summary(
            total_cases=len(results),
            retrieval_cases=retrieval_cases,
            curriculum_cases=curriculum_cases,
            avg_precision_at_k=_avg(prec_vals) or 0.0,
            avg_mrr=_avg(mrr_vals) or 0.0,
            avg_faithfulness=_avg(faith_vals),
            avg_requirement_coverage=_avg(cov_vals),
            avg_rule_score=_avg(rule_vals),
        )


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AX RAG 평가 파이프라인",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--testset", required=True, help="테스트셋 JSON 파일 경로")
    parser.add_argument("--output-dir", default="reports", help="리포트 출력 디렉토리")
    parser.add_argument("--chroma-dir", default=None, help="ChromaDB 경로 (기본: ../chroma_db)")
    parser.add_argument("--data-dir", default=None, help="데이터 디렉토리 경로 (기본: ../Data)")
    parser.add_argument("--force-index", action="store_true", help="평가 전 강제 재인덱싱")
    args = parser.parse_args()

    import os
    from dotenv import load_dotenv

    load_dotenv(_BASE / ".env")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set (.env 또는 환경변수)", file=sys.stderr)
        sys.exit(1)

    chroma_dir = Path(args.chroma_dir) if args.chroma_dir else _BASE / "chroma_db"
    data_dir = Path(args.data_dir) if args.data_dir else _BASE / "Data"
    output_dir = Path(args.output_dir)

    runner = EvaluationRunner(
        api_key=api_key,
        chroma_dir=chroma_dir,
        data_dir=data_dir,
        output_dir=output_dir,
        force_index=args.force_index,
    )

    report = runner.run(Path(args.testset))

    gen = ReportGenerator()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"eval_{ts}.json"
    md_path = output_dir / f"eval_{ts}.md"
    gen.save_json(report, json_path)
    gen.save_markdown(report, md_path)

    s = report.summary
    print(f"\n{'='*60}")
    print(f"평가 완료 | {s.total_cases}개 케이스")
    print(f"  Precision@k : {s.avg_precision_at_k:.3f}")
    print(f"  MRR         : {s.avg_mrr:.3f}")
    if s.avg_faithfulness is not None:
        print(f"  Faithfulness: {s.avg_faithfulness:.3f}")
    if s.avg_requirement_coverage is not None:
        print(f"  Req Coverage: {s.avg_requirement_coverage:.3f}")
    if s.avg_rule_score is not None:
        print(f"  Rule Score  : {s.avg_rule_score:.3f}")
    print(f"\n  JSON -> {json_path}")
    print(f"  MD   -> {md_path}")


if __name__ == "__main__":
    main()
