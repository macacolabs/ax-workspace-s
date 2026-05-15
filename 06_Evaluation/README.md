# 06_Evaluation — AX RAG 평가 파이프라인

## 개요

AdvancedRAGIndexer + 커리큘럼 생성 결과를 4개 차원에서 자동 평가합니다.

| 평가 모듈 | 파일 | 방식 | 출력 |
| --- | --- | --- | --- |
| Retrieval (Precision@k / MRR) | `evaluators/retrieval.py` | 키워드 매칭 | precision, mrr, hit 상세 |
| Faithfulness | `evaluators/faithfulness.py` | LLM (GPT-4o-mini) | 0-1 점수, 근거 없는 주장 목록 |
| Requirement Coverage | `evaluators/requirement_coverage.py` | LLM (GPT-4o-mini) | 목표/대상/제약 반영도 |
| Rule-based | `evaluators/rule_based.py` | 순수 Python | 시간 합계, 그룹 구성, 순서 등 |

## 디렉토리 구조

```
06_Evaluation/
├── evaluators/
│   ├── retrieval.py          # Precision@k, MRR
│   ├── faithfulness.py       # 커리큘럼 근거 충실도
│   ├── requirement_coverage.py  # 요구사항 반영도
│   └── rule_based.py         # 구조 규칙 검증
├── runner.py                 # 통합 실행 스크립트 (CLI)
├── report.py                 # JSON / Markdown 리포트 생성
├── testset_template.json     # 테스트셋 템플릿 (4개 케이스)
├── reports/                  # 평가 결과 출력 디렉토리
└── README.md
```

## 빠른 시작

### 1. 사전 조건

- `.env` 에 `OPENAI_API_KEY` 설정 (또는 환경변수)
- ChromaDB 인덱싱 완료 (Streamlit에서 "인덱싱 실행" 실행 또는 `--force-index` 사용)
- venv 활성화

```bash
cd c:/ax-dev/ax-workspace
.venv/Scripts/activate          # Windows
# source .venv/bin/activate    # Linux/Mac
```

### 2. 실행

```bash
cd 06_Evaluation

# 기본 실행 (testset_template.json 사용)
python runner.py --testset testset_template.json

# 재인덱싱 후 평가
python runner.py --testset testset_template.json --force-index

# 출력 디렉토리 지정
python runner.py --testset testset_template.json --output-dir reports/run01
```

결과 파일:
- `reports/eval_YYYYMMDD_HHMMSS.json`  — 전체 상세 결과
- `reports/eval_YYYYMMDD_HHMMSS.md`   — 마크다운 리포트

### 3. 출력 예시

```
평가 완료 | 4개 케이스
  Precision@k : 0.667
  MRR         : 1.000
  Faithfulness: 0.820
  Req Coverage: 0.780
  Rule Score  : 0.750
```

---

## 테스트셋 작성 방법

### 스키마

```json
{
  "version": "1.0",
  "cases": [
    {
      "id": "case_001",
      "description": "케이스 설명",
      "input": {
        "company": "회사명",
        "audience": "교육 대상자",
        "ai_experience": "AI 경험 수준",
        "constraints": "제약 사항",
        "goal": "교육 목표",
        "days": 2,
        "hours_per_day": 8,
        "ax_counts": {
          "균형형": 3, "이해형": 2,
          "과신형": 4, "실행형": 2,
          "판단형": 1, "조심형": 3
        }
      },
      "retrieval_queries": [
        {
          "query": "검색 쿼리 텍스트",
          "relevant_sections": ["예상 관련 키워드1", "키워드2"],
          "k": 6
        }
      ],
      "generated_curriculum": null
    }
  ]
}
```

### 필드 설명

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `id` | Y | 케이스 고유 ID |
| `description` | Y | 케이스 설명 |
| `input` | N | 커리큘럼 생성 입력값 (curriculum eval에 필요) |
| `retrieval_queries` | N | 검색 쿼리 목록 (빈 배열이면 retrieval eval 생략) |
| `retrieval_queries[].relevant_sections` | Y | 정답 청크가 포함해야 할 키워드 목록 |
| `retrieval_queries[].k` | N | top-k (기본: 6) |
| `generated_curriculum` | N | 커리큘럼 JSON (`null`이면 faithfulness/coverage/rule eval 생략) |

### 평가 조합

| `retrieval_queries` | `generated_curriculum` | 실행되는 평가 |
| --- | --- | --- |
| 있음 | null | Retrieval 전용 |
| 없음 | 있음 | Curriculum 전용 (Faithfulness + Coverage + Rule) |
| 있음 | 있음 | 전체 (모든 4개 평가) |
| 없음 | null | 케이스 스킵 |

---

## 평가 상세

### Retrieval — Precision@k / MRR

- **Precision@k**: top-k 결과 중 `relevant_sections` 키워드를 포함한 청크 비율
- **MRR**: 첫 번째 관련 청크의 순위 역수 (1/rank)
- 관련성 판단: 청크 텍스트 + section 헤딩에 키워드 포함 여부 (대소문자 무관)

> 정밀한 평가를 위해 사람이 레이블링한 chunk ID 목록을 `relevant_chunk_ids`로 제공하면  
> 코드를 수정하여 exact-match 기반 평가로 전환 가능합니다.

### Faithfulness (충실도)

GPT-4o-mini가 RAG로 검색된 청크를 근거로 커리큘럼의 AX Compass 관련 주장을 검증합니다.

- 0: 모든 주장이 근거 없음
- 1: 모든 주장이 근거 텍스트에 기반함
- `ungrounded_claims`에 근거 없는 구체적 주장 나열

### Requirement Coverage (요구사항 반영도)

| 차원 | 평가 내용 |
| --- | --- |
| `goal_alignment` | 교육 목표가 세션 목표·학습 결과에 반영되었는가 |
| `audience_appropriateness` | 교육 대상자 수준에 맞는 난이도·활동인가 |
| `constraint_compliance` | 도구·시간·방식 제약이 준수되었는가 |
| `overall` | 종합 점수 |

### Rule-based (구조 규칙)

| 규칙 | 검사 내용 |
| --- | --- |
| `total_hours_match` | `overview.total_hours == days * hours_per_day` |
| `days_match` | `overview.days == input.days` |
| `hours_per_day_match` | `overview.hours_per_day == input.hours_per_day` |
| `hours_sum_{그룹}` | `theory_hours + practice_hours == total_hours` (±0.5h 허용) |
| `group_present_{그룹}` | AX count > 0인 그룹은 `practice_sessions`에 존재 |
| `group_absent_{그룹}` | AX count == 0인 그룹은 `practice_sessions`에 없어야 함 |
| `theory_order_monotonic` | 이론 세션 `order` 단조 증가 |
| `practice_order_{그룹}` | 실습 세션 `order` 단조 증가 |
| `theory_duration_positive` | 모든 이론 세션 `duration_hours > 0` |
| `practice_duration_{그룹}` | 모든 실습 세션 `duration_hours > 0` |

---

## 커스터마이징

### 새 평가자 추가

`evaluators/` 에 새 파일을 만들고 `evaluators/__init__.py` 에 export 추가.  
`runner.py`의 `_run_case()` 에 호출 로직 추가.

### LLM 모델 변경

`FaithfulnessEvaluator` / `RequirementCoverageEvaluator` 생성 시 `model=` 파라미터 전달:

```python
FaithfulnessEvaluator(api_key, model="gpt-4o")
```

### 정확한 청크 ID 기반 Retrieval 평가

테스트셋에 `relevant_chunk_ids: ["id1", "id2"]` 필드 추가 후  
`RetrievalEvaluator._is_relevant()`를 ID 매칭으로 교체.
