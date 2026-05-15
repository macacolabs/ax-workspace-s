"""
AX Single Agent — Streamlit 프론트엔드
======================================
CurriculumAgent를 직접 임포트해 독립 실행 (FastAPI 불필요).
Streamlit Cloud 배포 대응.
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

_BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BASE / "07_SingleAgent"))
sys.path.insert(0, str(_BASE / "05_Advanced_RAG_indexing_contextual"))

load_dotenv(_BASE / ".env")

# ── 인증 ──────────────────────────────────────────────────────────────────────
TOKEN_TTL = 8 * 3600
USERS = {"admin": hashlib.sha256("admin".encode()).hexdigest()}


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def is_authenticated() -> bool:
    return bool(st.session_state.get("auth_token")) and time.time() < st.session_state.get("auth_expiry", 0)


def do_login(username: str, password: str) -> bool:
    if USERS.get(username) == _hash(password):
        st.session_state.auth_token = secrets.token_hex(32)
        st.session_state.auth_expiry = time.time() + TOKEN_TTL
        st.session_state.auth_user = username
        return True
    return False


def do_logout():
    for k in ("auth_token", "auth_expiry", "auth_user"):
        st.session_state.pop(k, None)


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
.tool-call { background:#fff8e1;border:1px solid #ffe082;border-radius:8px;padding:8px 12px;margin:6px 60px 6px 0;font-size:.78rem;color:#5d4037; }
.tool-label { font-size:.65rem;font-weight:700;color:#f57f17;text-transform:uppercase;letter-spacing:.08em;margin-bottom:3px; }
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
.done-banner { background:linear-gradient(135deg,#0a0a0a 0%,#1f1f1f 100%);color:#fff;border-radius:12px;padding:20px 28px;margin-bottom:24px;display:flex;align-items:center;gap:16px; }
.done-banner .done-icon { font-size:2rem;line-height:1;flex-shrink:0; }
.done-banner .done-title { font-size:1.05rem;font-weight:700;margin-bottom:3px; }
.done-banner .done-sub { font-size:.78rem;color:#aaa; }
.verify-ok   { background:#f0faf0;border:1px solid #cce5cc;color:#2d6a2d;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }
.verify-warn { background:#fff8f0;border:1px solid #f0d9b5;color:#7a4f00;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }
.outcome-item { display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0;font-size:.85rem;color:#333333; }
.outcome-item:last-child { border-bottom:none; }
.outcome-dot { width:6px;height:6px;background:#111111;border-radius:50%;flex-shrink:0;margin-top:6px; }
.stButton > button { background:#111111 !important;color:#ffffff !important;border:none !important;border-radius:8px !important;font-weight:600 !important;padding:10px 20px !important; }
.stButton > button:hover { background:#333333 !important; }
.main-title { font-size:1.5rem;font-weight:800;color:#111111;letter-spacing:-.02em;margin-bottom:2px; }
.main-subtitle { font-size:.85rem;color:#888888;margin-bottom:24px; }
.clean-divider { border:none;border-top:1px solid #eeeeee;margin:20px 0; }
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


# ── 로그인 페이지 ────────────────────────────────────────────────────────────
def show_login_page():
    st.set_page_config(page_title="AX Single Agent — 로그인", page_icon="◈", layout="centered")
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="login-wrap">
        <div class="login-logo">◈ AX Agent v1</div>
        <div class="login-sub">Single Agent 기반 AI 교육 커리큘럼 설계</div>
    </div>""", unsafe_allow_html=True)

    with st.form("login_form"):
        st.markdown("#### 로그인")
        username = st.text_input("아이디", placeholder="admin")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인", use_container_width=True)

    if submitted:
        if do_login(username, password):
            st.rerun()
        else:
            st.markdown('<div class="login-err">아이디 또는 비밀번호가 올바르지 않습니다.</div>', unsafe_allow_html=True)


# ── 에이전트 초기화 ──────────────────────────────────────────────────────────
def get_agent():
    if "agent" not in st.session_state:
        try:
            try:
                _secrets = st.secrets
                api_key = _secrets.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
                tavily_key = _secrets.get("TAVILY_API_KEY", "") or os.environ.get("TAVILY_API_KEY", "")
            except Exception:
                api_key = os.environ.get("OPENAI_API_KEY", "")
                tavily_key = os.environ.get("TAVILY_API_KEY", "")
            chroma_dir = _BASE / "chroma_db"
            data_dir = _BASE / "Data"

            from agent.agent import CurriculumAgent
            agent = CurriculumAgent(
                api_key=api_key,
                chroma_dir=chroma_dir,
                data_dir=data_dir,
                tavily_api_key=tavily_key,
            )
            st.session_state.agent = agent
        except Exception as e:
            st.error(f"에이전트 초기화 실패: {e}")
            return None
    return st.session_state.agent


# ── 커리큘럼 렌더링 ──────────────────────────────────────────────────────────
def render_curriculum(curriculum: dict):
    ov = curriculum.get("overview", {})

    st.markdown(f"""
    <div class="overview-card">
        <h2>{ov.get('company','')}</h2>
        <div class="subtitle">{ov.get('department','')} | {ov.get('audience','')}</div>
        <div class="stat-row">
            <div class="stat-box"><div class="label">총 교육 시간</div><div class="value">{ov.get('total_hours',0)}h</div></div>
            <div class="stat-box"><div class="label">교육 일수</div><div class="value">{ov.get('days',0)}일</div></div>
            <div class="stat-box"><div class="label">일 교육 시간</div><div class="value">{ov.get('hours_per_day',0)}h</div></div>
            <div class="stat-box"><div class="label">난이도</div><div class="value">{ov.get('difficulty','')}</div></div>
        </div>
    </div>""", unsafe_allow_html=True)

    # 이론 세션
    theory = curriculum.get("theory_sessions", [])
    if theory:
        st.markdown("""<div class="section-header"><span class="tag">THEORY</span><h3>이론 세션</h3></div>""", unsafe_allow_html=True)
        for s in theory:
            acts = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
            concepts = " ".join(f'<span class="badge">{c}</span>' for c in s.get("key_concepts", []))
            st.markdown(f"""
            <div class="session-card">
                <div class="session-title">{s.get('order','')}.  {s.get('title','')}</div>
                <div class="session-meta">
                    <span class="duration-badge">{s.get('duration_hours',0)}h</span>
                    {concepts}
                </div>
                <div class="objective">{s.get('objective','')}</div>
                <ul class="activities">{acts}</ul>
            </div>""", unsafe_allow_html=True)

    # 실습 세션
    practice = curriculum.get("practice_sessions", {})
    if practice:
        st.markdown("""<div class="section-header"><span class="tag">PRACTICE</span><h3>그룹별 실습 세션</h3></div>""", unsafe_allow_html=True)
        for grp in ["그룹A", "그룹B", "그룹C"]:
            sessions = practice.get(grp, [])
            if not sessions:
                continue
            lbl = grp[-1]
            st.markdown(f'<div class="group-header-{lbl}">{grp}</div>', unsafe_allow_html=True)
            for s in sessions:
                acts = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
                rationale = s.get("ax_type_rationale", "")
                st.markdown(f"""
                <div class="session-card" style="border-radius:0 0 10px 10px;margin-top:0;border-top:none;">
                    <div class="session-title">{s.get('order','')}.  {s.get('title','')}</div>
                    <div class="session-meta"><span class="duration-badge">{s.get('duration_hours',0)}h</span></div>
                    <div class="objective">{s.get('objective','')}</div>
                    <ul class="activities">{acts}</ul>
                    {"<div style='font-size:.78rem;color:#888;margin-top:8px;'>💡 " + rationale + "</div>" if rationale else ""}
                </div>""", unsafe_allow_html=True)

    # 기대 성과
    outcomes = curriculum.get("expected_outcomes", [])
    if outcomes:
        st.markdown("""<div class="section-header"><span class="tag">OUTCOMES</span><h3>기대 성과</h3></div>""", unsafe_allow_html=True)
        items = "".join(f'<div class="outcome-item"><div class="outcome-dot"></div>{o}</div>' for o in outcomes)
        st.markdown(f'<div>{items}</div>', unsafe_allow_html=True)

    # 사전 조건
    prereqs = curriculum.get("prerequisites", [])
    if prereqs:
        st.markdown("""<div class="section-header"><span class="tag">PREREQS</span><h3>사전 조건</h3></div>""", unsafe_allow_html=True)
        items = "".join(f'<div class="outcome-item"><div class="outcome-dot"></div>{p}</div>' for p in prereqs)
        st.markdown(f'<div>{items}</div>', unsafe_allow_html=True)


# ── 검증 결과 렌더링 ─────────────────────────────────────────────────────────
def render_validation(validation: dict):
    if validation.get("passed"):
        st.markdown(f'<div class="verify-ok">✓ 검증 통과 — {validation.get("summary","")}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="verify-warn">⚠ 검증 실패 — {validation.get("summary","")}</div>', unsafe_allow_html=True)
        for f in validation.get("failures", []):
            st.markdown(f'<div class="verify-warn">✗ {f["rule"]}: {f["detail"]}</div>', unsafe_allow_html=True)


# ── 사이드바 ─────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("### ◈ AX Agent v1")
        st.markdown(f"**{st.session_state.get('auth_user','')}** 로그인 중")
        st.markdown("---")

        if st.button("새로 시작", use_container_width=True):
            _reset_wizard()
            st.rerun()

        st.markdown("---")

        try:
            _secrets = st.secrets
            api_key = _secrets.get("OPENAI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
            tavily_key = _secrets.get("TAVILY_API_KEY", "") or os.environ.get("TAVILY_API_KEY", "")
        except Exception:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            tavily_key = os.environ.get("TAVILY_API_KEY", "")

        if api_key:
            st.markdown('<span style="color:#4caf50;font-size:.8rem;">✓ OpenAI API 연결됨</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#f44336;font-size:.8rem;">✗ OPENAI_API_KEY 미설정</span>', unsafe_allow_html=True)

        if tavily_key:
            st.markdown('<span style="color:#4caf50;font-size:.8rem;">✓ Tavily 웹검색 연결됨</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span style="color:#888;font-size:.8rem;">○ Tavily 미설정 (선택)</span>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 사용 가이드")
        st.markdown("""
1. 회사명, 교육 대상자 정보 입력
2. AI 경험 수준, 제약 조건 입력
3. 교육 목표, 일수, 시간 입력
4. AX Compass 유형별 인원 입력
5. 에이전트가 자동으로 커리큘럼 생성
""")
        st.markdown("---")
        if st.button("로그아웃", use_container_width=True):
            do_logout()
            st.rerun()


# ── 채팅 히스토리 렌더링 ─────────────────────────────────────────────────────
# ── 단계별 입력 정의 ─────────────────────────────────────────────────────────
_STEPS = [
    {"key": "company",       "label": "회사명",          "hint": "예: 삼성전자",                            "type": "text",   "q": "1단계 / 8  —  교육을 진행할 **회사명**을 입력해주세요."},
    {"key": "audience",      "label": "교육 대상자",      "hint": "예: 비개발 직군 대리~차장, AI 경험 거의 없음",  "type": "text",   "q": "2단계 / 8  —  **교육 대상자**를 설명해주세요."},
    {"key": "ai_experience", "label": "AI 경험 수준",     "hint": "예: ChatGPT 가끔 사용해봄",               "type": "text",   "q": "3단계 / 8  —  교육 대상자의 **AI 경험 수준**을 입력해주세요."},
    {"key": "constraints",   "label": "제약 조건",        "hint": "예: ChatGPT만 사용 가능, 실습 위주 구성",   "type": "area",   "q": "4단계 / 8  —  꼭 반영해야 할 **조건 또는 제한 사항**을 입력해주세요."},
    {"key": "goal",          "label": "교육 목표",        "hint": "예: 업무 생산성 향상, AI 도구 활용 역량 강화", "type": "area",   "q": "5단계 / 8  —  **교육 목표**를 입력해주세요."},
    {"key": "days",          "label": "교육 일수",        "hint": "예: 2",                                  "type": "int",    "q": "6단계 / 8  —  **교육 일수**를 입력해주세요. (정수)"},
    {"key": "hours_per_day", "label": "일 교육 시간",     "hint": "예: 8",                                  "type": "float",  "q": "7단계 / 8  —  **일 교육 시간**을 입력해주세요. (시간)"},
    {"key": "ax_counts",     "label": "AX Compass 인원", "hint": "",                                       "type": "ax",     "q": "8단계 / 8  —  **AX Compass 유형별 인원수**를 입력해주세요."},
]
_AX_TYPES = ["균형형", "이해형", "과신형", "실행형", "판단형", "조심형"]
_TOTAL_STEPS = len(_STEPS)

TOOL_NAME_KO = {
    "rag_search": "RAG 검색",
    "web_search": "웹 검색",
    "generate_curriculum": "커리큘럼 생성",
    "validate_curriculum": "검증",
}


def _init_wizard_state():
    if "wizard_step" not in st.session_state:
        st.session_state.wizard_step = 0
    if "wizard_data" not in st.session_state:
        st.session_state.wizard_data = {}
    if "agent_log" not in st.session_state:
        st.session_state.agent_log = []
    if "final_curriculum" not in st.session_state:
        st.session_state.final_curriculum = None
    if "final_validation" not in st.session_state:
        st.session_state.final_validation = None
    if "generating" not in st.session_state:
        st.session_state.generating = False


def _reset_wizard():
    for k in ("wizard_step", "wizard_data", "agent_log", "final_curriculum",
              "final_validation", "generating", "agent"):
        st.session_state.pop(k, None)


def render_step_form():
    step_idx = st.session_state.wizard_step
    step = _STEPS[step_idx]

    # 진행률
    progress = step_idx / _TOTAL_STEPS
    st.progress(progress)
    st.markdown(f"<div style='font-size:.75rem;color:#888;margin:-8px 0 12px;'>진행률 {step_idx}/{_TOTAL_STEPS}</div>", unsafe_allow_html=True)

    # 질문
    st.markdown(f"#### {step['q']}")

    with st.form(f"step_form_{step_idx}", clear_on_submit=False):
        if step["type"] == "text":
            value = st.text_input(step["label"], placeholder=step["hint"],
                                  value=st.session_state.wizard_data.get(step["key"], ""))
        elif step["type"] == "area":
            value = st.text_area(step["label"], placeholder=step["hint"], height=80,
                                 value=st.session_state.wizard_data.get(step["key"], ""))
        elif step["type"] == "int":
            value = st.number_input(step["label"], min_value=1, max_value=30, step=1,
                                    value=int(st.session_state.wizard_data.get(step["key"], 1)))
        elif step["type"] == "float":
            value = st.number_input(step["label"], min_value=1.0, max_value=24.0, step=0.5,
                                    value=float(st.session_state.wizard_data.get(step["key"], 8.0)))
        elif step["type"] == "ax":
            existing = st.session_state.wizard_data.get("ax_counts", {})
            ax_vals = {}
            cols = st.columns(3)
            for i, t in enumerate(_AX_TYPES):
                with cols[i % 3]:
                    ax_vals[t] = st.number_input(t, min_value=0, max_value=200, step=1,
                                                  value=int(existing.get(t, 0)), key=f"ax_{t}")
            value = ax_vals

        col_prev, col_next = st.columns([1, 2])
        with col_prev:
            prev = st.form_submit_button("← 이전", use_container_width=True, disabled=(step_idx == 0))
        with col_next:
            next_label = "커리큘럼 생성 →" if step_idx == _TOTAL_STEPS - 1 else "다음 →"
            nxt = st.form_submit_button(next_label, use_container_width=True)

    if prev and step_idx > 0:
        st.session_state.wizard_step -= 1
        st.rerun()

    if nxt:
        # 유효성 확인
        if step["type"] in ("text", "area"):
            if not str(value).strip():
                st.warning("내용을 입력해주세요.")
                return
            st.session_state.wizard_data[step["key"]] = str(value).strip()
        elif step["type"] in ("int", "float"):
            st.session_state.wizard_data[step["key"]] = value
        elif step["type"] == "ax":
            if sum(value.values()) == 0:
                st.warning("최소 한 명 이상 입력해주세요.")
                return
            st.session_state.wizard_data["ax_counts"] = value

        if step_idx < _TOTAL_STEPS - 1:
            st.session_state.wizard_step += 1
            st.rerun()
        else:
            # 마지막 단계 → 생성 트리거
            st.session_state.generating = True
            st.rerun()


def render_data_summary():
    data = st.session_state.wizard_data
    if not data:
        return
    st.markdown("#### 입력 정보 요약")
    rows = []
    for s in _STEPS:
        k = s["key"]
        if k not in data:
            continue
        if k == "ax_counts":
            counts = data[k]
            total = sum(counts.values())
            rows.append(f"**인원**: 총 {total}명 / " + " · ".join(f"{t} {n}명" for t, n in counts.items() if n > 0))
        else:
            rows.append(f"**{s['label']}**: {data[k]}")
    for r in rows:
        st.markdown(f"<div style='font-size:.82rem;color:#444;padding:3px 0;border-bottom:1px solid #f0f0f0;'>{r}</div>", unsafe_allow_html=True)


def render_agent_log():
    log = st.session_state.get("agent_log", [])
    if not log:
        return
    st.markdown("#### 에이전트 진행 상황")
    for entry in log:
        if entry["type"] == "tool":
            name_ko = TOOL_NAME_KO.get(entry["name"], entry["name"])
            st.markdown(
                f'<div class="tool-call"><div class="tool-label">TOOL</div>'
                f'<b>{name_ko}</b> — {entry.get("desc","")}</div>',
                unsafe_allow_html=True,
            )
        elif entry["type"] == "reply":
            st.markdown(
                f'<div class="bot-msg"><div class="msg-label">AGENT</div>{entry["text"]}</div>',
                unsafe_allow_html=True,
            )


def run_agent_generation():
    """세션 상태에서 데이터 읽어 에이전트 실행. 결과/에러 모두 session_state에 저장."""
    data = st.session_state.wizard_data
    st.session_state.agent_error = None

    agent = get_agent()
    if agent is None:
        st.session_state.agent_error = "에이전트 초기화 실패: API 키를 확인하세요."
        st.session_state.generating = False
        return

    tool_calls_log: list[dict] = []

    def on_tool_call(name: str, args: dict):
        desc_map = {
            "rag_search": f"쿼리: {args.get('query','')[:50]}",
            "web_search": f"쿼리: {args.get('query','')[:50]}",
            "generate_curriculum": f"{data.get('company','')} / {data.get('days',0)}일 × {data.get('hours_per_day',0)}h",
            "validate_curriculum": "규칙 검증 중...",
        }
        tool_calls_log.append({"type": "tool", "name": name, "desc": desc_map.get(name, "")})

    agent._on_tool_call = on_tool_call

    ax_summary = "\n".join(f"  - {t}: {n}명" for t, n in data.get("ax_counts", {}).items())
    msg = f"""다음 요구사항으로 AX Compass 기반 교육 커리큘럼을 생성해주세요.

회사명: {data.get('company','')}
교육 대상자: {data.get('audience','')}
AI 경험 수준: {data.get('ai_experience','')}
제약 조건: {data.get('constraints','')}
교육 목표: {data.get('goal','')}
교육 일수: {data.get('days',0)}일
일 교육 시간: {data.get('hours_per_day',0)}시간

AX Compass 유형별 인원:
{ax_summary}

RAG 검색으로 AX Compass 자료를 참조한 후, 커리큘럼을 생성하고 검증까지 완료해주세요."""

    try:
        reply, curriculum, validation = agent.chat(msg)
    except Exception as e:
        import traceback
        st.session_state.agent_error = f"에이전트 오류: {e}\n\n{traceback.format_exc()}"
        st.session_state.generating = False
        return

    st.session_state.agent_log = tool_calls_log + [{"type": "reply", "text": reply}]
    if curriculum:
        st.session_state.final_curriculum = curriculum
    if validation:
        st.session_state.final_validation = validation
    if not curriculum:
        st.session_state.agent_error = f"커리큘럼 생성 실패. 에이전트 응답:\n{reply}"
    st.session_state.generating = False


# ── 메인 앱 ──────────────────────────────────────────────────────────────────
def show_main_app():
    st.set_page_config(page_title="AX Single Agent", page_icon="◈", layout="wide")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    render_sidebar()
    _init_wizard_state()

    # 생성 실행은 컬럼 밖에서 (spinner가 전체 폭으로 표시되고 rerun 후 에러가 유지됨)
    if st.session_state.generating:
        with st.spinner("에이전트가 커리큘럼을 생성하고 있습니다... (1~2분 소요)"):
            run_agent_generation()
        st.rerun()
        return

    col_input, col_result = st.columns([1, 1], gap="large")

    with col_input:
        st.markdown('<div class="main-title">◈ AX Single Agent</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">AX Compass 기반 교육 커리큘럼 자동 설계</div>', unsafe_allow_html=True)
        st.markdown('<hr class="clean-divider">', unsafe_allow_html=True)

        step_idx = st.session_state.wizard_step
        done = st.session_state.final_curriculum is not None

        # 에러 표시 (rerun 후에도 유지)
        if st.session_state.get("agent_error"):
            st.error(st.session_state.agent_error)
            if st.button("다시 시도", use_container_width=True):
                st.session_state.agent_error = None
                st.session_state.generating = True
                st.rerun()

        elif done:
            st.markdown("""
            <div class="done-banner">
                <div class="done-icon">✓</div>
                <div>
                    <div class="done-title">커리큘럼 생성 완료</div>
                    <div class="done-sub">오른쪽에서 결과를 확인하세요.</div>
                </div>
            </div>""", unsafe_allow_html=True)
            render_agent_log()
            st.markdown("---")
            render_data_summary()
            if st.button("새로 시작", use_container_width=True):
                _reset_wizard()
                st.rerun()
        else:
            render_step_form()
            if step_idx > 0:
                st.markdown("---")
                render_data_summary()

    with col_result:
        st.markdown('<div class="main-title">커리큘럼 결과</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">생성된 교육 과정이 여기에 표시됩니다.</div>', unsafe_allow_html=True)
        st.markdown('<hr class="clean-divider">', unsafe_allow_html=True)

        curriculum = st.session_state.get("final_curriculum")
        validation = st.session_state.get("final_validation")

        if curriculum:
            if validation:
                if validation.get("passed"):
                    st.markdown("""
                    <div class="done-banner">
                        <div class="done-icon">✓</div>
                        <div>
                            <div class="done-title">커리큘럼 생성 완료</div>
                            <div class="done-sub">모든 규칙 검증을 통과했습니다.</div>
                        </div>
                    </div>""", unsafe_allow_html=True)
                render_validation(validation)
                st.markdown("---")

            render_curriculum(curriculum)

            st.markdown("---")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button(
                    "JSON 다운로드",
                    data=json.dumps(curriculum, ensure_ascii=False, indent=2),
                    file_name="curriculum.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with col_dl2:
                md_lines = [f"# {curriculum.get('overview',{}).get('company','')} 교육 커리큘럼\n"]
                ov = curriculum.get("overview", {})
                md_lines.append(f"- 대상: {ov.get('audience','')}")
                md_lines.append(f"- 기간: {ov.get('days',0)}일 × {ov.get('hours_per_day',0)}h = {ov.get('total_hours',0)}h\n")
                for s in curriculum.get("theory_sessions", []):
                    md_lines.append(f"## {s['order']}. {s['title']} ({s['duration_hours']}h)\n{s.get('objective','')}")
                st.download_button(
                    "Markdown 다운로드",
                    data="\n".join(md_lines),
                    file_name="curriculum.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
        else:
            st.markdown("""
            <div style="text-align:center;padding:60px 20px;color:#aaa;border:1px dashed #ddd;border-radius:12px;">
                <div style="font-size:2.5rem;margin-bottom:12px;">📋</div>
                <div style="font-size:.9rem;">아직 생성된 커리큘럼이 없습니다.<br>왼쪽 채팅에서 요구사항을 입력하세요.</div>
            </div>""", unsafe_allow_html=True)


# ── 진입점 ────────────────────────────────────────────────────────────────────
def main():
    if not is_authenticated():
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()
