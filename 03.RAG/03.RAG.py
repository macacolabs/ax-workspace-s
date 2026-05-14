#!/usr/bin/env python3
"""AX 교육 커리큘럼 RAG 설계 챗봇"""

import os
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── 경로 설정 ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "Data"
CHROMA_DIR = BASE_DIR / "chroma_db"

# ── AX Compass 정의 ────────────────────────────────────────────
AX_TYPES = ["균형형", "이해형", "과신형", "실행형", "판단형", "조심형"]

GROUPS = {
    "A": ["균형형", "이해형"],
    "B": ["과신형", "실행형"],
    "C": ["판단형", "조심형"],
}

# ── 시스템 프롬프트 ────────────────────────────────────────────
CURRICULUM_SYSTEM_PROMPT = """당신은 20년 경력의 IT·AI 강사이자 교육 스타트업 대표입니다.

강의 철학:
- 투자한 시간만큼 수강생에게 실질적 가치(취업, 업무 능력 향상)를 제공
- 이론보다 실습 중심, 현업 적용 가능성 최우선
- AX Compass 유형 특성에 맞는 정밀한 맞춤형 설계

역할: AX 교육 커리큘럼을 JSON 형식으로 생성합니다.

출력 규칙:
1. 반드시 아래 JSON 스키마를 따를 것
2. 시간 제약을 반드시 만족할 것: 이론 세션 합 + 그룹 실습 합(단일 그룹 기준) = 총 교육 시간
3. 0명 그룹은 practice_sessions에서 완전 제외
4. 세션명/목표/활동은 구체적으로 작성, 예시 자료 문장 직접 복사 금지
5. RAG 검색 결과를 참고해 현업 적용 가능한 내용으로 재구성

JSON 스키마:
{
  "overview": {
    "company": "string",
    "department": "string",
    "audience": "string",
    "topics": ["string"],
    "total_hours": number,
    "days": number,
    "hours_per_day": number,
    "difficulty": "입문|초급|중급|고급",
    "ax_compass_distribution": {
      "그룹A": {"types": ["균형형","이해형"], "count": number},
      "그룹B": {"types": ["과신형","실행형"], "count": number},
      "그룹C": {"types": ["판단형","조심형"], "count": number}
    }
  },
  "theory_sessions": [
    {
      "order": number,
      "title": "string",
      "duration_hours": number,
      "objective": "string",
      "activities": ["string"],
      "key_concepts": ["string"]
    }
  ],
  "practice_sessions": {
    "그룹A": [
      {
        "order": number,
        "title": "string",
        "duration_hours": number,
        "objective": "string",
        "activities": ["string"],
        "ax_type_rationale": "string"
      }
    ],
    "그룹B": [],
    "그룹C": []
  },
  "expected_outcomes": ["string"],
  "prerequisites": ["string"],
  "rag_references": ["string"]
}
"""

# ── 데이터 클래스 ──────────────────────────────────────────────
@dataclass
class EducationRequest:
    company: str = ""
    department: str = ""
    audience: str = ""
    topics: list = field(default_factory=list)
    days: int = 0
    hours_per_day: float = 0.0
    ax_counts: dict = field(default_factory=dict)

    @property
    def total_hours(self) -> float:
        return self.days * self.hours_per_day

    @property
    def active_groups(self) -> dict:
        result = {}
        for grp, types in GROUPS.items():
            count = sum(self.ax_counts.get(t, 0) for t in types)
            if count > 0:
                result[grp] = {"types": types, "count": count}
        return result

    def is_complete(self) -> bool:
        return bool(
            self.company and self.department and self.audience
            and self.topics and self.days > 0 and self.hours_per_day > 0
            and self.ax_counts
        )


# ── RAG 인덱서 ─────────────────────────────────────────────────
class RAGIndexer:
    def __init__(self, api_key: str):
        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
            self._chromadb = chromadb
            self._embed_fn = OpenAIEmbeddingFunction(
                api_key=api_key,
                model_name="text-embedding-3-small",
            )
            self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._ax_col = self._client.get_or_create_collection(
                "ax_compass_types", embedding_function=self._embed_fn
            )
            self._cur_col = self._client.get_or_create_collection(
                "curriculum_examples", embedding_function=self._embed_fn
            )
            self.available = True
        except ImportError:
            print("[경고] chromadb 미설치 → LLM 전용 모드")
            self.available = False

    def _load_pdf(self, path: Path) -> str:
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            print(f"  PDF 로드 실패 {path.name}: {e}")
            return ""

    def _load_excel(self, path: Path) -> str:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), data_only=True)
            parts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    line = " | ".join(str(c) for c in row if c is not None)
                    if line.strip():
                        parts.append(line)
            return "\n".join(parts)
        except Exception as e:
            print(f"  Excel 로드 실패 {path.name}: {e}")
            return ""

    def _chunk(self, text: str, size: int = 800, overlap: int = 100) -> list[str]:
        chunks, start = [], 0
        while start < len(text):
            chunks.append(text[start:start + size])
            start += size - overlap
        return [c for c in chunks if len(c.strip()) > 50]

    def index_documents(self):
        if not self.available:
            return

        if not DATA_DIR.exists():
            print(f"[경고] Data 폴더 없음: {DATA_DIR}")
            return

        files = list(DATA_DIR.glob("*"))
        if not files:
            print("[경고] Data 폴더 비어 있음 → RAG 컨텍스트 없이 생성")
            return

        print("\n[RAG] 문서 인덱싱 중...")

        for f in files:
            suffix = f.suffix.lower()
            if suffix == ".pdf":
                text = self._load_pdf(f)
            elif suffix in (".xlsx", ".xls"):
                text = self._load_excel(f)
            else:
                continue

            if not text.strip():
                continue

            chunks = self._chunk(text)
            is_ax = "axcompass" in f.stem.lower() or "ax_compass" in f.stem.lower()
            collection = self._ax_col if is_ax else self._cur_col

            existing = set(collection.get()["ids"])
            ids, docs = [], []
            for i, c in enumerate(chunks):
                doc_id = f"{f.stem}_{i}"
                if doc_id not in existing:
                    ids.append(doc_id)
                    docs.append(c)

            if ids:
                collection.add(ids=ids, documents=docs)
                print(f"  ✓ {f.name} → {len(ids)}청크 ({collection.name})")
            else:
                print(f"  - {f.name} 이미 인덱싱됨")

    def query_ax_types(self, type_names: list[str], n: int = 6) -> str:
        if not self.available or self._ax_col.count() == 0:
            return ""
        query = f"AX Compass 유형 특성: {', '.join(type_names)}"
        results = self._ax_col.query(query_texts=[query], n_results=min(n, self._ax_col.count()))
        return "\n---\n".join(results["documents"][0]) if results["documents"] else ""

    def query_curriculum(self, topics: list[str], audience: str, n: int = 6) -> str:
        if not self.available or self._cur_col.count() == 0:
            return ""
        query = f"교육 대상: {audience}. 주제: {', '.join(topics)}"
        results = self._cur_col.query(query_texts=[query], n_results=min(n, self._cur_col.count()))
        return "\n---\n".join(results["documents"][0]) if results["documents"] else ""


# ── 커리큘럼 생성 ──────────────────────────────────────────────
def build_generation_prompt(req: EducationRequest, ax_context: str, cur_context: str) -> str:
    active = req.active_groups
    group_str = "\n".join(
        f"  그룹{k}: {', '.join(v['types'])} ({v['count']}명)"
        for k, v in active.items()
    )
    inactive = [k for k in GROUPS if k not in active]

    prompt = f"""다음 정보를 바탕으로 AX 교육 커리큘럼 JSON을 생성하세요.

## 교육 기본 정보
- 회사/부서: {req.company} / {req.department}
- 교육 대상: {req.audience}
- 주요 주제: {', '.join(req.topics)}
- 교육 일정: {req.days}일 × {req.hours_per_day}시간 = 총 {req.total_hours}시간

## AX Compass 인원 분포
{group_str}
{'- 제외 그룹(0명): 그룹' + ', 그룹'.join(inactive) if inactive else ''}

## 시간 제약 (반드시 준수)
- theory_sessions duration_hours 합계 + practice_sessions 단일 그룹 duration_hours 합계 = {req.total_hours}
- 그룹별 실습 시간 합계는 동일해야 함 (동시 진행)
- 이론 비중 권장: 40~50%, 실습 비중: 50~60%

## RAG: AX Compass 유형 특성
{ax_context if ax_context else '(인덱싱된 AX Compass 문서 없음 - LLM 지식 활용)'}

## RAG: 커리큘럼 예시 참고
{cur_context if cur_context else '(인덱싱된 커리큘럼 예시 없음 - LLM 지식 활용)'}

## 생성 지침
1. 이론 세션은 전원 공통 (그룹 구분 없음)
2. 실습/프로젝트는 그룹별 AX 유형 특성에 맞게 차별화
3. 예시 자료 문장 직접 복사 금지 - 현재 요구사항에 맞게 재구성
4. rag_references 필드에 참고한 RAG 문서/섹션 명시
5. 인원수 0명 그룹은 practice_sessions에서 완전 제외

반드시 유효한 JSON만 출력하세요. 다른 텍스트 없이 JSON만."""

    return prompt


def generate_curriculum(client: OpenAI, req: EducationRequest, rag: RAGIndexer) -> dict:
    active_types = [t for grp in req.active_groups.values() for t in grp["types"]]

    print("\n[RAG] 유형 특성 검색 중...")
    ax_context = rag.query_ax_types(active_types)

    print("[RAG] 커리큘럼 예시 검색 중...")
    cur_context = rag.query_curriculum(req.topics, req.audience)

    print("[GPT] 커리큘럼 생성 중...\n")

    prompt = build_generation_prompt(req, ax_context, cur_context)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": CURRICULUM_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.6,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    return json.loads(raw)


# ── 출력 포매터 ────────────────────────────────────────────────
def print_curriculum(data: dict):
    ov = data.get("overview", {})
    total = ov.get("total_hours", 0)

    print("\n" + "═" * 60)
    print(f"  {ov.get('company', '')} / {ov.get('department', '')} AX 교육 커리큘럼")
    print("═" * 60)
    print(f"  대상: {ov.get('audience', '')}")
    print(f"  일정: {ov.get('days', '')}일 × {ov.get('hours_per_day', '')}h = {total}h")
    print(f"  난이도: {ov.get('difficulty', '')}")

    dist = ov.get("ax_compass_distribution", {})
    if dist:
        print("\n  [AX Compass 분포]")
        for grp, info in dist.items():
            print(f"    {grp}: {', '.join(info.get('types', []))} → {info.get('count', 0)}명")

    theory = data.get("theory_sessions", [])
    theory_total = sum(s.get("duration_hours", 0) for s in theory)
    print(f"\n{'─' * 60}")
    print(f"  [공통 이론 세션] (합계: {theory_total}h)")
    print(f"{'─' * 60}")
    for s in theory:
        print(f"\n  Day {s.get('order', '?')} | {s.get('title', '')} [{s.get('duration_hours', 0)}h]")
        print(f"  목표: {s.get('objective', '')}")
        for act in s.get("activities", []):
            print(f"    • {act}")

    practice = data.get("practice_sessions", {})
    for grp, sessions in practice.items():
        if not sessions:
            continue
        grp_total = sum(s.get("duration_hours", 0) for s in sessions)
        print(f"\n{'─' * 60}")
        print(f"  [그룹 {grp} 실습 세션] (합계: {grp_total}h)")
        print(f"{'─' * 60}")
        for s in sessions:
            print(f"\n  세션 {s.get('order', '?')} | {s.get('title', '')} [{s.get('duration_hours', 0)}h]")
            print(f"  목표: {s.get('objective', '')}")
            print(f"  유형 근거: {s.get('ax_type_rationale', '')}")
            for act in s.get("activities", []):
                print(f"    • {act}")

    outcomes = data.get("expected_outcomes", [])
    if outcomes:
        print(f"\n{'─' * 60}")
        print("  [교육 후 기대 효과]")
        for o in outcomes:
            print(f"    ✓ {o}")

    prereqs = data.get("prerequisites", [])
    if prereqs:
        print(f"\n  [추천 사전 학습]")
        for p in prereqs:
            print(f"    → {p}")

    refs = data.get("rag_references", [])
    if refs:
        print(f"\n  [RAG 참고 출처]")
        for r in refs:
            print(f"    [ref] {r}")

    print("\n" + "═" * 60)

    # 시간 검증
    practice_hours = []
    for sessions in practice.values():
        if sessions:
            practice_hours.append(sum(s.get("duration_hours", 0) for s in sessions))

    if practice_hours:
        grp_h = practice_hours[0]
        calc_total = theory_total + grp_h
        status = "✓" if abs(calc_total - total) < 0.1 else "⚠ 불일치"
        print(f"  시간 검증: 이론 {theory_total}h + 실습 {grp_h}h = {calc_total}h / 목표 {total}h {status}")
        unique = len(set(round(h, 1) for h in practice_hours))
        if unique > 1:
            print(f"  ⚠ 그룹별 실습 시간 불일치: {practice_hours}")
        else:
            print(f"  ✓ 그룹별 실습 시간 동일: {grp_h}h")
    print()


# ── 입력 수집 ──────────────────────────────────────────────────
def prompt_input(label: str, validator=None, cast=None):
    while True:
        val = input(f"  {label}: ").strip()
        if not val:
            print("    값을 입력해주세요.")
            continue
        if cast:
            try:
                val = cast(val)
            except ValueError:
                print(f"    올바른 형식으로 입력해주세요.")
                continue
        if validator and not validator(val):
            continue
        return val


def collect_request() -> EducationRequest:
    req = EducationRequest()

    print("\n" + "─" * 60)
    print("  [1단계] 교육 기본 정보")
    print("─" * 60)
    req.company = prompt_input("회사명")
    req.department = prompt_input("부서명")
    req.audience = prompt_input("교육 대상자 설명 (예: 비개발 직군 대리~차장, AI 경험 없음)")
    topics_raw = prompt_input("주요 주제/도구 (쉼표 구분, 예: ChatGPT 활용, 업무 자동화, 프롬프트 엔지니어링)")
    req.topics = [t.strip() for t in topics_raw.split(",") if t.strip()]
    req.days = prompt_input("교육 일수", cast=int)
    req.hours_per_day = prompt_input("일 교육 시간 (예: 8)", cast=float)

    print(f"\n  ※ 총 교육 시간: {req.total_hours}h")

    print("\n" + "─" * 60)
    print("  [2단계] AX Compass 유형별 인원수")
    print("─" * 60)
    print("  유형: 균형형 / 이해형 / 과신형 / 실행형 / 판단형 / 조심형")
    print("  (해당 없는 유형은 0 입력)\n")

    for t in AX_TYPES:
        count = prompt_input(f"{t} 인원수", cast=int)
        req.ax_counts[t] = count

    print("\n  [AX Compass 그룹 요약]")
    for grp, types in GROUPS.items():
        cnt = sum(req.ax_counts.get(t, 0) for t in types)
        status = f"{cnt}명" if cnt > 0 else "0명 (제외)"
        print(f"    그룹 {grp} ({', '.join(types)}): {status}")

    return req


# ── 메인 ───────────────────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════════╗
║   AX 교육 커리큘럼 RAG 설계 챗봇 (v2.0)                 ║
║   AX Compass 유형별 맞춤형 커리큘럼 자동 설계            ║
╚══════════════════════════════════════════════════════════╝

명령어: 'new' = 새 커리큘럼 | 'quit' = 종료
"""


def get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    print("OPENAI_API_KEY 미설정.")
    key = input("OpenAI API Key 입력: ").strip()
    if not key:
        print("API Key 필요. 종료합니다.")
        sys.exit(1)
    return key


def main():
    api_key = get_api_key()
    client = OpenAI(api_key=api_key)

    print(BANNER)

    rag = RAGIndexer(api_key=api_key)
    rag.index_documents()

    while True:
        print("\n새 커리큘럼을 설계하려면 Enter, 종료는 'quit':")
        cmd = input("  > ").strip().lower()
        if cmd in ("quit", "exit"):
            print("종료합니다.")
            break

        try:
            req = collect_request()
        except (KeyboardInterrupt, EOFError):
            print("\n입력 취소.")
            continue

        if not req.active_groups:
            print("\n[오류] 인원수가 1명 이상인 그룹이 없습니다.")
            continue

        try:
            curriculum = generate_curriculum(client, req, rag)
            print_curriculum(curriculum)

            save = input("JSON 파일로 저장하시겠습니까? (y/n): ").strip().lower()
            if save == "y":
                fname = BASE_DIR / f"curriculum_{req.company}_{req.department}.json"
                fname.write_text(
                    json.dumps(curriculum, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(f"  저장 완료: {fname}")

        except Exception as e:
            print(f"\n[오류] {e}")


if __name__ == "__main__":
    main()
