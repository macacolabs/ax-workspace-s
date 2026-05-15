"""
Advanced RAG Indexing — Streamlit UI
=====================================
04_1.Streamlit.py 기반으로 고도화된 AdvancedRAGIndexer를 연동한 버전.
- 구조 인식 PDF/Excel 파서
- 증분 인덱싱 (SHA-256 변경 감지)
- 메타데이터 필터링 (doc_type / page / sheet)
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from indexing_pipeline import AdvancedRAGIndexer

load_dotenv(Path(__file__).parent.parent / ".env")

# ── 경로 ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "Data"
CHROMA_DIR = BASE_DIR / "chroma_db"

# ── 인증 ─────────────────────────────────────────────────────────────────────
TOKEN_TTL = 8 * 3600
USERS = {"admin": hashlib.sha256("admin".encode()).hexdigest()}


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def is_authenticated() -> bool:
    return bool(st.session_state.get("auth_token")) and time.time() < st.session_state.get("auth_expiry", 0)


def do_login(username: str, password: str) -> bool:
    if USERS.get(username) == _hash(password):
        st.session_state.auth_token  = secrets.token_hex(32)
        st.session_state.auth_expiry = time.time() + TOKEN_TTL
        st.session_state.auth_user   = username
        return True
    return False


def do_logout():
    for k in ("auth_token", "auth_expiry", "auth_user"):
        st.session_state.pop(k, None)


# ── 커리큘럼 설정 ──────────────────────────────────────────────────────────────
AX_TYPES = ["균형형", "이해형", "과신형", "실행형", "판단형", "조심형"]
GROUPS   = {"A": ["균형형", "이해형"], "B": ["과신형", "실행형"], "C": ["판단형", "조심형"]}
GROUP_DESC = {t: grp for grp, types in GROUPS.items() for t in types}

STEPS = [
    {"phase": "company",       "question": "1️⃣ 교육을 진행할 **회사명**을 입력해주세요.",             "hint": "예: 삼성전자",                                         "key": "company",        "cast": str},
    {"phase": "audience",      "question": "2️⃣ **교육 대상자**를 설명해주세요.",                     "hint": "예: 비개발 직군 대리~차장, AI 경험 거의 없음",              "key": "audience",       "cast": str},
    {"phase": "ai_experience", "question": "3️⃣ 교육 대상자의 **AI 경험 수준**을 입력해주세요.",      "hint": "예: ChatGPT 가끔 사용해봄",                              "key": "ai_experience",  "cast": str},
    {"phase": "constraints",   "question": "4️⃣ **꼭 반영해야 할 조건 또는 제한 사항**을 입력해주세요.", "hint": "예: ChatGPT만 사용 가능, 실습 위주 구성",               "key": "constraints",    "cast": str},
    {"phase": "goal",          "question": "5️⃣ **교육 목표**를 입력해주세요.",                       "hint": "예: 업무 생산성 향상, AI 도구 활용 역량 강화",             "key": "goal",           "cast": str},
    {"phase": "days",          "question": "6️⃣ **교육 일수**를 입력해주세요.",                       "hint": "예: 2",                                                "key": "days",           "cast": int,   "error": "숫자(정수)로 입력해주세요. 예: 2"},
    {"phase": "hours_per_day", "question": "7️⃣ **일 교육 시간**을 입력해주세요.",                    "hint": "예: 8",                                                "key": "hours_per_day",  "cast": float, "error": "숫자로 입력해주세요. 예: 8"},
]
STEP_PHASES = [s["phase"] for s in STEPS]
AX_STEPS    = [{"phase": f"ax_{i}", "type": t, "order": i} for i, t in enumerate(AX_TYPES)]
AX_STEP_PHASES = [s["phase"] for s in AX_STEPS]

CURRICULUM_SYSTEM_PROMPT = """당신은 20년 경력의 IT·AI 강사이자 교육 스타트업 대표입니다.

다음 JSON 스키마로만 응답하세요. 다른 텍스트 없이 JSON만 출력합니다.

{
  "overview": {
    "company": "string", "department": "string", "audience": "string",
    "topics": ["string"], "total_hours": number, "days": number,
    "hours_per_day": number, "difficulty": "입문|초급|중급|고급",
    "ax_compass_distribution": {
      "그룹A": {"types": ["균형형","이해형"], "count": number},
      "그룹B": {"types": ["과신형","실행형"], "count": number},
      "그룹C": {"types": ["판단형","조심형"], "count": number}
    }
  },
  "theory_sessions": [
    {"order": number, "title": "string", "duration_hours": number,
     "objective": "string", "activities": ["string"], "key_concepts": ["string"]}
  ],
  "practice_sessions": {
    "그룹A": [{"order": number, "title": "string", "duration_hours": number,
               "objective": "string", "activities": ["string"], "ax_type_rationale": "string"}],
    "그룹B": [], "그룹C": []
  },
  "expected_outcomes": ["string"],
  "prerequisites": ["string"]
}

시간 제약 규칙:
- theory_sessions 합 + practice_sessions 단일 그룹 합 = total_hours
- 그룹별 실습 시간 합은 동일 (동시 진행)
- 0명 그룹은 practice_sessions에서 완전 제외
- 이론 40~50%, 실습 50~60% 권장
"""

# ── CSS ───────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #ffffff; color: #111111; }
section[data-testid="stSidebar"] { background: #0a0a0a !important; border-right: 1px solid #222222; }
section[data-testid="stSidebar"] * { color: #f0f0f0 !important; }
section[data-testid="stSidebar"] hr { border-color: #333 !important; }
.user-msg { background:#111111;color:#ffffff;padding:12px 16px;border-radius:12px 12px 2px 12px;margin:8px 0 8px 60px;font-size:.92rem;line-height:1.6; }
.bot-msg  { background:#f5f5f5;color:#111111;padding:12px 16px;border-radius:12px 12px 12px 2px;margin:8px 60px 8px 0;font-size:.92rem;line-height:1.6;border:1px solid #e8e8e8; }
.msg-label { font-size:.72rem;font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;color:#888; }
.user-label { color:#aaaaaa !important; }
.overview-card { background:#111111;color:#ffffff;border-radius:12px;padding:28px 32px;margin-bottom:24px; }
.overview-card h2 { font-size:1.3rem;font-weight:700;margin:0 0 6px;color:#ffffff; }
.overview-card .subtitle { font-size:.85rem;color:#999999;margin-bottom:20px; }
.stat-row { display:flex;gap:16px;flex-wrap:wrap;margin-top:16px; }
.stat-box { background:#1e1e1e;border:1px solid #333;border-radius:8px;padding:12px 18px;flex:1;min-width:100px; }
.stat-box .label { font-size:.7rem;color:#888;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px; }
.stat-box .value { font-size:1.2rem;font-weight:700;color:#ffffff; }
.section-header { display:flex;align-items:center;gap:10px;margin:28px 0 14px;padding-bottom:10px;border-bottom:2px solid #111111; }
.section-header .tag { background:#111111;color:#ffffff;font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 10px;border-radius:20px; }
.section-header h3 { font-size:1rem;font-weight:700;margin:0;color:#111111; }
.session-card { border:1px solid #e0e0e0;border-radius:10px;padding:18px 20px;margin-bottom:12px;background:#ffffff; }
.session-card .session-title { font-size:.95rem;font-weight:600;color:#111111;margin-bottom:6px; }
.session-card .session-meta { font-size:.78rem;color:#666666;margin-bottom:10px;display:flex;gap:12px; }
.session-card .badge { background:#f0f0f0;color:#333;font-size:.7rem;font-weight:600;padding:2px 8px;border-radius:4px; }
.session-card .duration-badge { background:#111111;color:#ffffff;font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:4px; }
.session-card .objective { font-size:.82rem;color:#444444;margin-bottom:8px;line-height:1.5; }
.session-card .activities { list-style:none;padding:0;margin:0; }
.session-card .activities li { font-size:.8rem;color:#555555;padding:3px 0;border-top:1px solid #f0f0f0;display:flex;align-items:flex-start;gap:8px; }
.session-card .activities li::before { content:"→";color:#999999;flex-shrink:0;margin-top:1px; }
.group-header-A { background:#111111;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;font-size:.8rem;font-weight:700; }
.group-header-B { background:#333333;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;font-size:.8rem;font-weight:700; }
.group-header-C { background:#555555;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;font-size:.8rem;font-weight:700; }
.time-bar-container { margin:16px 0;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden; }
.time-bar-row { display:flex;align-items:center;padding:10px 16px;font-size:.8rem;border-bottom:1px solid #f0f0f0; }
.time-bar-row:last-child { border-bottom:none; }
.time-bar-label { width:120px;color:#555;font-weight:500; }
.time-bar-track { flex:1;height:6px;background:#f0f0f0;border-radius:3px;margin:0 12px;overflow:hidden; }
.time-bar-fill { height:100%;background:#111111;border-radius:3px; }
.time-bar-val { color:#111;font-weight:700;min-width:40px;text-align:right; }
.outcome-item { display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0;font-size:.85rem;color:#333333; }
.outcome-item:last-child { border-bottom:none; }
.outcome-dot { width:6px;height:6px;background:#111111;border-radius:50%;flex-shrink:0;margin-top:6px; }
.stButton > button { background:#111111 !important;color:#ffffff !important;border:none !important;border-radius:8px !important;font-weight:600 !important;padding:10px 20px !important; }
.stButton > button:hover { background:#333333 !important; }
.main-title { font-size:1.5rem;font-weight:800;color:#111111;letter-spacing:-.02em;margin-bottom:2px; }
.main-subtitle { font-size:.85rem;color:#888888;margin-bottom:24px; }
.clean-divider { border:none;border-top:1px solid #eeeeee;margin:20px 0; }
.verify-ok   { background:#f0faf0;border:1px solid #cce5cc;color:#2d6a2d;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }
.verify-warn { background:#fff8f0;border:1px solid #f0d9b5;color:#7a4f00;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }

/* ── 생성 완료 배너 */
@keyframes slideDown {
  from { opacity:0; transform:translateY(-16px); }
  to   { opacity:1; transform:translateY(0); }
}
.done-banner {
  animation: slideDown .45s ease-out;
  background: linear-gradient(135deg, #0a0a0a 0%, #1f1f1f 100%);
  color: #fff;
  border-radius: 12px;
  padding: 20px 28px;
  margin-bottom: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
}
.done-banner .done-icon {
  font-size: 2rem;
  line-height: 1;
  flex-shrink: 0;
}
.done-banner .done-title {
  font-size: 1.05rem;
  font-weight: 700;
  margin-bottom: 3px;
}
.done-banner .done-sub {
  font-size: .78rem;
  color: #aaa;
}

/* ── RAG 참고 자료 패널 */
.rag-panel-header {
  display:flex; align-items:center; gap:10px;
  margin: 28px 0 14px; padding-bottom:10px;
  border-bottom: 2px solid #e0e0e0;
}
.rag-panel-header .rag-tag {
  background:#e8f4fd; color:#1a6fa8;
  font-size:.68rem; font-weight:700;
  letter-spacing:.1em; text-transform:uppercase;
  padding:3px 10px; border-radius:20px;
}
.rag-panel-header h3 { font-size:1rem;font-weight:700;margin:0;color:#333; }
.rag-chunk {
  border:1px solid #e0e0e0; border-radius:10px;
  margin-bottom:10px; overflow:hidden;
}
.rag-chunk-header {
  background:#f4f8fd; padding:10px 14px;
  display:flex; align-items:center; gap:10px;
  border-bottom:1px solid #e0e0e0;
}
.rag-chunk-header .rag-rank {
  background:#1a6fa8; color:#fff;
  font-size:.68rem; font-weight:700;
  padding:2px 8px; border-radius:20px; flex-shrink:0;
}
.rag-chunk-header .rag-source { font-size:.82rem;font-weight:700;color:#111; }
.rag-chunk-header .rag-meta   { font-size:.74rem;color:#666;margin-left:auto; }
.rag-chunk-header .rag-dist   { font-size:.72rem;color:#1a6fa8;font-weight:700; }

/* retrieval method 배지 */
.badge-semantic { background:#e8f4fd;color:#1a6fa8;font-size:.65rem;font-weight:700;padding:2px 7px;border-radius:10px;letter-spacing:.04em; }
.badge-bm25     { background:#fff3e0;color:#e65100;font-size:.65rem;font-weight:700;padding:2px 7px;border-radius:10px;letter-spacing:.04em; }
.badge-both     { background:#f3e8fd;color:#6a1a8f;font-size:.65rem;font-weight:700;padding:2px 7px;border-radius:10px;letter-spacing:.04em; }

/* 맥락 설명 영역 */
.ctx-desc {
  background:#f0f7ff; border-left:3px solid #1a6fa8;
  padding:8px 12px; font-size:.78rem; color:#2c4a6e;
  line-height:1.6; margin:0;
}
.ctx-label {
  font-size:.65rem; font-weight:700; color:#1a6fa8;
  text-transform:uppercase; letter-spacing:.08em;
  margin-bottom:4px;
}
.rag-chunk-body {
  padding:12px 14px; font-size:.8rem; color:#444;
  line-height:1.65; background:#fff;
  white-space:pre-wrap; word-break:break-word;
}
.rag-empty {
  text-align:center; padding:28px; color:#aaa;
  border:1px dashed #ddd; border-radius:10px;
  font-size:.85rem;
}

/* 리랭킹 점수 바 */
.rerank-bar-wrap {
  display:flex; align-items:center; gap:8px;
  padding:6px 14px; background:#fff8f0;
  border-bottom:1px solid #ffe0b2;
}
.rerank-bar-label {
  font-size:.65rem; font-weight:700; color:#e65100;
  text-transform:uppercase; letter-spacing:.06em;
  white-space:nowrap; flex-shrink:0;
}
.rerank-bar-track {
  flex:1; height:5px; background:#ffe0b2; border-radius:3px; overflow:hidden;
}
.rerank-bar-fill { height:100%; border-radius:3px; background:#e65100; }
.rerank-bar-val {
  font-size:.7rem; font-weight:700; color:#e65100;
  min-width:32px; text-align:right; flex-shrink:0;
}
</style>
"""

LOGIN_CSS = """
<style>
.login-wrap { max-width:380px;margin:80px auto 0;padding:40px 36px 36px;border:1px solid #e0e0e0;border-radius:16px;background:#fff; }
.login-logo { font-size:2rem;font-weight:900;letter-spacing:-.04em;color:#111;text-align:center;margin-bottom:4px; }
.login-sub  { font-size:.82rem;color:#888;text-align:center;margin-bottom:28px; }
.login-err  { background:#fff0f0;border:1px solid #ffcccc;color:#cc0000;border-radius:8px;padding:10px 14px;font-size:.82rem;margin-bottom:12px;text-align:center; }
</style>
"""


# ── 로그인 페이지 ──────────────────────────────────────────────────────────────
def show_login_page():
    st.set_page_config(page_title="AX 교육 커리큘럼 — 로그인", page_icon="◈", layout="centered")
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="login-wrap">
        <div class="login-logo">◈ AX Curriculum v2</div>
        <div class="login-sub">고도화된 RAG 인덱싱 기반 교육 설계</div>
    </div>""", unsafe_allow_html=True)

    with st.form("login_form"):
        st.markdown("#### 로그인")
        username = st.text_input("아이디", placeholder="아이디를 입력하세요")
        password = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인", use_container_width=True)

    if submitted:
        if do_login(username.strip(), password):
            st.rerun()
        else:
            st.markdown('<div class="login-err">아이디 또는 비밀번호가 올바르지 않습니다.</div>',
                        unsafe_allow_html=True)


# ── RAG 쿼리 헬퍼 ─────────────────────────────────────────────────────────────
def rag_query(
    indexer: AdvancedRAGIndexer, ax_types: list[str], audience: str, constraints: str
) -> tuple[str, list[dict]]:
    """(LLM용 컨텍스트 문자열, 화면 표시용 raw hit 목록) 반환."""
    query_text = f"AX Compass 유형: {', '.join(ax_types)}. 교육 대상: {audience}. 조건: {constraints}"
    hits = indexer.query(query_text, k=5)
    if not hits:
        return "", []
    parts = []
    for h in hits:
        if not h or not h.get("text"):
            continue
        meta    = h.get("metadata") or {}
        src     = meta.get("source", "")
        section = meta.get("section", "")
        page    = meta.get("page", "")
        label   = f"{src}" + (f" p.{page}" if page else "") + (f" [{section}]" if section else "")
        parts.append(f"[{label}]\n{h['text'][:400]}")
    return "\n\n---\n\n".join(parts), hits


def build_curriculum_prompt(chat_summary: str, ax_counts: dict, rag_ctx: str) -> str:
    active_groups = {
        grp: {"types": types, "count": sum(ax_counts.get(t, 0) for t in types)}
        for grp, types in GROUPS.items()
        if sum(ax_counts.get(t, 0) for t in types) > 0
    }
    group_str = "\n".join(
        f"  그룹{k}: {', '.join(v['types'])} ({v['count']}명)"
        for k, v in active_groups.items()
    )
    inactive = [k for k in GROUPS if k not in active_groups]
    return f"""다음 정보를 바탕으로 커리큘럼 JSON을 생성하세요.

## 교육 정보
{chat_summary}

## AX Compass 인원 분포
{group_str}
{'제외 그룹(0명): 그룹' + ', 그룹'.join(inactive) if inactive else ''}

## RAG 참고 자료
{rag_ctx if rag_ctx else '(없음 — LLM 지식 활용)'}

반드시 유효한 JSON만 출력하세요."""


# ── 커리큘럼 시각화 ────────────────────────────────────────────────────────────
def render_curriculum(data: dict):
    ov = data.get("overview", {})
    total_h   = ov.get("total_hours", 0)
    theory    = data.get("theory_sessions", [])
    practice  = data.get("practice_sessions", {})
    theory_total   = sum(s.get("duration_hours", 0) for s in theory)
    active_practice = {k: v for k, v in practice.items() if v}
    practice_totals = {k: sum(s.get("duration_hours", 0) for s in v) for k, v in active_practice.items()}

    st.markdown(f"""
    <div class="overview-card">
        <div style="font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:#666;margin-bottom:6px;">AX 교육 커리큘럼 v2</div>
        <h2>{ov.get('company','')} · {ov.get('department','')}</h2>
        <div class="subtitle">{ov.get('audience','')}</div>
        <div style="font-size:.8rem;color:#aaa;margin-bottom:8px;">{'  ·  '.join(ov.get('topics',[]))}</div>
        <div class="stat-row">
            <div class="stat-box"><div class="label">총 시간</div><div class="value">{total_h}h</div></div>
            <div class="stat-box"><div class="label">교육 일수</div><div class="value">{ov.get('days','')}일</div></div>
            <div class="stat-box"><div class="label">일 시간</div><div class="value">{ov.get('hours_per_day','')}h</div></div>
            <div class="stat-box"><div class="label">난이도</div><div class="value" style="font-size:1rem;">{ov.get('difficulty','')}</div></div>
            <div class="stat-box"><div class="label">참여 그룹</div><div class="value">{len(active_practice)}개</div></div>
        </div>
    </div>""", unsafe_allow_html=True)

    # 시간 배분
    if total_h > 0:
        theory_pct  = int(theory_total / total_h * 100)
        practice_h  = list(practice_totals.values())[0] if practice_totals else 0
        practice_pct = int(practice_h / total_h * 100)
        st.markdown("""<div class="section-header"><span class="tag">시간 배분</span><h3>이론 vs 실습</h3></div>""",
                    unsafe_allow_html=True)
        st.markdown(f"""
        <div class="time-bar-container">
            <div class="time-bar-row">
                <div class="time-bar-label">공통 이론</div>
                <div class="time-bar-track"><div class="time-bar-fill" style="width:{theory_pct}%"></div></div>
                <div class="time-bar-val">{theory_total}h</div>
            </div>
            <div class="time-bar-row">
                <div class="time-bar-label">그룹 실습</div>
                <div class="time-bar-track"><div class="time-bar-fill" style="width:{practice_pct}%"></div></div>
                <div class="time-bar-val">{practice_h}h</div>
            </div>
        </div>""", unsafe_allow_html=True)

    # 이론 세션
    st.markdown("""<div class="section-header"><span class="tag">공통</span><h3>이론 세션 (전원 참여)</h3></div>""",
                unsafe_allow_html=True)
    for s in theory:
        acts_html = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
        concepts  = "  ".join(f'<span class="badge">{c}</span>' for c in s.get("key_concepts", []))
        st.markdown(f"""
        <div class="session-card">
            <div class="session-title">세션 {s.get('order','')} · {s.get('title','')}</div>
            <div class="session-meta"><span class="duration-badge">{s.get('duration_hours',0)}h</span> {concepts}</div>
            <div class="objective">{s.get('objective','')}</div>
            <ul class="activities">{acts_html}</ul>
        </div>""", unsafe_allow_html=True)

    # 그룹별 실습
    if active_practice:
        st.markdown("""<div class="section-header"><span class="tag">그룹별</span><h3>맞춤형 실습 세션 (동시 진행)</h3></div>""",
                    unsafe_allow_html=True)
        cols = st.columns(len(active_practice))
        grp_styles = {"A": "group-header-A", "B": "group-header-B", "C": "group-header-C"}
        for col, (grp, sessions) in zip(cols, active_practice.items()):
            with col:
                types_str = " · ".join(GROUPS.get(grp, []))
                grp_h  = practice_totals.get(grp, 0)
                style  = grp_styles.get(grp, "group-header-A")
                st.markdown(f"""
                <div class="{style}">그룹 {grp} · {grp_h}h<br>
                    <span style="font-weight:400;font-size:.72rem;opacity:.8">{types_str}</span>
                </div>""", unsafe_allow_html=True)
                for s in sessions:
                    acts_html = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
                    st.markdown(f"""
                    <div class="session-card" style="border-radius:0 0 10px 10px;margin-top:0;border-top:none;">
                        <div class="session-title">{s.get('title','')}</div>
                        <div class="session-meta"><span class="duration-badge">{s.get('duration_hours',0)}h</span></div>
                        <div class="objective">{s.get('objective','')}</div>
                        <div style="font-size:.75rem;color:#888;margin-bottom:6px;font-style:italic">{s.get('ax_type_rationale','')}</div>
                        <ul class="activities">{acts_html}</ul>
                    </div>""", unsafe_allow_html=True)

    # 기대효과 + 사전학습
    outcomes = data.get("expected_outcomes", [])
    prereqs  = data.get("prerequisites", [])
    if outcomes or prereqs:
        c1, c2 = st.columns(2)
        with c1:
            if outcomes:
                st.markdown("""<div class="section-header"><span class="tag">효과</span><h3>교육 후 기대 효과</h3></div>""",
                            unsafe_allow_html=True)
                items = "".join(f'<div class="outcome-item"><div class="outcome-dot"></div>{o}</div>' for o in outcomes)
                st.markdown(f'<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px">{items}</div>',
                            unsafe_allow_html=True)
        with c2:
            if prereqs:
                st.markdown("""<div class="section-header"><span class="tag">준비</span><h3>추천 사전 학습</h3></div>""",
                            unsafe_allow_html=True)
                items = "".join(f'<div class="outcome-item"><div class="outcome-dot" style="background:#999"></div>{p}</div>' for p in prereqs)
                st.markdown(f'<div style="border:1px solid #e0e0e0;border-radius:8px;padding:12px 16px">{items}</div>',
                            unsafe_allow_html=True)

    # 시간 검증
    st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)
    prac_list = list(practice_totals.values())
    if prac_list:
        grp_h  = prac_list[0]
        calc   = theory_total + grp_h
        ok     = abs(calc - total_h) < 0.1
        uniq_ok = len({round(h, 1) for h in prac_list}) == 1
        v1, v2 = ("verify-ok" if ok else "verify-warn"), ("verify-ok" if uniq_ok else "verify-warn")
        st.markdown(f"""
        <span class="{v1}">{'✓' if ok else '⚠'} 총 시간: 이론 {theory_total}h + 실습 {grp_h}h = {calc}h / 목표 {total_h}h</span>
        &nbsp;
        <span class="{v2}">{'✓' if uniq_ok else '⚠'} 그룹별 실습 시간: {list(practice_totals.values())}</span>
        """, unsafe_allow_html=True)


# ── 앱 메인 ───────────────────────────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="AX 교육 커리큘럼 v2",
        page_icon="◈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # 세션 초기화
    defaults = {
        "messages": [{"role": "assistant", "content":
            "안녕하세요! AX 교육 커리큘럼 설계 챗봇 v2입니다.\n\n"
            "몇 가지 항목을 순서대로 입력하시면 맞춤형 커리큘럼을 설계해드립니다.\n\n"
            + STEPS[0]["question"] + f"\n\n*{STEPS[0]['hint']}*"}],
        "curriculum": None,
        "indexer": None,
        "index_report": None,
        "rag_hits": [],
        "just_completed": False,
        "rerank_enabled": True,
        "phase": STEP_PHASES[0],
        "ax_counts": {},
        "edu_info": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

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
        st.markdown("### RAG 인덱싱")

        if api_key:
            # ── 컬렉션 현황 (세션 복구: indexer 없으면 stats 조회용으로 초기화)
            indexer_obj = st.session_state.get("indexer")
            if indexer_obj is None:
                try:
                    indexer_obj = AdvancedRAGIndexer(
                        api_key=api_key,
                        chroma_dir=CHROMA_DIR,
                        data_dir=DATA_DIR,
                        rerank=st.session_state.get("rerank_enabled", True),
                    )
                    st.session_state.indexer = indexer_obj
                except Exception:
                    indexer_obj = None
            stats = indexer_obj.collection_stats() if indexer_obj else {}
            total_chunks = sum(stats.values())

            if total_chunks == 0:
                st.markdown(
                    "<small style='color:#ff6b35;'>⚠ 컬렉션이 비어 있습니다.<br>"
                    "아래 버튼으로 인덱싱을 실행하세요.</small>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<small>" +
                    "  ".join(f"<b>{dt}</b>: {cnt}청크" for dt, cnt in stats.items()) +
                    "</small>",
                    unsafe_allow_html=True,
                )

            st.markdown("")
            rerank_enabled = st.checkbox(
                "리랭킹 활성화 (LLM Reranker)",
                value=st.session_state.get("rerank_enabled", True),
                help="RRF 병합 후 GPT-4o-mini 크로스-인코더로 최종 재정렬. 응답 품질 향상, 지연 소폭 증가.",
            )
            st.session_state.rerank_enabled = rerank_enabled

            col_force, col_idx = st.columns(2)
            with col_force:
                force = st.checkbox("전체 재인덱싱", value=False)
            with col_idx:
                if st.button("인덱싱 실행", use_container_width=True):
                    with st.spinner("Contextual Enrichment + BM25 인덱싱 중...\n(청크당 LLM 호출 — 잠시 기다려 주세요)"):
                        new_indexer = AdvancedRAGIndexer(
                            api_key=api_key,
                            chroma_dir=CHROMA_DIR,
                            data_dir=DATA_DIR,
                            rerank=rerank_enabled,
                        )
                        report = new_indexer.index_directory(force=force)
                        st.session_state.indexer      = new_indexer
                        st.session_state.index_report = report
                    st.rerun()

            if st.session_state.index_report:
                rpt = st.session_state.index_report
                color = "#2d6a2d" if not rpt.errors else "#7a4f00"
                st.markdown(f"""
                <small style='color:{color}'>
                ✓ 신규 <b>{rpt.indexed}</b>청크 &nbsp;|&nbsp;
                스킵 <b>{rpt.skipped}</b>건 &nbsp;|&nbsp;
                삭제 <b>{rpt.removed}</b>청크
                </small>""", unsafe_allow_html=True)
                for e in rpt.errors:
                    st.warning(e)
        else:
            st.markdown("<small>API Key를 입력하면 인덱싱 버튼이 활성화됩니다.</small>",
                        unsafe_allow_html=True)

        st.markdown("---")
        if st.session_state.ax_counts:
            st.markdown("### AX Compass 현황")
            for grp, types in GROUPS.items():
                cnt = sum(st.session_state.ax_counts.get(t, 0) for t in types)
                bar = "█" * min(cnt, 10) + "░" * max(0, 10 - cnt)
                st.markdown(f"<small><b>그룹{grp}</b> {bar} {cnt}명</small>", unsafe_allow_html=True)

        st.markdown("---")
        if st.button("새 대화 시작", use_container_width=True):
            for k, v in defaults.items():
                st.session_state[k] = v if k not in ("indexer", "index_report") else st.session_state[k]
            st.session_state.messages = [{"role": "assistant", "content":
                "새 커리큘럼 설계를 시작합니다.\n\n"
                + STEPS[0]["question"] + f"\n\n*{STEPS[0]['hint']}*"}]
            st.session_state.curriculum = None
            st.session_state.phase      = STEP_PHASES[0]
            st.session_state.ax_counts  = {}
            st.session_state.edu_info   = {}
            st.rerun()

        st.markdown("---")
        user   = st.session_state.get("auth_user", "")
        expiry = st.session_state.get("auth_expiry", 0)
        remain = max(0, int((expiry - time.time()) / 60))
        st.markdown(f"<small>👤 <b>{user}</b> · 세션 {remain}분 남음</small>", unsafe_allow_html=True)
        if st.button("로그아웃", use_container_width=True):
            do_logout()
            st.rerun()

    # ── 메인 영역
    if not api_key:
        st.markdown('<div class="main-title">◈ AX 교육 커리큘럼 설계 v2</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">사이드바에서 OpenAI API Key를 입력해주세요.</div>',
                    unsafe_allow_html=True)
        return

    client = OpenAI(api_key=api_key)

    # 인덱서 객체 초기화 (처음 로드 시 — index_directory 는 사이드바 버튼으로만 실행)
    if st.session_state.indexer is None:
        indexer = AdvancedRAGIndexer(
            api_key=api_key,
            chroma_dir=CHROMA_DIR,
            data_dir=DATA_DIR,
            rerank=st.session_state.get("rerank_enabled", True),
        )
        st.session_state.indexer = indexer

    tab_chat, tab_result = st.tabs(["💬 대화", "📋 커리큘럼"])

    with tab_chat:
        st.markdown('<div class="main-title">◈ AX 교육 커리큘럼 설계 v2</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">구조 인식 RAG + 증분 인덱싱 기반 커리큘럼 설계</div>',
                    unsafe_allow_html=True)

        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(f'<div class="msg-label user-label">나</div><div class="user-msg">{msg["content"]}</div>',
                            unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="msg-label">챗봇</div><div class="bot-msg">{msg["content"]}</div>',
                            unsafe_allow_html=True)

        if st.session_state.phase == "ready":
            info      = st.session_state.edu_info
            ax_counts = st.session_state.ax_counts

            with st.expander("📋 입력 정보 확인", expanded=False):
                st.json({**info, "ax_counts": ax_counts})

            if st.button("🎯 커리큘럼 생성", type="primary"):
                status = st.status("커리큘럼 생성 중...", expanded=True)
                try:
                    with status:
                        st.write("① RAG 검색 중...")
                        rag_ctx, raw_hits = "", []
                        indexer = st.session_state.indexer
                        if indexer and indexer.available:
                            active_types = [t for grp, types in GROUPS.items()
                                            for t in types if ax_counts.get(t, 0) > 0]
                            rag_ctx, raw_hits = rag_query(
                                indexer, active_types,
                                info.get("audience", ""),
                                info.get("constraints", ""),
                            )

                        st.write("② GPT-4o 커리큘럼 생성 중...")
                        chat_summary = "\n".join(f"{k}: {v}" for k, v in info.items())
                        prompt = build_curriculum_prompt(chat_summary, ax_counts, rag_ctx)

                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {"role": "system", "content": CURRICULUM_SYSTEM_PROMPT},
                                {"role": "user",   "content": prompt},
                            ],
                            temperature=0.6,
                            response_format={"type": "json_object"},
                        )
                        st.session_state.curriculum     = json.loads(response.choices[0].message.content)
                        st.session_state.rag_hits       = raw_hits
                        st.session_state.just_completed = True
                        status.update(label="✅ 생성 완료!", state="complete")
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ 오류 발생", state="error")
                    st.error(f"오류 내용: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        # 사용자 입력
        phase = st.session_state.phase
        if phase in AX_STEP_PHASES:
            placeholder = "0 이상 정수 입력 (해당 없으면 0)"
        elif phase == "ready":
            placeholder = "커리큘럼 생성 버튼을 눌러주세요."
        else:
            current_step = next((s for s in STEPS if s["phase"] == phase), None)
            placeholder  = current_step["hint"] if current_step else "입력해주세요..."

        if user_input := st.chat_input(placeholder, disabled=(phase == "ready")):
            st.session_state.messages.append({"role": "user", "content": user_input})
            reply = ""

            if phase in AX_STEP_PHASES:
                ax_step = next(s for s in AX_STEPS if s["phase"] == phase)
                try:
                    n = int(user_input.strip())
                    if n < 0:
                        raise ValueError("음수 불가")
                    st.session_state.ax_counts[ax_step["type"]] = n
                    next_idx = ax_step["order"] + 1
                    if next_idx < len(AX_STEPS):
                        nxt = AX_STEPS[next_idx]
                        st.session_state.phase = nxt["phase"]
                        reply = f"**{nxt['type']}** (그룹 {GROUP_DESC[nxt['type']]}) 인원수를 입력해주세요.\n\n*0 이상 정수, 해당 없으면 0*"
                    else:
                        counts = st.session_state.ax_counts
                        total  = sum(counts.values())
                        grp_lines = "\n".join(
                            f"- 그룹{g} ({' · '.join(t)}): {sum(counts.get(tp,0) for tp in t)}명"
                            for g, t in GROUPS.items()
                        )
                        reply = f"✅ AX Compass 입력 완료! 총 **{total}명**\n\n{grp_lines}\n\n아래 **커리큘럼 생성** 버튼을 눌러주세요."
                        st.session_state.phase = "ready"
                except ValueError as e:
                    reply = f"숫자(0 이상 정수)로 입력해주세요. 오류: {e}"
            else:
                step = next((s for s in STEPS if s["phase"] == phase), None)
                if step:
                    try:
                        val = step["cast"](user_input.strip())
                    except (ValueError, TypeError):
                        reply = step.get("error", "다시 입력해주세요.")
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                        st.rerun()

                    st.session_state.edu_info[step["key"]] = val
                    cur_idx  = STEP_PHASES.index(phase)
                    next_idx = cur_idx + 1

                    if next_idx < len(STEPS):
                        nxt   = STEPS[next_idx]
                        st.session_state.phase = nxt["phase"]
                        reply = nxt["question"] + f"\n\n*{nxt['hint']}*"
                    else:
                        info    = st.session_state.edu_info
                        total_h = info.get("days", 0) * info.get("hours_per_day", 0)
                        first_ax = AX_STEPS[0]
                        st.session_state.phase = first_ax["phase"]
                        reply = (
                            f"✅ 기본 정보 입력 완료!\n\n"
                            f"| 항목 | 내용 |\n|------|------|\n"
                            f"| 회사 | {info.get('company','')} |\n"
                            f"| 교육 대상자 | {info.get('audience','')} |\n"
                            f"| AI 경험 | {info.get('ai_experience','')} |\n"
                            f"| 조건/제한 | {info.get('constraints','')} |\n"
                            f"| 목표 | {info.get('goal','')} |\n"
                            f"| 일정 | {info.get('days','')}일 × {info.get('hours_per_day','')}h = 총 {total_h}h |\n\n"
                            f"---\n이제 **AX Compass 유형별 인원수**를 하나씩 입력해주세요.\n\n"
                            f"**{first_ax['type']}** (그룹 {GROUP_DESC[first_ax['type']]}) 인원수를 입력해주세요.\n\n"
                            f"*0 이상 정수, 해당 없으면 0*"
                        )

            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()

    with tab_result:
        if st.session_state.curriculum:
            # ── 완료 이펙트 (최초 생성 직후 1회)
            if st.session_state.just_completed:
                st.balloons()
                company = st.session_state.curriculum.get("overview", {}).get("company", "")
                total_h = st.session_state.curriculum.get("overview", {}).get("total_hours", "")
                rag_cnt = len(st.session_state.rag_hits)
                st.markdown(f"""
                <div class="done-banner">
                    <div class="done-icon">✅</div>
                    <div>
                        <div class="done-title">커리큘럼 생성 완료</div>
                        <div class="done-sub">
                            {company} &nbsp;·&nbsp; 총 {total_h}h &nbsp;·&nbsp;
                            RAG 참고 {rag_cnt}청크 적용
                        </div>
                    </div>
                </div>""", unsafe_allow_html=True)
                st.session_state.just_completed = False

            render_curriculum(st.session_state.curriculum)

            # ── RAG 참고 자료 패널 ──────────────────────────────────────────
            hits = st.session_state.get("rag_hits", [])

            retrieval_counts = {"semantic": 0, "bm25": 0, "both": 0}
            for h in hits:
                retrieval_counts[h.get("retrieval", "semantic")] += 1

            rerank_active = st.session_state.get("rerank_enabled", True)
            pipeline_label = (
                "Contextual Embedding + BM25 + RRF → LLM Reranker"
                if rerank_active else
                "Contextual Embedding + BM25 + RRF"
            )
            st.markdown(f"""
            <div class="rag-panel-header">
                <span class="rag-tag">Hybrid RAG</span>
                <div>
                    <h3 style="margin:0 0 2px;">커리큘럼 생성에 사용된 참고 자료</h3>
                    <div style="font-size:.68rem;color:#888;">{pipeline_label}</div>
                </div>
                <span style="margin-left:auto;font-size:.75rem;color:#555;">
                    총 {len(hits)}청크
                    &nbsp;·&nbsp;
                    <span class="badge-both">BOTH {retrieval_counts['both']}</span>
                    &nbsp;
                    <span class="badge-semantic">SEMANTIC {retrieval_counts['semantic']}</span>
                    &nbsp;
                    <span class="badge-bm25">BM25 {retrieval_counts['bm25']}</span>
                </span>
            </div>""", unsafe_allow_html=True)

            if hits:
                for i, h in enumerate(hits, 1):
                    meta      = h["metadata"]
                    src       = meta.get("source", "알 수 없음")
                    doc_type  = meta.get("doc_type", "")
                    section   = meta.get("section", "")
                    page      = meta.get("page", "")
                    sheet     = meta.get("sheet", "")
                    chunk_i   = meta.get("chunk_index", "")
                    total_c   = meta.get("total_chunks", "")
                    ctx_desc  = meta.get("context_desc", "")
                    retrieval    = h.get("retrieval", "semantic")
                    rrf_score    = h.get("rrf_score", 0.0)
                    rerank_score = h.get("rerank_score")
                    distance     = h.get("distance", 1.0)

                    type_icon = "📄" if doc_type == "pdf" else "📊"
                    meta_parts = []
                    if page:
                        meta_parts.append(f"p.{page}")
                    if sheet:
                        meta_parts.append(f"시트: {sheet}")
                    if section:
                        meta_parts.append(f"섹션: {section}")
                    if chunk_i != "":
                        meta_parts.append(f"청크 {chunk_i}/{total_c}")
                    meta_str = "  ·  ".join(meta_parts) if meta_parts else "—"

                    badge_class = f"badge-{retrieval}"
                    badge_label = {"semantic": "SEMANTIC", "bm25": "BM25", "both": "BOTH"}.get(retrieval, retrieval.upper())

                    # 본문 미리보기: 맥락 설명 이후 원본 텍스트만 표시
                    raw_text = h["text"]
                    if ctx_desc and raw_text.startswith(ctx_desc):
                        raw_text = raw_text[len(ctx_desc):].lstrip()
                    preview = raw_text.replace("<", "&lt;").replace(">", "&gt;")
                    preview = preview[:280] + ("..." if len(raw_text) > 280 else "")

                    ctx_html = ""
                    if ctx_desc:
                        ctx_safe = ctx_desc.replace("<", "&lt;").replace(">", "&gt;")
                        ctx_html = f"""
                        <div style="padding:10px 14px;background:#f0f7ff;border-bottom:1px solid #d0e6f8;">
                            <div class="ctx-label">Contextual Description</div>
                            <div class="ctx-desc">{ctx_safe}</div>
                        </div>"""

                    score_str = f"RRF {rrf_score:.4f}" if rrf_score else f"유사도 {1 - distance:.3f}"

                    rerank_html = ""
                    if rerank_score is not None:
                        pct = int(rerank_score * 100)
                        rerank_html = f"""
                        <div class="rerank-bar-wrap">
                            <span class="rerank-bar-label">Reranker</span>
                            <div class="rerank-bar-track">
                                <div class="rerank-bar-fill" style="width:{pct}%"></div>
                            </div>
                            <span class="rerank-bar-val">{pct}</span>
                        </div>"""

                    st.markdown(f"""
                    <div class="rag-chunk">
                        <div class="rag-chunk-header">
                            <span class="rag-rank">#{i}</span>
                            <span class="{badge_class}">{badge_label}</span>
                            <span class="rag-source">{type_icon} {src}</span>
                            <span class="rag-meta">{meta_str}</span>
                            <span class="rag-dist">{score_str}</span>
                        </div>
                        {ctx_html}
                        {rerank_html}
                        <div class="rag-chunk-body">{preview}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown("""
                <div class="rag-empty">
                    RAG 참고 자료 없음 — LLM 자체 지식으로 생성됨<br>
                    <small>Data/ 폴더에 PDF 또는 Excel 파일을 넣고 인덱싱 후 재생성하면 참고 자료가 표시됩니다.</small>
                </div>""", unsafe_allow_html=True)

            # ── JSON 다운로드
            st.markdown("<hr class='clean-divider'>", unsafe_allow_html=True)
            col1, _ = st.columns([1, 4])
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
                <div style="font-size:.85rem;margin-top:8px">💬 대화 탭에서 정보를 입력하고 커리큘럼을 생성해주세요.</div>
            </div>""", unsafe_allow_html=True)


if __name__ == "__main__":
    if not is_authenticated():
        show_login_page()
    else:
        main()
