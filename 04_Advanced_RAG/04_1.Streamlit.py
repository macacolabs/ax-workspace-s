import os
import json
import sys
import time
import hashlib
import secrets
from pathlib import Path
from dataclasses import dataclass, field

import streamlit as st
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ── 인증 설정 ───────────────────────────────────────────────────
TOKEN_TTL = 8 * 3600  # 8시간

USERS = {
    "admin": hashlib.sha256("admin".encode()).hexdigest(),
}

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def _make_token() -> str:
    return secrets.token_hex(32)

def is_authenticated() -> bool:
    token = st.session_state.get("auth_token")
    expiry = st.session_state.get("auth_expiry", 0)
    return bool(token) and time.time() < expiry

def do_login(username: str, password: str) -> bool:
    expected = USERS.get(username)
    if expected and expected == _hash(password):
        st.session_state.auth_token = _make_token()
        st.session_state.auth_expiry = time.time() + TOKEN_TTL
        st.session_state.auth_user = username
        return True
    return False

def do_logout():
    for k in ("auth_token", "auth_expiry", "auth_user"):
        st.session_state.pop(k, None)

# ── 로그인 페이지 ───────────────────────────────────────────────
LOGIN_CSS = """
<style>
.login-wrap {
    max-width: 380px;
    margin: 80px auto 0;
    padding: 40px 36px 36px;
    border: 1px solid #e0e0e0;
    border-radius: 16px;
    background: #fff;
}
.login-logo {
    font-size: 2rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    color: #111;
    text-align: center;
    margin-bottom: 4px;
}
.login-sub {
    font-size: 0.82rem;
    color: #888;
    text-align: center;
    margin-bottom: 28px;
}
.login-err {
    background: #fff0f0;
    border: 1px solid #ffcccc;
    color: #cc0000;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 0.82rem;
    margin-bottom: 12px;
    text-align: center;
}
</style>
"""

def show_login_page():
    st.set_page_config(
        page_title="AX 교육 커리큘럼 — 로그인",
        page_icon="◈",
        layout="centered",
    )
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-wrap">
        <div class="login-logo">◈ AX Curriculum</div>
        <div class="login-sub">기업 맞춤형 AX 교육 커리큘럼 설계</div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        st.markdown("#### 로그인")
        username = st.text_input("아이디", placeholder="아이디를 입력하세요")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인", use_container_width=True)

    if submitted:
        if do_login(username.strip(), password):
            st.rerun()
        else:
            st.markdown(
                '<div class="login-err">아이디 또는 비밀번호가 올바르지 않습니다.</div>',
                unsafe_allow_html=True,
            )

# ── 경로 ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "Data"
CHROMA_DIR = BASE_DIR / "chroma_db"

AX_TYPES = ["균형형", "이해형", "과신형", "실행형", "판단형", "조심형"]
GROUPS = {
    "A": ["균형형", "이해형"],
    "B": ["과신형", "실행형"],
    "C": ["판단형", "조심형"],
}

# ── CSS ─────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* 전체 배경 */
.stApp {
    background: #ffffff;
    color: #111111;
}

/* 사이드바 */
section[data-testid="stSidebar"] {
    background: #0a0a0a !important;
    border-right: 1px solid #222222;
}
section[data-testid="stSidebar"] * {
    color: #f0f0f0 !important;
}
section[data-testid="stSidebar"] .stTextInput input,
section[data-testid="stSidebar"] .stNumberInput input,
section[data-testid="stSidebar"] .stSelectbox select {
    background: #1a1a1a !important;
    border: 1px solid #333 !important;
    color: #f0f0f0 !important;
    border-radius: 6px !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #333 !important;
}

/* 채팅 메시지 */
.user-msg {
    background: #111111;
    color: #ffffff;
    padding: 12px 16px;
    border-radius: 12px 12px 2px 12px;
    margin: 8px 0 8px 60px;
    font-size: 0.92rem;
    line-height: 1.6;
}
.bot-msg {
    background: #f5f5f5;
    color: #111111;
    padding: 12px 16px;
    border-radius: 12px 12px 12px 2px;
    margin: 8px 60px 8px 0;
    font-size: 0.92rem;
    line-height: 1.6;
    border: 1px solid #e8e8e8;
}
.msg-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 4px;
    color: #888;
}
.user-label { color: #aaaaaa !important; }

/* 커리큘럼 카드 */
.overview-card {
    background: #111111;
    color: #ffffff;
    border-radius: 12px;
    padding: 28px 32px;
    margin-bottom: 24px;
}
.overview-card h2 {
    font-size: 1.3rem;
    font-weight: 700;
    margin: 0 0 6px 0;
    color: #ffffff;
}
.overview-card .subtitle {
    font-size: 0.85rem;
    color: #999999;
    margin-bottom: 20px;
}
.stat-row {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-top: 16px;
}
.stat-box {
    background: #1e1e1e;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 12px 18px;
    flex: 1;
    min-width: 100px;
}
.stat-box .label {
    font-size: 0.7rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
}
.stat-box .value {
    font-size: 1.2rem;
    font-weight: 700;
    color: #ffffff;
}

/* 섹션 헤더 */
.section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 28px 0 14px 0;
    padding-bottom: 10px;
    border-bottom: 2px solid #111111;
}
.section-header .tag {
    background: #111111;
    color: #ffffff;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 20px;
}
.section-header h3 {
    font-size: 1rem;
    font-weight: 700;
    margin: 0;
    color: #111111;
}

/* 세션 카드 */
.session-card {
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 12px;
    background: #ffffff;
    transition: border-color 0.15s;
}
.session-card:hover { border-color: #111111; }
.session-card .session-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: #111111;
    margin-bottom: 6px;
}
.session-card .session-meta {
    font-size: 0.78rem;
    color: #666666;
    margin-bottom: 10px;
    display: flex;
    gap: 12px;
}
.session-card .badge {
    background: #f0f0f0;
    color: #333;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
}
.session-card .duration-badge {
    background: #111111;
    color: #ffffff;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
}
.session-card .objective {
    font-size: 0.82rem;
    color: #444444;
    margin-bottom: 8px;
    line-height: 1.5;
}
.session-card .activities {
    list-style: none;
    padding: 0;
    margin: 0;
}
.session-card .activities li {
    font-size: 0.8rem;
    color: #555555;
    padding: 3px 0;
    border-top: 1px solid #f0f0f0;
    display: flex;
    align-items: flex-start;
    gap: 8px;
}
.session-card .activities li::before {
    content: "→";
    color: #999999;
    flex-shrink: 0;
    margin-top: 1px;
}

/* 그룹 헤더 */
.group-header-A {
    background: #111111;
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px 8px 0 0;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.group-header-B {
    background: #333333;
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px 8px 0 0;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.group-header-C {
    background: #555555;
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px 8px 0 0;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* 시간 바 */
.time-bar-container {
    margin: 16px 0;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    overflow: hidden;
}
.time-bar-row {
    display: flex;
    align-items: center;
    padding: 10px 16px;
    font-size: 0.8rem;
    border-bottom: 1px solid #f0f0f0;
}
.time-bar-row:last-child { border-bottom: none; }
.time-bar-label { width: 120px; color: #555; font-weight: 500; }
.time-bar-track {
    flex: 1;
    height: 6px;
    background: #f0f0f0;
    border-radius: 3px;
    margin: 0 12px;
    overflow: hidden;
}
.time-bar-fill {
    height: 100%;
    background: #111111;
    border-radius: 3px;
}
.time-bar-val { color: #111; font-weight: 700; min-width: 40px; text-align: right; }

/* 기대효과 */
.outcome-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;
    font-size: 0.85rem;
    color: #333333;
}
.outcome-item:last-child { border-bottom: none; }
.outcome-dot {
    width: 6px;
    height: 6px;
    background: #111111;
    border-radius: 50%;
    flex-shrink: 0;
    margin-top: 6px;
}

/* 버튼 */
.stButton > button {
    background: #111111 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.03em !important;
    padding: 10px 20px !important;
    transition: background 0.15s !important;
}
.stButton > button:hover {
    background: #333333 !important;
}

/* chat input */
.stChatInputContainer {
    border-top: 1px solid #e0e0e0 !important;
    background: #ffffff !important;
}
.stChatInput textarea {
    border: 1px solid #ddd !important;
    border-radius: 10px !important;
    font-size: 0.9rem !important;
}

/* 검증 배지 */
.verify-ok {
    background: #f0faf0;
    border: 1px solid #cce5cc;
    color: #2d6a2d;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    display: inline-block;
    margin: 4px 0;
}
.verify-warn {
    background: #fff8f0;
    border: 1px solid #f0d9b5;
    color: #7a4f00;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
    display: inline-block;
    margin: 4px 0;
}

/* 타이틀 */
.main-title {
    font-size: 1.5rem;
    font-weight: 800;
    color: #111111;
    letter-spacing: -0.02em;
    margin-bottom: 2px;
}
.main-subtitle {
    font-size: 0.85rem;
    color: #888888;
    margin-bottom: 24px;
}

/* divider */
.clean-divider {
    border: none;
    border-top: 1px solid #eeeeee;
    margin: 20px 0;
}
</style>
"""

# ── 단계별 질의 정의 ───────────────────────────────────────────
STEPS = [
    {
        "phase": "company",
        "question": "1️⃣ 교육을 진행할 **회사명**을 입력해주세요.",
        "hint": "예: 삼성전자",
        "key": "company",
        "cast": str,
    },
    {
        "phase": "audience",
        "question": "2️⃣ **교육 대상자**를 설명해주세요.",
        "hint": "예: 비개발 직군 대리~차장, AI 경험 거의 없음",
        "key": "audience",
        "cast": str,
    },
    {
        "phase": "ai_experience",
        "question": "3️⃣ 교육 대상자의 **AI 경험 수준**을 입력해주세요.",
        "hint": "예: AI 툴 사용 경험 없음, ChatGPT 가끔 사용해봄, 업무에 정기적으로 활용 중",
        "key": "ai_experience",
        "cast": str,
    },
    {
        "phase": "constraints",
        "question": "4️⃣ 커리큘럼에 **꼭 반영해야 할 조건 또는 제한 사항**을 입력해주세요.",
        "hint": "예: ChatGPT만 사용 가능, 실습 위주 구성, 코딩 금지",
        "key": "constraints",
        "cast": str,
    },
    {
        "phase": "goal",
        "question": "5️⃣ **교육 목표**를 입력해주세요.",
        "hint": "예: 업무 생산성 향상, AI 도구 활용 역량 강화",
        "key": "goal",
        "cast": str,
    },
    {
        "phase": "days",
        "question": "6️⃣ **교육 일수**를 입력해주세요.",
        "hint": "예: 2",
        "key": "days",
        "cast": int,
        "error": "숫자(정수)로 입력해주세요. 예: 2",
    },
    {
        "phase": "hours_per_day",
        "question": "7️⃣ **일 교육 시간**을 입력해주세요.",
        "hint": "예: 8",
        "key": "hours_per_day",
        "cast": float,
        "error": "숫자로 입력해주세요. 예: 8",
    },
]

STEP_PHASES = [s["phase"] for s in STEPS]

# AX Compass 개별 입력 단계 (phase: "ax_0" ~ "ax_5")
AX_STEPS = [
    {"phase": f"ax_{i}", "type": t, "order": i}
    for i, t in enumerate(AX_TYPES)
]
AX_STEP_PHASES = [s["phase"] for s in AX_STEPS]

GROUP_DESC = {t: grp for grp, types in GROUPS.items() for t in types}

CURRICULUM_SYSTEM_PROMPT = """당신은 20년 경력의 IT·AI 강사이자 교육 스타트업 대표입니다.

다음 JSON 스키마로만 응답하세요. 다른 텍스트 없이 JSON만 출력합니다.

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
  "prerequisites": ["string"]
}

시간 제약 규칙:
- theory_sessions duration_hours 합 + practice_sessions 단일 그룹 합 = total_hours
- 그룹별 실습 시간 합은 동일 (동시 진행)
- 0명 그룹은 practice_sessions에서 완전 제외
- 이론 40~50%, 실습 50~60% 권장
"""


# ── RAG ───────────────────────────────────────────────────────
class RAGIndexer:
    def __init__(self, api_key: str, data_dir: Path):
        self.available = False
        self.data_dir = data_dir
        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
            embed_fn = OpenAIEmbeddingFunction(api_key=api_key, model_name="text-embedding-3-small")
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            self._ax_col = client.get_or_create_collection("ax_compass_types", embedding_function=embed_fn)
            self._cur_col = client.get_or_create_collection("curriculum_examples", embedding_function=embed_fn)
            self.available = True
        except Exception:
            pass

    def _load_pdf(self, path: Path) -> str:
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
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
        except Exception:
            return ""

    def _chunk(self, text: str, size: int = 800, overlap: int = 100) -> list[str]:
        chunks, start = [], 0
        while start < len(text):
            chunks.append(text[start:start + size])
            start += size - overlap
        return [c for c in chunks if len(c.strip()) > 50]

    def index_documents(self) -> str:
        if not self.available or not self.data_dir.exists():
            return "RAG 비활성 (chromadb 미설치 또는 Data 폴더 없음)"
        files = [f for f in self.data_dir.glob("*") if f.suffix.lower() in (".pdf", ".xlsx", ".xls")]
        if not files:
            return "Data 폴더 비어있음 - LLM 전용 모드"

        count = 0
        for f in files:
            text = self._load_pdf(f) if f.suffix.lower() == ".pdf" else self._load_excel(f)
            if not text.strip():
                continue
            chunks = self._chunk(text)
            is_ax = "axcompass" in f.stem.lower() or "ax_compass" in f.stem.lower()
            col = self._ax_col if is_ax else self._cur_col
            existing = set(col.get()["ids"])
            ids = [f"{f.stem}_{i}" for i in range(len(chunks)) if f"{f.stem}_{i}" not in existing]
            docs = [chunks[i] for i in range(len(chunks)) if f"{f.stem}_{i}" not in existing]
            if ids:
                col.add(ids=ids, documents=docs)
                count += len(ids)
        return f"인덱싱 완료 ({count}청크 신규)" if count else "모든 문서 이미 인덱싱됨"

    def query(self, ax_types: list[str], topics: list[str], audience: str) -> tuple[str, str]:
        ax_ctx, cur_ctx = "", ""
        if not self.available:
            return ax_ctx, cur_ctx
        if self._ax_col.count() > 0:
            r = self._ax_col.query(
                query_texts=[f"AX Compass 유형 특성: {', '.join(ax_types)}"],
                n_results=min(6, self._ax_col.count())
            )
            ax_ctx = "\n---\n".join(r["documents"][0]) if r["documents"] else ""
        if self._cur_col.count() > 0:
            r = self._cur_col.query(
                query_texts=[f"교육 대상: {audience}. 주제: {', '.join(topics)}"],
                n_results=min(6, self._cur_col.count())
            )
            cur_ctx = "\n---\n".join(r["documents"][0]) if r["documents"] else ""
        return ax_ctx, cur_ctx


# ── 커리큘럼 생성 ──────────────────────────────────────────────
def build_curriculum_prompt(chat_summary: str, ax_counts: dict, rag_ax: str, rag_cur: str) -> str:
    active_groups = {}
    for grp, types in GROUPS.items():
        cnt = sum(ax_counts.get(t, 0) for t in types)
        if cnt > 0:
            active_groups[grp] = {"types": types, "count": cnt}

    group_str = "\n".join(
        f"  그룹{k}: {', '.join(v['types'])} ({v['count']}명)"
        for k, v in active_groups.items()
    )
    inactive = [k for k in GROUPS if k not in active_groups]

    return f"""다음 대화에서 수집한 정보와 AX Compass 분포를 바탕으로 커리큘럼 JSON을 생성하세요.

## 대화에서 수집한 교육 정보
{chat_summary}

## AX Compass 인원 분포
{group_str}
{'제외 그룹(0명): 그룹' + ', 그룹'.join(inactive) if inactive else ''}

## RAG: AX Compass 유형 특성
{rag_ax if rag_ax else '(없음 - LLM 지식 활용)'}

## RAG: 커리큘럼 예시
{rag_cur if rag_cur else '(없음 - LLM 지식 활용)'}

반드시 유효한 JSON만 출력하세요."""


# ── 커리큘럼 시각화 ────────────────────────────────────────────
def render_curriculum(data: dict):
    ov = data.get("overview", {})
    total_h = ov.get("total_hours", 0)
    theory = data.get("theory_sessions", [])
    practice = data.get("practice_sessions", {})
    theory_total = sum(s.get("duration_hours", 0) for s in theory)
    active_practice = {k: v for k, v in practice.items() if v}
    practice_totals = {k: sum(s.get("duration_hours", 0) for s in v) for k, v in active_practice.items()}

    # ── 오버뷰 카드
    st.markdown(f"""
    <div class="overview-card">
        <div style="font-size:0.72rem;letter-spacing:0.12em;text-transform:uppercase;color:#666;margin-bottom:6px;">AX 교육 커리큘럼</div>
        <h2>{ov.get('company','')} · {ov.get('department','')}</h2>
        <div class="subtitle">{ov.get('audience','')}</div>
        <div style="font-size:0.8rem;color:#aaa;margin-bottom:8px;">
            {'  ·  '.join(ov.get('topics',[]))}
        </div>
        <div class="stat-row">
            <div class="stat-box">
                <div class="label">총 시간</div>
                <div class="value">{total_h}h</div>
            </div>
            <div class="stat-box">
                <div class="label">교육 일수</div>
                <div class="value">{ov.get('days','')}일</div>
            </div>
            <div class="stat-box">
                <div class="label">일 시간</div>
                <div class="value">{ov.get('hours_per_day','')}h</div>
            </div>
            <div class="stat-box">
                <div class="label">난이도</div>
                <div class="value" style="font-size:1rem;">{ov.get('difficulty','')}</div>
            </div>
            <div class="stat-box">
                <div class="label">참여 그룹</div>
                <div class="value">{len(active_practice)}개</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── AX Compass 분포
    dist = ov.get("ax_compass_distribution", {})
    if dist:
        st.markdown("""
        <div class="section-header">
            <span class="tag">AX Compass</span>
            <h3>인원 분포</h3>
        </div>""", unsafe_allow_html=True)
        total_people = sum(v.get("count", 0) for v in dist.values())
        if total_people > 0:
            st.markdown('<div class="time-bar-container">', unsafe_allow_html=True)
            for grp, info in dist.items():
                cnt = info.get("count", 0)
                if cnt == 0:
                    continue
                pct = int(cnt / total_people * 100)
                types_str = " · ".join(info.get("types", []))
                st.markdown(f"""
                <div class="time-bar-row">
                    <div class="time-bar-label">{grp} ({types_str})</div>
                    <div class="time-bar-track">
                        <div class="time-bar-fill" style="width:{pct}%"></div>
                    </div>
                    <div class="time-bar-val">{cnt}명</div>
                </div>""", unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── 시간 배분
    st.markdown("""
    <div class="section-header">
        <span class="tag">시간 배분</span>
        <h3>이론 vs 실습</h3>
    </div>""", unsafe_allow_html=True)
    if total_h > 0:
        theory_pct = int(theory_total / total_h * 100)
        practice_h = list(practice_totals.values())[0] if practice_totals else 0
        practice_pct = int(practice_h / total_h * 100)
        st.markdown(f"""
        <div class="time-bar-container">
            <div class="time-bar-row">
                <div class="time-bar-label">공통 이론</div>
                <div class="time-bar-track">
                    <div class="time-bar-fill" style="width:{theory_pct}%"></div>
                </div>
                <div class="time-bar-val">{theory_total}h</div>
            </div>
            <div class="time-bar-row">
                <div class="time-bar-label">그룹 실습</div>
                <div class="time-bar-track">
                    <div class="time-bar-fill" style="width:{practice_pct}%"></div>
                </div>
                <div class="time-bar-val">{practice_h}h</div>
            </div>
        </div>""", unsafe_allow_html=True)

    # ── 공통 이론 세션
    st.markdown("""
    <div class="section-header">
        <span class="tag">공통</span>
        <h3>이론 세션 (전원 참여)</h3>
    </div>""", unsafe_allow_html=True)
    for s in theory:
        acts_html = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
        concepts = "  ".join(
            f'<span class="badge">{c}</span>' for c in s.get("key_concepts", [])
        )
        st.markdown(f"""
        <div class="session-card">
            <div class="session-title">세션 {s.get('order','')} · {s.get('title','')}</div>
            <div class="session-meta">
                <span class="duration-badge">{s.get('duration_hours',0)}h</span>
                {concepts}
            </div>
            <div class="objective">{s.get('objective','')}</div>
            <ul class="activities">{acts_html}</ul>
        </div>""", unsafe_allow_html=True)

    # ── 그룹별 실습
    if active_practice:
        st.markdown("""
        <div class="section-header">
            <span class="tag">그룹별</span>
            <h3>맞춤형 실습 세션 (동시 진행)</h3>
        </div>""", unsafe_allow_html=True)

        cols = st.columns(len(active_practice))
        grp_styles = {"A": "group-header-A", "B": "group-header-B", "C": "group-header-C"}

        for col, (grp, sessions) in zip(cols, active_practice.items()):
            with col:
                types_str = " · ".join(GROUPS.get(grp, []))
                grp_h = practice_totals.get(grp, 0)
                style = grp_styles.get(grp, "group-header-A")
                st.markdown(f"""
                <div class="{style}">
                    그룹 {grp} · {grp_h}h<br>
                    <span style="font-weight:400;font-size:0.72rem;opacity:0.8">{types_str}</span>
                </div>""", unsafe_allow_html=True)
                for s in sessions:
                    acts_html = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
                    st.markdown(f"""
                    <div class="session-card" style="border-radius:0 0 10px 10px;margin-top:0;border-top:none;">
                        <div class="session-title">{s.get('title','')}</div>
                        <div class="session-meta">
                            <span class="duration-badge">{s.get('duration_hours',0)}h</span>
                        </div>
                        <div class="objective">{s.get('objective','')}</div>
                        <div style="font-size:0.75rem;color:#888;margin-bottom:6px;font-style:italic">
                            {s.get('ax_type_rationale','')}
                        </div>
                        <ul class="activities">{acts_html}</ul>
                    </div>""", unsafe_allow_html=True)

    # ── 기대 효과 + 사전 학습
    outcomes = data.get("expected_outcomes", [])
    prereqs = data.get("prerequisites", [])

    if outcomes or prereqs:
        c1, c2 = st.columns(2)
        with c1:
            if outcomes:
                st.markdown("""
                <div class="section-header">
                    <span class="tag">효과</span>
                    <h3>교육 후 기대 효과</h3>
                </div>""", unsafe_allow_html=True)
                items = "".join(
                    f'<div class="outcome-item"><div class="outcome-dot"></div>{o}</div>'
                    for o in outcomes
                )
                st.markdown(f'<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px">{items}</div>',
                            unsafe_allow_html=True)
        with c2:
            if prereqs:
                st.markdown("""
                <div class="section-header">
                    <span class="tag">준비</span>
                    <h3>추천 사전 학습</h3>
                </div>""", unsafe_allow_html=True)
                items = "".join(
                    f'<div class="outcome-item"><div class="outcome-dot" style="background:#999"></div>{p}</div>'
                    for p in prereqs
                )
                st.markdown(f'<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px">{items}</div>',
                            unsafe_allow_html=True)

    # ── 시간 검증
    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)
    prac_list = list(practice_totals.values())
    if prac_list:
        grp_h = prac_list[0]
        calc = theory_total + grp_h
        ok = abs(calc - total_h) < 0.1
        unique_ok = len(set(round(h, 1) for h in prac_list)) == 1
        v1 = "verify-ok" if ok else "verify-warn"
        v2 = "verify-ok" if unique_ok else "verify-warn"
        st.markdown(f"""
        <span class="{v1}">{'✓' if ok else '⚠'} 총 시간: 이론 {theory_total}h + 실습 {grp_h}h = {calc}h / 목표 {total_h}h</span>
        &nbsp;
        <span class="{v2}">{'✓' if unique_ok else '⚠'} 그룹별 실습 시간: {list(practice_totals.values())}</span>
        """, unsafe_allow_html=True)


# ── 앱 메인 ───────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="AX 교육 커리큘럼 설계",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # ── 세션 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                "안녕하세요! AX 교육 커리큘럼 설계 챗봇입니다.\n\n"
                "몇 가지 항목을 순서대로 입력하시면 맞춤형 커리큘럼을 설계해드립니다.\n\n"
                + STEPS[0]["question"] + f"\n\n*{STEPS[0]['hint']}*"
            ),
        }]
    if "curriculum" not in st.session_state:
        st.session_state.curriculum = None
    if "rag_status" not in st.session_state:
        st.session_state.rag_status = None
    if "rag_indexer" not in st.session_state:
        st.session_state.rag_indexer = None
    if "phase" not in st.session_state:
        st.session_state.phase = STEP_PHASES[0]
    if "ax_counts" not in st.session_state:
        st.session_state.ax_counts = {}
    if "edu_info" not in st.session_state:
        st.session_state.edu_info = {}

    # ── 사이드바
    with st.sidebar:
        st.markdown("### ◈ 설정")
        st.markdown("---")

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            api_key = st.text_input("OpenAI API Key", type="password", placeholder="sk-...")
        else:
            st.markdown("**API Key** ✓ 환경변수에서 로드됨")

        st.markdown("---")

        # AX Compass 현황 표시 (대화에서 입력된 경우)
        if st.session_state.ax_counts:
            st.markdown("### AX Compass 현황")
            for grp, types in GROUPS.items():
                cnt = sum(st.session_state.ax_counts.get(t, 0) for t in types)
                bar = "█" * min(cnt, 10) + "░" * max(0, 10 - cnt)
                st.markdown(
                    f"<small><b>그룹{grp}</b> {bar} {cnt}명</small>",
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        use_rag = st.checkbox("RAG 활성화", value=True)

        if use_rag and api_key:
            if st.button("문서 인덱싱", use_container_width=True):
                with st.spinner("인덱싱 중..."):
                    rag = RAGIndexer(api_key, DATA_DIR)
                    status = rag.index_documents()
                    st.session_state.rag_indexer = rag
                    st.session_state.rag_status = status
            if st.session_state.rag_status:
                st.markdown(f"<small>{st.session_state.rag_status}</small>", unsafe_allow_html=True)

        st.markdown("---")
        if st.button("새 대화 시작", use_container_width=True):
            st.session_state.messages = [{
                "role": "assistant",
                "content": (
                    "새 커리큘럼 설계를 시작합니다.\n\n"
                    + STEPS[0]["question"] + f"\n\n*{STEPS[0]['hint']}*"
                ),
            }]
            st.session_state.curriculum = None
            st.session_state.phase = STEP_PHASES[0]
            st.session_state.ax_counts = {}
            st.session_state.edu_info = {}
            st.rerun()

        st.markdown("---")
        user = st.session_state.get("auth_user", "")
        expiry = st.session_state.get("auth_expiry", 0)
        remain = max(0, int((expiry - time.time()) / 60))
        st.markdown(
            f"<small>👤 <b>{user}</b> · 세션 {remain}분 남음</small>",
            unsafe_allow_html=True,
        )
        if st.button("로그아웃", use_container_width=True):
            do_logout()
            st.rerun()

    # ── 메인 영역
    if not api_key:
        st.markdown('<div class="main-title">◈ AX 교육 커리큘럼 설계</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">사이드바에서 OpenAI API Key를 입력해주세요.</div>',
                    unsafe_allow_html=True)
        return

    client = OpenAI(api_key=api_key)

    # RAG 자동 초기화
    if use_rag and st.session_state.rag_indexer is None:
        rag = RAGIndexer(api_key, DATA_DIR)
        st.session_state.rag_indexer = rag

    # 탭
    tab_chat, tab_result = st.tabs(["💬 대화", "📋 커리큘럼"])

    with tab_chat:
        st.markdown('<div class="main-title">◈ AX 교육 커리큘럼 설계</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">기업 맞춤형 AI 전환 교육 커리큘럼을 설계합니다.</div>',
                    unsafe_allow_html=True)

        # 채팅 히스토리
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="msg-label user-label">나</div>
                <div class="user-msg">{msg["content"]}</div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="msg-label">챗봇</div>
                <div class="bot-msg">{msg["content"]}</div>
                """, unsafe_allow_html=True)

        # ── ready 상태: 입력 요약 + 커리큘럼 생성 버튼
        if st.session_state.phase == "ready":
            info = st.session_state.edu_info
            ax_counts = st.session_state.ax_counts

            with st.expander("📋 입력 정보 확인", expanded=False):
                st.json({**info, "ax_counts": ax_counts})

            if st.button("🎯 커리큘럼 생성", type="primary", use_container_width=False):
                status = st.status("커리큘럼 생성 중...", expanded=True)
                try:
                    with status:
                        st.write("① RAG 검색 중...")
                        rag_ax, rag_cur = "", ""
                        rag_inst = st.session_state.get("rag_indexer")
                        if use_rag and rag_inst and rag_inst.available:
                            active_types = [t for grp, types in GROUPS.items()
                                            for t in types if ax_counts.get(t, 0) > 0]
                            constraints = info.get("constraints", "")
                            topics_list = [t.strip() for t in constraints.split(",") if t.strip()]
                            audience = info.get("audience", "기업 직원")
                            rag_ax, rag_cur = rag_inst.query(active_types, topics_list, audience)

                        st.write("② GPT-4o 커리큘럼 생성 중...")
                        chat_summary = "\n".join(f"{k}: {v}" for k, v in info.items())
                        prompt = build_curriculum_prompt(chat_summary, ax_counts, rag_ax, rag_cur)

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
                        st.session_state.curriculum = json.loads(raw)
                        status.update(label="✅ 생성 완료!", state="complete")

                    st.rerun()
                except Exception as e:
                    status.update(label=f"❌ 오류 발생", state="error")
                    st.error(f"오류 내용: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        # ── 사용자 입력
        phase = st.session_state.phase
        if phase in AX_STEP_PHASES:
            ax_step = next(s for s in AX_STEPS if s["phase"] == phase)
            placeholder = f"0 이상 정수 입력 (해당 없으면 0)"
        elif phase == "ready":
            placeholder = "커리큘럼 생성 버튼을 눌러주세요."
        else:
            current_step = next((s for s in STEPS if s["phase"] == phase), None)
            placeholder = current_step["hint"] if current_step else "입력해주세요..."

        if user_input := st.chat_input(placeholder, disabled=(phase == "ready")):
            st.session_state.messages.append({"role": "user", "content": user_input})
            reply = ""

            # ── AX Compass 개별 입력
            if phase in AX_STEP_PHASES:
                ax_step = next(s for s in AX_STEPS if s["phase"] == phase)
                try:
                    n = int(user_input.strip())
                    if n < 0:
                        raise ValueError("음수 불가")
                    st.session_state.ax_counts[ax_step["type"]] = n
                    next_ax_idx = ax_step["order"] + 1

                    if next_ax_idx < len(AX_STEPS):
                        # 다음 유형 질문
                        next_ax = AX_STEPS[next_ax_idx]
                        grp = GROUP_DESC[next_ax["type"]]
                        st.session_state.phase = next_ax["phase"]
                        reply = (
                            f"**{next_ax['type']}** (그룹 {grp}) 인원수를 입력해주세요.\n\n"
                            f"*0 이상 정수, 해당 없으면 0*"
                        )
                    else:
                        # 모든 AX 입력 완료
                        counts = st.session_state.ax_counts
                        total = sum(counts.values())
                        grp_lines = "\n".join(
                            f"- 그룹{g} ({' · '.join(t)}): "
                            f"{sum(counts.get(tp, 0) for tp in t)}명"
                            for g, t in GROUPS.items()
                        )
                        reply = (
                            f"✅ AX Compass 입력 완료! 총 **{total}명**\n\n"
                            f"{grp_lines}\n\n"
                            "아래 **커리큘럼 생성** 버튼을 눌러주세요."
                        )
                        st.session_state.phase = "ready"
                except ValueError as e:
                    reply = f"숫자(0 이상 정수)로 입력해주세요. 오류: {e}"

            # ── 기본 정보 단계별 입력
            else:
                step = next((s for s in STEPS if s["phase"] == phase), None)
                if step:
                    val_raw = user_input.strip()
                    try:
                        if "choices" in step:
                            val = step["choices"].get(val_raw, step["choices"].get(val_raw.lower()))
                            if not val:
                                raise ValueError
                        else:
                            val = step["cast"](val_raw)
                    except (ValueError, TypeError):
                        reply = step.get("error", "다시 입력해주세요.")
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                        st.rerun()

                    st.session_state.edu_info[step["key"]] = val
                    cur_idx = STEP_PHASES.index(phase)
                    next_idx = cur_idx + 1

                    if next_idx < len(STEPS):
                        next_step = STEPS[next_idx]
                        st.session_state.phase = next_step["phase"]
                        reply = next_step["question"] + f"\n\n*{next_step['hint']}*"
                    else:
                        # 기본 정보 완료 → AX Compass 첫 번째 유형 질문
                        info = st.session_state.edu_info
                        total_h = info.get("days", 0) * info.get("hours_per_day", 0)
                        first_ax = AX_STEPS[0]
                        grp = GROUP_DESC[first_ax["type"]]
                        st.session_state.phase = first_ax["phase"]
                        reply = (
                            f"✅ 기본 정보 입력 완료!\n\n"
                            f"| 항목 | 내용 |\n|------|------|\n"
                            f"| 회사 | {info.get('company','')} |\n"
                            f"| 교육 대상자 | {info.get('audience','')} |\n"
                            f"| AI 경험 | {info.get('ai_experience','')} |\n"
                            f"| 조건/제한 | {info.get('constraints','')} |\n"
                            f"| 목표 | {info.get('goal','')} |\n"
                            f"| 일정 | {info.get('days','')}일 × {info.get('hours_per_day','')}h "
                            f"= 총 {total_h}h |\n\n"
                            f"---\n"
                            f"이제 **AX Compass 유형별 인원수**를 하나씩 입력해주세요.\n\n"
                            f"**{first_ax['type']}** (그룹 {grp}) 인원수를 입력해주세요.\n\n"
                            f"*0 이상 정수, 해당 없으면 0*"
                        )

            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

    with tab_result:
        if st.session_state.curriculum:
            render_curriculum(st.session_state.curriculum)

            st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)
            col1, col2 = st.columns([1, 4])
            with col1:
                json_str = json.dumps(st.session_state.curriculum, ensure_ascii=False, indent=2)
                st.download_button(
                    "JSON 다운로드",
                    data=json_str.encode("utf-8"),
                    file_name="curriculum.json",
                    mime="application/json",
                    use_container_width=True,
                )
        else:
            st.markdown("""
            <div style="text-align:center;padding:80px 0;color:#aaaaaa;">
                <div style="font-size:2.5rem;margin-bottom:16px;">◈</div>
                <div style="font-size:1rem;font-weight:500">커리큘럼이 아직 생성되지 않았습니다.</div>
                <div style="font-size:0.85rem;margin-top:8px">
                    💬 대화 탭에서 정보를 입력하고 커리큘럼을 생성해주세요.
                </div>
            </div>
            """, unsafe_allow_html=True)


if __name__ == "__main__":
    if not is_authenticated():
        show_login_page()
    else:
        main()
