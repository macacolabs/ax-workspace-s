"""
AX MultiAgent — Streamlit 프론트엔드
=====================================
OrchestratorAgent를 직접 임포트해 독립 실행 (FastAPI 불필요).
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
sys.path.insert(0, str(_BASE / "08_MultiAgent"))
sys.path.insert(0, str(_BASE / "05_Advanced_RAG_indexing_contextual"))

load_dotenv(_BASE / ".env")

# ── 인증 ──────────────────────────────────────────────────────────────────────
USERS = {"admin": hashlib.sha256("admin".encode()).hexdigest()}
TOKEN_TTL = 8 * 3600


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def is_authenticated() -> bool:
    return bool(st.session_state.get("auth_token")) and time.time() < st.session_state.get("auth_expiry", 0)


def do_login(u: str, p: str) -> bool:
    if USERS.get(u) == _hash(p):
        st.session_state.auth_token = secrets.token_hex(32)
        st.session_state.auth_expiry = time.time() + TOKEN_TTL
        st.session_state.auth_user = u
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
section[data-testid="stSidebar"] { background: #0a0a0a !important; border-right: 1px solid #222; }
section[data-testid="stSidebar"] * { color: #f0f0f0 !important; }
section[data-testid="stSidebar"] hr { border-color: #333 !important; }

/* 타이틀 */
.main-title { font-size:1.5rem;font-weight:800;color:#111;letter-spacing:-.02em;margin-bottom:2px; }
.main-subtitle { font-size:.85rem;color:#888;margin-bottom:24px; }
.clean-divider { border:none;border-top:1px solid #eee;margin:20px 0; }

/* 진행 이벤트 */
.prog-item { display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid #f0f0f0; }
.prog-item:last-child { border-bottom:none; }
.prog-icon { width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700;flex-shrink:0; }
.prog-rag    { background:#e8f4fd;color:#1a6fa8; }
.prog-gen    { background:#fff3e0;color:#e65100; }
.prog-val    { background:#f3e8fd;color:#6a1a8f; }
.prog-orch   { background:#e8fdf0;color:#1a8f50; }
.prog-err    { background:#fde8e8;color:#8f1a1a; }
.prog-body { flex:1; }
.prog-agent { font-size:.68rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:#888;margin-bottom:2px; }
.prog-msg { font-size:.82rem;color:#333;line-height:1.5; }

/* 검증 결과 */
.val-section { border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;margin-bottom:16px; }
.val-header { display:flex;align-items:center;justify-content:space-between;padding:10px 16px;font-size:.78rem;font-weight:700; }
.val-header-code { background:#f4f8fd; }
.val-header-llm  { background:#fdf4fd; }
.val-check { display:flex;align-items:flex-start;gap:8px;padding:8px 16px;border-top:1px solid #f0f0f0;font-size:.8rem; }
.val-check:first-child { border-top:none; }
.val-pass { color:#2d6a2d; }
.val-fail { color:#cc0000; }
.val-warn { color:#7a4f00; }
.val-name { font-weight:600;min-width:160px;flex-shrink:0; }
.val-detail { color:#666;flex:1; }
.val-score { font-weight:700;min-width:40px;text-align:right;flex-shrink:0; }
.verify-ok   { background:#f0faf0;border:1px solid #cce5cc;color:#2d6a2d;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }
.verify-warn { background:#fff8f0;border:1px solid #f0d9b5;color:#7a4f00;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }
.verify-fail { background:#fff0f0;border:1px solid #ffcccc;color:#cc0000;padding:8px 14px;border-radius:8px;font-size:.8rem;font-weight:600;display:inline-block;margin:4px 0; }

/* 커리큘럼 카드 */
.overview-card { background:#111;color:#fff;border-radius:12px;padding:28px 32px;margin-bottom:24px; }
.overview-card h2 { font-size:1.3rem;font-weight:700;margin:0 0 6px; }
.overview-card .subtitle { font-size:.85rem;color:#999;margin-bottom:20px; }
.stat-row { display:flex;gap:16px;flex-wrap:wrap;margin-top:16px; }
.stat-box { background:#1e1e1e;border:1px solid #333;border-radius:8px;padding:12px 18px;flex:1;min-width:100px; }
.stat-box .label { font-size:.7rem;color:#888;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px; }
.stat-box .value { font-size:1.2rem;font-weight:700; }
.section-header { display:flex;align-items:center;gap:10px;margin:28px 0 14px;padding-bottom:10px;border-bottom:2px solid #111; }
.section-header .tag { background:#111;color:#fff;font-size:.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;padding:3px 10px;border-radius:20px; }
.section-header h3 { font-size:1rem;font-weight:700;margin:0; }
.session-card { border:1px solid #e0e0e0;border-radius:10px;padding:18px 20px;margin-bottom:12px; }
.session-card .session-title { font-size:.95rem;font-weight:600;margin-bottom:6px; }
.session-card .session-meta { font-size:.78rem;color:#666;margin-bottom:10px;display:flex;gap:12px; }
.session-card .badge { background:#f0f0f0;color:#333;font-size:.7rem;font-weight:600;padding:2px 8px;border-radius:4px; }
.session-card .duration-badge { background:#111;color:#fff;font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:4px; }
.session-card .objective { font-size:.82rem;color:#444;margin-bottom:8px;line-height:1.5; }
.session-card .activities { list-style:none;padding:0;margin:0; }
.session-card .activities li { font-size:.8rem;color:#555;padding:3px 0;border-top:1px solid #f0f0f0;display:flex;align-items:flex-start;gap:8px; }
.session-card .activities li::before { content:"→";color:#999;flex-shrink:0;margin-top:1px; }
.group-header-A { background:#111;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;font-size:.8rem;font-weight:700; }
.group-header-B { background:#333;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;font-size:.8rem;font-weight:700; }
.group-header-C { background:#555;color:#fff;padding:10px 16px;border-radius:8px 8px 0 0;font-size:.8rem;font-weight:700; }
.outcome-item { display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid #f0f0f0;font-size:.85rem;color:#333; }
.outcome-item:last-child { border-bottom:none; }
.outcome-dot { width:6px;height:6px;background:#111;border-radius:50%;flex-shrink:0;margin-top:6px; }
.done-banner { background:linear-gradient(135deg,#0a0a0a,#1f1f1f);color:#fff;border-radius:12px;padding:20px 28px;margin-bottom:24px;display:flex;align-items:center;gap:16px; }
.done-banner .done-icon { font-size:2rem;line-height:1;flex-shrink:0; }
.done-banner .done-title { font-size:1.05rem;font-weight:700;margin-bottom:3px; }
.done-banner .done-sub { font-size:.78rem;color:#aaa; }
.stButton > button { background:#111 !important;color:#fff !important;border:none !important;border-radius:8px !important;font-weight:600 !important;padding:10px 20px !important; }
.stButton > button:hover { background:#333 !important; }

/* 이력 테이블 */
.hist-row { display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #f0f0f0;font-size:.82rem; }
.hist-row:last-child { border-bottom:none; }
.hist-company { font-weight:600;min-width:120px;color:#111; }
.hist-meta { color:#888;flex:1; }
.hist-badge-ok   { background:#f0faf0;color:#2d6a2d;font-size:.68rem;font-weight:700;padding:2px 8px;border-radius:20px; }
.hist-badge-fail { background:#fff0f0;color:#cc0000;font-size:.68rem;font-weight:700;padding:2px 8px;border-radius:20px; }
.hist-badge-none { background:#f0f0f0;color:#888;font-size:.68rem;font-weight:700;padding:2px 8px;border-radius:20px; }
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

# ── 단계별 입력 ───────────────────────────────────────────────────────────────
_STEPS = [
    {"key": "company",       "label": "회사명",      "hint": "예: 삼성전자",                             "type": "text",  "q": "1단계 / 8  —  교육을 진행할 **회사명**을 입력해주세요."},
    {"key": "audience",      "label": "교육 대상자",  "hint": "예: 비개발 직군 대리~차장, AI 경험 거의 없음", "type": "text",  "q": "2단계 / 8  —  **교육 대상자**를 설명해주세요."},
    {"key": "ai_experience", "label": "AI 경험 수준", "hint": "예: ChatGPT 가끔 사용해봄",                "type": "text",  "q": "3단계 / 8  —  교육 대상자의 **AI 경험 수준**을 입력해주세요."},
    {"key": "constraints",   "label": "제약 조건",    "hint": "예: ChatGPT만 사용 가능, 실습 위주 구성",   "type": "area",  "q": "4단계 / 8  —  꼭 반영해야 할 **조건 또는 제한 사항**을 입력해주세요."},
    {"key": "goal",          "label": "교육 목표",    "hint": "예: 업무 생산성 향상, AI 도구 활용 역량 강화", "type": "area",  "q": "5단계 / 8  —  **교육 목표**를 입력해주세요."},
    {"key": "days",          "label": "교육 일수",    "hint": "예: 2",                                   "type": "int",   "q": "6단계 / 8  —  **교육 일수**를 입력해주세요."},
    {"key": "hours_per_day", "label": "일 교육 시간", "hint": "예: 8",                                   "type": "float", "q": "7단계 / 8  —  **일 교육 시간**을 입력해주세요."},
    {"key": "ax_counts",     "label": "AX Compass",  "hint": "",                                        "type": "ax",    "q": "8단계 / 8  —  **AX Compass 유형별 인원수**를 입력해주세요."},
]
_AX_TYPES = ["균형형", "이해형", "과신형", "실행형", "판단형", "조심형"]
_TOTAL_STEPS = len(_STEPS)

AGENT_ICON = {"RAGAgent": "🔍", "CurriculumGeneratorAgent": "✏️", "ValidatorAgent": "✓", "Orchestrator": "◈"}
AGENT_CSS = {"RAGAgent": "prog-rag", "CurriculumGeneratorAgent": "prog-gen", "ValidatorAgent": "prog-val", "Orchestrator": "prog-orch"}


# ── 상태 초기화 / 리셋 ────────────────────────────────────────────────────────
def _init_state():
    for k, v in [
        ("wizard_step", 0), ("wizard_data", {}), ("progress_log", []),
        ("final_result", None), ("generating", False), ("agent_error", None),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v


def _reset():
    for k in ("wizard_step", "wizard_data", "progress_log", "final_result",
              "generating", "agent_error", "orchestrator"):
        st.session_state.pop(k, None)


def _get_orchestrator():
    if "orchestrator" not in st.session_state:
        try:
            api_key = _get_secret("OPENAI_API_KEY")
            from agents.orchestrator import OrchestratorAgent
            from evaluation.schema import AgentProgress

            log: list[dict] = st.session_state.setdefault("progress_log", [])

            def on_progress(p: AgentProgress):
                log.append({
                    "stage": p.stage, "agent": p.agent,
                    "message": p.message, "data": p.data,
                })

            st.session_state.orchestrator = OrchestratorAgent(
                api_key=api_key,
                chroma_dir=_BASE / "chroma_db",
                data_dir=_BASE / "Data",
                on_progress=on_progress,
            )
        except Exception as e:
            import traceback
            st.session_state.agent_error = f"오케스트레이터 초기화 실패: {e}\n{traceback.format_exc()}"
            return None
    return st.session_state.orchestrator


def _get_secret(key: str) -> str:
    try:
        v = st.secrets.get(key, "")
    except Exception:
        v = ""
    return v or os.environ.get(key, "")


# ── 로그인 ────────────────────────────────────────────────────────────────────
def show_login_page():
    st.set_page_config(page_title="AX MultiAgent — 로그인", page_icon="◈", layout="centered")
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    st.markdown("""
    <div class="login-wrap">
        <div class="login-logo">◈ AX MultiAgent</div>
        <div class="login-sub">멀티 에이전트 기반 AI 교육 커리큘럼 설계</div>
    </div>""", unsafe_allow_html=True)
    with st.form("login_form"):
        st.markdown("#### 로그인")
        u = st.text_input("아이디", placeholder="admin")
        p = st.text_input("비밀번호", type="password")
        ok = st.form_submit_button("로그인", use_container_width=True)
    if ok:
        if do_login(u, p):
            st.rerun()
        else:
            st.markdown('<div class="login-err">아이디 또는 비밀번호가 올바르지 않습니다.</div>', unsafe_allow_html=True)


# ── 사이드바 ──────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("### ◈ AX MultiAgent")
        st.markdown(f"**{st.session_state.get('auth_user','')}** 로그인 중")
        st.markdown("---")
        if st.button("새로 시작", use_container_width=True):
            _reset()
            st.rerun()

        st.markdown("---")
        ok_color = "#4caf50" if _get_secret("OPENAI_API_KEY") else "#f44336"
        ok_icon  = "✓" if _get_secret("OPENAI_API_KEY") else "✗"
        st.markdown(f'<span style="color:{ok_color};font-size:.8rem;">{ok_icon} OpenAI API</span>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### 에이전트 구성")
        for agent, icon in AGENT_ICON.items():
            if agent != "Orchestrator":
                st.markdown(f'<div style="font-size:.8rem;padding:3px 0;">{icon} {agent}</div>', unsafe_allow_html=True)

        st.markdown("---")
        if st.button("로그아웃", use_container_width=True):
            do_logout()
            st.rerun()

        # 이력 사이드바
        try:
            from backend.storage import CurriculumStorage
            storage = CurriculumStorage()
            items = storage.list()
            if items:
                st.markdown("---")
                st.markdown("#### 저장된 커리큘럼")
                for item in items[:5]:
                    badge = "hist-badge-ok" if item.get("validation_passed") else (
                        "hist-badge-fail" if item.get("validation_passed") is False else "hist-badge-none")
                    badge_text = "통과" if item.get("validation_passed") else (
                        "실패" if item.get("validation_passed") is False else "?")
                    st.markdown(
                        f'<div class="hist-row">'
                        f'<div class="hist-company">{item["company"][:10]}</div>'
                        f'<div class="hist-meta">{item["total_hours"]}h</div>'
                        f'<span class="{badge}">{badge_text}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        except Exception:
            pass


# ── 위자드 단계 폼 ────────────────────────────────────────────────────────────
def render_step_form():
    step_idx = st.session_state.wizard_step
    step = _STEPS[step_idx]

    st.progress(step_idx / _TOTAL_STEPS)
    st.markdown(f"<div style='font-size:.75rem;color:#888;margin:-8px 0 12px;'>진행률 {step_idx}/{_TOTAL_STEPS}</div>", unsafe_allow_html=True)
    st.markdown(f"#### {step['q']}")

    with st.form(f"step_{step_idx}", clear_on_submit=False):
        if step["type"] == "text":
            val = st.text_input(step["label"], placeholder=step["hint"],
                                value=st.session_state.wizard_data.get(step["key"], ""))
        elif step["type"] == "area":
            val = st.text_area(step["label"], placeholder=step["hint"], height=80,
                               value=st.session_state.wizard_data.get(step["key"], ""))
        elif step["type"] == "int":
            val = st.number_input(step["label"], min_value=1, max_value=30, step=1,
                                  value=int(st.session_state.wizard_data.get(step["key"], 1)))
        elif step["type"] == "float":
            val = st.number_input(step["label"], min_value=1.0, max_value=24.0, step=0.5,
                                  value=float(st.session_state.wizard_data.get(step["key"], 8.0)))
        else:  # ax
            existing = st.session_state.wizard_data.get("ax_counts", {})
            ax_vals = {}
            cols = st.columns(3)
            for i, t in enumerate(_AX_TYPES):
                with cols[i % 3]:
                    ax_vals[t] = st.number_input(t, min_value=0, max_value=200, step=1,
                                                  value=int(existing.get(t, 0)), key=f"ax_{t}")
            val = ax_vals

        c1, c2 = st.columns([1, 2])
        with c1:
            prev = st.form_submit_button("← 이전", use_container_width=True, disabled=(step_idx == 0))
        with c2:
            btn_label = "커리큘럼 생성 →" if step_idx == _TOTAL_STEPS - 1 else "다음 →"
            nxt = st.form_submit_button(btn_label, use_container_width=True)

    if prev and step_idx > 0:
        st.session_state.wizard_step -= 1
        st.rerun()

    if nxt:
        if step["type"] in ("text", "area"):
            if not str(val).strip():
                st.warning("내용을 입력해주세요.")
                return
            st.session_state.wizard_data[step["key"]] = str(val).strip()
        elif step["type"] in ("int", "float"):
            st.session_state.wizard_data[step["key"]] = val
        else:  # ax
            if sum(val.values()) == 0:
                st.warning("최소 한 명 이상 입력해주세요.")
                return
            st.session_state.wizard_data["ax_counts"] = val

        if step_idx < _TOTAL_STEPS - 1:
            st.session_state.wizard_step += 1
        else:
            st.session_state.progress_log = []
            st.session_state.generating = True
        st.rerun()


def render_data_summary():
    data = st.session_state.wizard_data
    if not data:
        return
    rows = []
    for s in _STEPS:
        k = s["key"]
        if k not in data:
            continue
        if k == "ax_counts":
            total = sum(data[k].values())
            rows.append(f"**인원**: 총 {total}명 — " + " · ".join(f"{t} {n}" for t, n in data[k].items() if n > 0))
        else:
            rows.append(f"**{s['label']}**: {data[k]}")
    for r in rows:
        st.markdown(f"<div style='font-size:.82rem;color:#444;padding:3px 0;border-bottom:1px solid #f0f0f0;'>{r}</div>", unsafe_allow_html=True)


# ── 진행 로그 렌더링 ──────────────────────────────────────────────────────────
def render_progress_log():
    log = st.session_state.get("progress_log", [])
    if not log:
        return
    st.markdown("#### 에이전트 실행 이력")
    for entry in log:
        agent = entry.get("agent", "")
        icon = AGENT_ICON.get(agent, "•")
        css_cls = AGENT_CSS.get(agent, "prog-orch")
        msg = entry.get("message", "")
        stage = entry.get("stage", "")
        if stage == "error":
            css_cls = "prog-err"
        st.markdown(
            f'<div class="prog-item">'
            f'<div class="prog-icon {css_cls}">{icon}</div>'
            f'<div class="prog-body">'
            f'<div class="prog-agent">{agent}</div>'
            f'<div class="prog-msg">{msg}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


# ── 검증 결과 렌더링 ──────────────────────────────────────────────────────────
def render_validation(validation: dict):
    if not validation:
        return

    code_val = validation.get("code_validation", {})
    llm_val = validation.get("llm_validation", {})
    overall_passed = validation.get("passed", False)

    if overall_passed:
        st.markdown(f'<div class="verify-ok">✓ 검증 통과 — 종합 점수 {validation.get("overall_score", 0):.0%}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="verify-fail">✗ 검증 실패 — 종합 점수 {validation.get("overall_score", 0):.0%} | 시도 {validation.get("attempt", 1)}회</div>', unsafe_allow_html=True)

    # 코드 검증
    st.markdown(
        f'<div class="val-section">'
        f'<div class="val-header val-header-code">'
        f'<span>코드 검증 (규칙 기반)</span>'
        f'<span>점수: {code_val.get("score", 0):.0%} {"✓" if code_val.get("passed") else "✗"}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    for c in code_val.get("checks", []):
        status = c.get("status", "fail")
        css = "val-pass" if status == "pass" else ("val-warn" if status == "warn" else "val-fail")
        icon = "✓" if status == "pass" else ("⚠" if status == "warn" else "✗")
        detail = c.get("detail", "")
        st.markdown(
            f'<div class="val-check {css}">'
            f'<span>{icon}</span>'
            f'<span class="val-name">{c["name"]}</span>'
            f'<span class="val-detail">{detail}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    # LLM 판단
    st.markdown(
        f'<div class="val-section">'
        f'<div class="val-header val-header-llm">'
        f'<span>LLM 판단 (의미 기반)</span>'
        f'<span>점수: {llm_val.get("score", 0):.0%} {"✓" if llm_val.get("passed") else "✗"}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    LABEL_KO = {
        "goal_alignment": "목표 부합도",
        "audience_appropriateness": "대상 적절성",
        "constraint_compliance": "제약 준수도",
        "faithfulness": "충실도 (RAG)",
    }
    for c in llm_val.get("checks", []):
        passed = c.get("passed", False)
        score = c.get("score", 0)
        css = "val-pass" if passed else "val-fail"
        icon = "✓" if passed else "✗"
        name_ko = LABEL_KO.get(c["name"], c["name"])
        reason = c.get("reason", "")
        st.markdown(
            f'<div class="val-check {css}">'
            f'<span>{icon}</span>'
            f'<span class="val-name">{name_ko}</span>'
            f'<span class="val-detail">{reason[:80]}</span>'
            f'<span class="val-score">{score:.0%}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        ungrounded = c.get("ungrounded_claims", [])
        if ungrounded:
            for claim in ungrounded:
                st.markdown(
                    f'<div class="val-check val-warn" style="padding-left:40px;">'
                    f'<span>⚠</span><span class="val-detail">근거 없음: {claim[:100]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    st.markdown('</div>', unsafe_allow_html=True)


# ── 커리큘럼 카드 뷰 ──────────────────────────────────────────────────────────
def render_curriculum_card(curriculum: dict):
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

    theory = curriculum.get("theory_sessions", [])
    if theory:
        st.markdown('<div class="section-header"><span class="tag">THEORY</span><h3>이론 세션</h3></div>', unsafe_allow_html=True)
        for s in theory:
            acts = "".join(f"<li>{a}</li>" for a in s.get("activities", []))
            concepts = " ".join(f'<span class="badge">{c}</span>' for c in s.get("key_concepts", []))
            st.markdown(f"""
            <div class="session-card">
                <div class="session-title">{s.get('order','')}. {s.get('title','')}</div>
                <div class="session-meta"><span class="duration-badge">{s.get('duration_hours',0)}h</span> {concepts}</div>
                <div class="objective">{s.get('objective','')}</div>
                <ul class="activities">{acts}</ul>
            </div>""", unsafe_allow_html=True)

    practice = curriculum.get("practice_sessions", {})
    if practice:
        st.markdown('<div class="section-header"><span class="tag">PRACTICE</span><h3>그룹별 실습</h3></div>', unsafe_allow_html=True)
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
                    <div class="session-title">{s.get('order','')}. {s.get('title','')}</div>
                    <div class="session-meta"><span class="duration-badge">{s.get('duration_hours',0)}h</span></div>
                    <div class="objective">{s.get('objective','')}</div>
                    <ul class="activities">{acts}</ul>
                    {"<div style='font-size:.78rem;color:#888;margin-top:8px;'>💡 " + rationale + "</div>" if rationale else ""}
                </div>""", unsafe_allow_html=True)

    outcomes = curriculum.get("expected_outcomes", [])
    if outcomes:
        st.markdown('<div class="section-header"><span class="tag">OUTCOMES</span><h3>기대 성과</h3></div>', unsafe_allow_html=True)
        items = "".join(f'<div class="outcome-item"><div class="outcome-dot"></div>{o}</div>' for o in outcomes)
        st.markdown(f'<div>{items}</div>', unsafe_allow_html=True)


# ── 생성 실행 ─────────────────────────────────────────────────────────────────
def run_generation():
    st.session_state.agent_error = None
    orchestrator = _get_orchestrator()
    if orchestrator is None:
        st.session_state.generating = False
        return

    from backend.storage import CurriculumStorage
    storage = CurriculumStorage()
    requirements = dict(st.session_state.wizard_data)

    try:
        result = orchestrator.run(requirements)
    except Exception as e:
        import traceback
        st.session_state.agent_error = f"실행 오류: {e}\n{traceback.format_exc()}"
        st.session_state.generating = False
        return

    if result.curriculum:
        try:
            storage.save(
                curriculum=result.curriculum,
                validation=result.validation.to_dict() if result.validation else None,
                requirements=requirements,
                attempts=result.attempts,
            )
        except Exception:
            pass

    if not result.curriculum:
        st.session_state.agent_error = f"커리큘럼 생성 실패.\n에이전트 응답: {result.reply}"

    st.session_state.final_result = result
    st.session_state.generating = False


# ── 메인 앱 ──────────────────────────────────────────────────────────────────
def show_main_app():
    st.set_page_config(page_title="AX MultiAgent", page_icon="◈", layout="wide")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    render_sidebar()
    _init_state()

    # 생성 실행은 컬럼 밖에서
    if st.session_state.generating:
        with st.spinner("멀티 에이전트 실행 중... (RAG → 생성 → 검증, 1~2분 소요)"):
            run_generation()
        st.rerun()
        return

    col_input, col_result = st.columns([1, 1], gap="large")

    with col_input:
        st.markdown('<div class="main-title">◈ AX MultiAgent</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">멀티 에이전트 기반 AI 교육 커리큘럼 설계</div>', unsafe_allow_html=True)
        st.markdown('<hr class="clean-divider">', unsafe_allow_html=True)

        result = st.session_state.final_result
        error = st.session_state.agent_error
        step_idx = st.session_state.wizard_step

        if error:
            st.error(error)
            if st.button("다시 시도", use_container_width=True):
                st.session_state.agent_error = None
                st.session_state.progress_log = []
                st.session_state.generating = True
                st.rerun()
            st.markdown("---")
            render_progress_log()

        elif result is not None:
            st.markdown("""
            <div class="done-banner">
                <div class="done-icon">◈</div>
                <div>
                    <div class="done-title">커리큘럼 생성 완료</div>
                    <div class="done-sub">오른쪽에서 결과를 확인하고 다운로드하세요.</div>
                </div>
            </div>""", unsafe_allow_html=True)
            render_progress_log()
            st.markdown("---")
            render_data_summary()
            if st.button("새로 시작", use_container_width=True):
                _reset()
                st.rerun()

        else:
            render_step_form()
            if step_idx > 0:
                st.markdown("---")
                render_data_summary()

    with col_result:
        st.markdown('<div class="main-title">커리큘럼 결과</div>', unsafe_allow_html=True)
        st.markdown('<div class="main-subtitle">생성된 교육 과정 및 검증 결과</div>', unsafe_allow_html=True)
        st.markdown('<hr class="clean-divider">', unsafe_allow_html=True)

        result = st.session_state.final_result
        if result is None or result.curriculum is None:
            st.markdown("""
            <div style="text-align:center;padding:60px 20px;color:#aaa;border:1px dashed #ddd;border-radius:12px;">
                <div style="font-size:2.5rem;margin-bottom:12px;">◈</div>
                <div style="font-size:.9rem;">아직 생성된 커리큘럼이 없습니다.<br>왼쪽에서 요구사항을 입력하세요.</div>
            </div>""", unsafe_allow_html=True)
            return

        curriculum = result.curriculum
        validation = result.validation

        # 에이전트 응답
        if result.reply:
            st.markdown(
                f'<div style="background:#f5f5f5;border-radius:10px;padding:12px 16px;font-size:.88rem;color:#333;margin-bottom:16px;">'
                f'{result.reply}</div>',
                unsafe_allow_html=True,
            )

        # 검증 결과
        if validation:
            render_validation(validation.to_dict())
        st.markdown("---")

        # 카드뷰 / JSON뷰 탭
        tab_card, tab_json = st.tabs(["📋 커리큘럼 카드", "{ } JSON"])
        with tab_card:
            render_curriculum_card(curriculum)
        with tab_json:
            st.code(json.dumps(curriculum, ensure_ascii=False, indent=2), language="json")

        # 다운로드
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "JSON 다운로드",
                data=json.dumps(curriculum, ensure_ascii=False, indent=2),
                file_name=f"{curriculum.get('overview',{}).get('company','curriculum')}_curriculum.json",
                mime="application/json",
                use_container_width=True,
            )
        with c2:
            ov = curriculum.get("overview", {})
            lines = [
                f"# {ov.get('company','')} AI 교육 커리큘럼",
                f"- 대상: {ov.get('audience','')}",
                f"- 기간: {ov.get('days',0)}일 × {ov.get('hours_per_day',0)}h = {ov.get('total_hours',0)}h",
                f"- 난이도: {ov.get('difficulty','')}",
                "",
            ]
            for s in curriculum.get("theory_sessions", []):
                lines.append(f"## {s['order']}. {s['title']} ({s['duration_hours']}h)")
                lines.append(s.get("objective", ""))
                lines.append("")
            for grp, sessions in curriculum.get("practice_sessions", {}).items():
                if sessions:
                    lines.append(f"## {grp} 실습")
                    for s in sessions:
                        lines.append(f"### {s['order']}. {s['title']} ({s['duration_hours']}h)")
                        lines.append(s.get("objective", ""))
                    lines.append("")
            st.download_button(
                "Markdown 다운로드",
                data="\n".join(lines),
                file_name=f"{ov.get('company','curriculum')}_curriculum.md",
                mime="text/markdown",
                use_container_width=True,
            )


# ── 진입점 ────────────────────────────────────────────────────────────────────
def main():
    if not is_authenticated():
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()
