import time
from html import escape
from uuid import uuid4

import streamlit as st

from core.audit import read_audit_events, verify_audit_integrity, write_audit_event
from core.config import enterprise_warnings, get_settings
from core.connectors import connector_inventory
from core.database import init_db, list_approval_requests, list_interview_actions
from core.pdf_utils import extract_document_text
from core.security import stable_hash, verify_password


settings = get_settings()
init_db()

st.set_page_config(page_title=settings.app_name, page_icon="P", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --po-ink: #111827;
        --po-muted: #64748b;
        --po-soft: #94a3b8;
        --po-line: #e2e8f0;
        --po-paper: #f6f8fb;
        --po-panel: #ffffff;
        --po-panel-strong: #f8fafc;
        --po-accent: #2563eb;
        --po-accent-soft: #eff6ff;
        --po-accent-line: #bfdbfe;
        --po-amber: #b45309;
        --po-green: #047857;
        --po-blue: #1d4ed8;
        --po-red: #b42318;
        --po-shadow: 0 1px 2px rgba(15, 23, 42, 0.05), 0 10px 22px rgba(15, 23, 42, 0.035);
        --po-shadow-soft: 0 1px 1px rgba(15, 23, 42, 0.04);
        --po-radius: 6px;
    }

    .stApp {
        background: var(--po-paper);
        color: var(--po-ink);
    }
    .block-container {
        max-width: 1240px;
        padding-top: 0.85rem;
        padding-bottom: 1.75rem;
    }
    header[data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stDeployButton"],
    [data-testid="stAppDeployButton"],
    #MainMenu {
        display: none !important;
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
        border-right: 1px solid var(--po-line);
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 0.9rem;
    }
    h1, h2, h3 {
        letter-spacing: 0;
        color: var(--po-ink);
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        padding: 10px 12px;
        box-shadow: var(--po-shadow);
    }
    div[data-testid="stMetric"] label {
        color: var(--po-muted);
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--po-ink);
        font-weight: 760;
        font-size: 1.2rem;
    }
    .po-topline {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 18px;
        padding: 14px 16px;
        margin-bottom: 12px;
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: #ffffff;
        box-shadow: var(--po-shadow);
    }
    .po-kicker {
        color: var(--po-muted);
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.11em;
        margin-bottom: 4px;
    }
    .po-title {
        margin: 0;
        font-size: 26px;
        line-height: 1.12;
        font-weight: 820;
    }
    .po-subtitle {
        margin-top: 6px;
        max-width: 820px;
        color: var(--po-muted);
        font-size: 13px;
    }
    .po-status-stack {
        display: grid;
        grid-template-columns: 1fr;
        gap: 6px;
        min-width: 178px;
    }
    .po-pill {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 28px;
        padding: 5px 9px;
        border-radius: var(--po-radius);
        border: 1px solid var(--po-line);
        background: rgba(255,255,255,0.88);
        color: var(--po-ink);
        font-size: 12px;
        font-weight: 760;
        white-space: nowrap;
    }
    .po-pill.green { color: var(--po-green); border-color: rgba(15,118,110,0.28); background: #ecfdf5; }
    .po-pill.amber { color: var(--po-amber); border-color: #fde68a; background: #fffbeb; }
    .po-pill.blue { color: var(--po-blue); border-color: var(--po-accent-line); background: var(--po-accent-soft); }
    .po-section {
        margin: 14px 0 8px;
        color: var(--po-muted);
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .po-panel {
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: #ffffff;
        padding: 12px;
        box-shadow: var(--po-shadow);
    }
    .po-panel-title {
        margin: 0 0 4px;
        color: var(--po-ink);
        font-weight: 820;
        font-size: 14px;
    }
    .po-panel-copy {
        margin: 0;
        color: var(--po-muted);
        font-size: 13px;
    }
    .po-agent-hero {
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: #ffffff;
        padding: 12px 14px;
        margin: 6px 0 10px;
        box-shadow: var(--po-shadow);
    }
    .po-agent-title {
        margin: 0;
        color: var(--po-ink);
        font-size: 18px;
        line-height: 1.25;
        font-weight: 840;
    }
    .po-agent-copy {
        margin: 6px 0 0;
        max-width: 900px;
        color: var(--po-muted);
        font-size: 13px;
        line-height: 1.55;
    }
    div[data-testid="stForm"] {
        border: 1px solid var(--po-accent-line);
        border-radius: var(--po-radius);
        background: #ffffff;
        padding: 10px;
        margin-bottom: 12px;
        box-shadow: var(--po-shadow);
    }
    div[data-testid="stForm"] textarea {
        min-height: 92px !important;
        border-radius: var(--po-radius);
        border-color: var(--po-line) !important;
        background: #ffffff !important;
        font-size: 15px !important;
        line-height: 1.55 !important;
    }
    div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
        min-height: 44px;
        border-color: var(--po-accent) !important;
        background: var(--po-accent) !important;
        color: #ffffff !important;
        font-weight: 820;
    }
    .po-evidence-card {
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: #ffffff;
        padding: 10px 11px;
        margin-bottom: 8px;
        box-shadow: var(--po-shadow-soft);
    }
    .po-evidence-source {
        color: var(--po-blue);
        font-size: 11px;
        font-weight: 800;
        overflow-wrap: anywhere;
    }
    .po-evidence-snippet {
        margin-top: 5px;
        color: var(--po-ink);
        font-size: 12px;
        line-height: 1.55;
    }
    .po-signal-list {
        display: grid;
        gap: 6px;
    }
    .po-signal-row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        border-bottom: 1px solid var(--po-line);
        padding: 6px 0;
        font-size: 12px;
    }
    .po-signal-row:last-child {
        border-bottom: 0;
    }
    .po-signal-label {
        color: var(--po-muted);
        font-weight: 700;
    }
    .po-signal-value {
        color: var(--po-ink);
        font-weight: 800;
        text-align: right;
    }
    .po-context-note {
        border: 1px dashed var(--po-line);
        border-radius: var(--po-radius);
        background: #f8fafc;
        color: var(--po-muted);
        font-size: 12px;
        line-height: 1.5;
        padding: 10px;
    }
    .po-chat-feed-label {
        margin: 16px 0 8px;
        color: var(--po-muted);
        font-size: 11px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .po-loop-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 8px;
        margin: 10px 0 8px;
    }
    .po-loop-rail {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 6px;
        align-items: center;
        margin: 8px 0 10px;
        padding: 6px;
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: #eaf1fb;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.85);
    }
    .po-rail-item {
        min-height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--po-radius);
        border: 1px solid var(--po-line);
        background: #ffffff;
        color: var(--po-muted);
        font-size: 12px;
        font-weight: 820;
        text-align: center;
    }
    .po-rail-item.ready {
        border-color: var(--po-accent-line);
        background: linear-gradient(180deg, #f8fbff 0%, var(--po-accent-soft) 100%);
        color: var(--po-blue);
    }
    .po-step {
        height: 164px;
        display: flex;
        flex-direction: column;
        border: 1px solid var(--po-line);
        border-top: 3px solid var(--po-accent-line);
        border-radius: var(--po-radius);
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        padding: 12px 12px 13px;
        box-shadow: var(--po-shadow);
        overflow: hidden;
    }
    .po-step-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 8px;
    }
    .po-step-index {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 26px;
        height: 26px;
        border-radius: var(--po-radius);
        border: 1px solid var(--po-line);
        background: #f3f6fb;
        color: var(--po-muted);
        font-size: 12px;
        font-weight: 820;
    }
    .po-step-state {
        font-size: 11px;
        font-weight: 820;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .po-step-state.green { color: var(--po-green); }
    .po-step-state.amber { color: var(--po-amber); }
    .po-step-state.blue { color: var(--po-blue); }
    .po-step:has(.po-step-state.green) { border-top-color: rgba(15,118,110,0.46); }
    .po-step:has(.po-step-state.amber) { border-top-color: rgba(180,83,9,0.42); }
    .po-step:has(.po-step-state.blue) { border-top-color: rgba(29,78,216,0.42); }
    .po-step .po-step-title {
        margin: 6px 0 8px !important;
        color: var(--po-ink);
        font-size: 18px !important;
        line-height: 1.22 !important;
        font-weight: 820;
    }
    .po-step .po-step-copy {
        margin: 0;
        color: var(--po-muted);
        font-size: 12px;
        line-height: 1.45;
        overflow-wrap: anywhere;
    }
    .po-next-action {
        margin: 10px 0 14px;
        border-left: 4px solid var(--po-accent);
        border-radius: var(--po-radius);
        border-top: 1px solid var(--po-line);
        border-right: 1px solid var(--po-line);
        border-bottom: 1px solid var(--po-line);
        background: linear-gradient(90deg, rgba(31,94,255,0.06), #ffffff 34%);
        padding: 10px 12px;
        box-shadow: var(--po-shadow);
    }
    .po-next-action strong {
        display: block;
        margin-bottom: 4px;
        color: var(--po-ink);
        font-size: 14px;
    }
    .po-next-action span {
        color: var(--po-muted);
        font-size: 13px;
    }
    .po-evidence-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
        margin: 8px 0 14px;
    }
    .po-evidence-item {
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
        padding: 12px;
        box-shadow: var(--po-shadow);
    }
    .po-evidence-value {
        color: var(--po-ink);
        font-size: 22px;
        line-height: 1;
        font-weight: 840;
    }
    .po-evidence-label {
        margin-top: 6px;
        color: var(--po-muted);
        font-size: 12px;
        font-weight: 760;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .po-ledger-row {
        display: grid;
        grid-template-columns: 72px minmax(0, 1fr);
        gap: 10px;
        padding: 8px 0;
        border-bottom: 1px solid var(--po-line);
        font-size: 12px;
    }
    .po-ledger-row:last-child { border-bottom: 0; }
    .po-ledger-key { color: var(--po-muted); font-weight: 760; }
    .po-ledger-value { color: var(--po-ink); overflow-wrap: anywhere; }
    .po-empty {
        padding: 14px;
        border: 1px dashed var(--po-line);
        border-radius: var(--po-radius);
        color: var(--po-muted);
        background: #f8fafc;
        font-size: 13px;
    }
    .stChatMessage {
        border: 1px solid var(--po-line);
        border-radius: var(--po-radius);
        background: linear-gradient(180deg, #ffffff 0%, #fbfdff 100%);
    }
    .stTextInput input, .stTextArea textarea {
        border-radius: var(--po-radius);
        border-color: var(--po-line);
        background: #ffffff;
    }
    .stButton button {
        border-radius: var(--po-radius);
        font-weight: 760;
        border-color: var(--po-line);
        color: var(--po-ink);
    }
    [data-testid="stDeployButton"] {
        display: none;
    }
    @media (max-width: 820px) {
        .po-topline {
            align-items: flex-start;
            flex-direction: column;
        }
        .po-status-stack {
            width: 100%;
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .po-title {
            font-size: 24px;
        }
        .po-loop-grid,
        .po-evidence-grid,
        .po-loop-rail {
            grid-template-columns: 1fr;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def cached_extract_document_text(file_bytes: bytes, filename: str) -> str:
    return extract_document_text(file_bytes, filename)


def get_agent_app():
    try:
        from core.workflow import agent_app
    except ModuleNotFoundError as exc:
        st.warning(f"Agent runtime dependency is not installed: {exc.name}")
        return None
    return agent_app


def get_policy_evidence(question: str) -> list[dict]:
    try:
        from core.rag_engine import retrieve_policy_evidence
    except ModuleNotFoundError as exc:
        st.warning(f"RAG runtime dependency is not installed: {exc.name}")
        return []
    return retrieve_policy_evidence(question)


def init_state() -> None:
    st.session_state.setdefault("extracted_resume_text", "")
    st.session_state.setdefault("resume_file_names", [])
    st.session_state.setdefault("thread_id", f"peopleops_session_{uuid4().hex[:8]}")
    st.session_state.setdefault("authenticated", not bool(settings.access_password))
    st.session_state.setdefault(
        "messages",
        [
            {
                "role": "assistant",
                "content": (
                    "浣犲ソ锛屾垜鏄?PeopleOps Intelligence Assistant銆備綘鍙互涓婁紶鍊欓€変汉绠€鍘嗗苟绮樿创 JD 鍋氬尮閰嶈瘎浼帮紝"
                    "涔熷彲浠ヨ闂憳宸ユ墜鍐屻€佽€冨嫟銆佹姤閿€銆佺鍒╃瓑鍒跺害闂銆?
                ),
            }
        ],
    )


def render_stream(text: str) -> None:
    placeholder = st.empty()
    displayed = ""
    for chunk in text:
        displayed += chunk
        placeholder.markdown(displayed + "鈻?)
        time.sleep(0.002)
    placeholder.markdown(text)


def pill(label: str, tone: str = "blue") -> str:
    return f'<span class="po-pill {tone}">{escape(label)}</span>'


def render_step(index: int, title: str, copy: str, state: str, tone: str) -> str:
    return f"""
    <div class="po-step">
      <div class="po-step-top">
        <span class="po-step-index">{index}</span>
        <span class="po-step-state {tone}">{escape(state)}</span>
      </div>
      <h3 class="po-step-title">{escape(title)}</h3>
      <p class="po-step-copy">{escape(copy)}</p>
    </div>
    """


def render_rail_item(label: str, ready: bool) -> str:
    state_class = "ready" if ready else ""
    return f'<div class="po-rail-item {state_class}">{escape(label)}</div>'


def latest_user_question() -> str:
    for message in reversed(st.session_state.get("messages", [])):
        if message.get("role") == "user" and message.get("content", "").strip():
            return message["content"].strip()
    return ""


def render_auto_evidence_preview() -> None:
    question = latest_user_question()
    if not question:
        st.markdown(
            """
            <div class="po-context-note">
              寮曠敤鐗囨浼氭牴鎹富宸ヤ綔鍖烘渶杩戜竴娆℃彁闂嚜鍔ㄥ埛鏂帮紱杩欓噷涓嶅啀鍗曠嫭鎻愪緵妫€绱㈠叆鍙ｃ€?            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    evidence = get_policy_evidence(question)
    if not evidence:
        st.markdown('<div class="po-context-note">鏈€杩戜竴娆℃彁闂殏鏃犲彲灞曠ず寮曠敤銆?/div>', unsafe_allow_html=True)
        return

    st.caption(f"鍩轰簬鏈€杩戞彁闂細{question[:42]}{'...' if len(question) > 42 else ''}")
    for item in evidence[:2]:
        st.markdown(
            f"""
            <div class="po-evidence-card">
              <div class="po-evidence-source">{escape(str(item["source"]))}</div>
              <div class="po-evidence-snippet">{escape(str(item["snippet"])[:420])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_runtime_signals() -> None:
    rows = [
        ("鐭ヨ瘑搴?, "Ready" if settings.policy_pdf_path.exists() else "Missing PDF"),
        ("LLM", "Configured" if settings.has_llm_config else "Degraded"),
        ("璁块棶鎺у埗", "Enabled" if settings.access_password else "Local Demo"),
        ("宸ュ叿妯″紡", settings.tool_execution_mode.upper()),
    ]
    for label, value in rows:
        left, right = st.columns([1.15, 0.85], gap="small")
        with left:
            st.caption(label)
        with right:
            st.markdown(
                f'<div style="text-align:right; font-weight:800; font-size:0.8rem; color:#111827;">{escape(value)}</div>',
                unsafe_allow_html=True,
            )


def workflow_snapshot(jd_input: str) -> dict:
    resume_count = len(st.session_state["resume_file_names"])
    has_resume = bool(st.session_state["extracted_resume_text"])
    has_jd = bool(jd_input.strip())
    interviews = list_interview_actions(limit=100)
    approvals = list_approval_requests(limit=100)
    events = read_audit_events(limit=100)
    pending_approvals = [item for item in approvals if item["status"] == "PENDING"]
    integrity = verify_audit_integrity()

    if not has_resume and not has_jd:
        next_action = "鍏堝湪宸︿晶瀵煎叆鍊欓€変汉绠€鍘嗗苟绮樿创 JD锛屽舰鎴愬彲璇勪及鐨勪笂涓嬫枃銆?
    elif not has_resume:
        next_action = "JD 宸插氨缁紱缁х画瀵煎叆绠€鍘嗗悗鍗冲彲璁?Agent 杈撳嚭鍖归厤鎶ュ憡銆?
    elif not has_jd:
        next_action = "绠€鍘嗗凡灏辩华锛涜ˉ鍏?JD 鍚庡彲鑾峰緱鏇村彲淇＄殑鍖归厤鍒ゆ柇銆?
    elif not interviews:
        next_action = "鏉愭枡宸查綈锛涘湪涓嬫柟瀵硅瘽涓姹?Agent 鍋氬€欓€変汉鍖归厤鎴栫敓鎴愬€欓€変汉璺熻繘鍔ㄤ綔銆?
    elif pending_approvals:
        next_action = "宸叉湁寰呭鍔ㄤ綔锛涘垏鍒版不鐞嗚瘉鎹〉鏌ョ湅瀹℃壒闃熷垪鍜屽璁￠摼銆?
    else:
        next_action = "闂幆宸插舰鎴愶紱鍙湪娌荤悊璇佹嵁椤靛鏍稿姩浣溿€佷骇鐗╁拰瀹¤璁板綍銆?

    steps = [
        {
            "title": "杈撳叆鏉愭枡",
            "copy": f"{resume_count} 浠界畝鍘嗭紝JD {'宸插～鍐? if has_jd else '寰呭～鍐?}銆?,
            "state": "Ready" if has_resume and has_jd else "Needs Input",
            "tone": "green" if has_resume and has_jd else "amber",
        },
        {
            "title": "Agent 鍒ゆ柇",
            "copy": "鑷姩璺敱鍒版斂绛栭棶绛斻€佺畝鍘嗗尮閰嶆垨琛屾斂鍔ㄤ綔宸ュ叿銆?,
            "state": "Online" if settings.has_llm_config else "Degraded",
            "tone": "green" if settings.has_llm_config else "amber",
        },
        {
            "title": "鎵ц鍔ㄤ綔",
            "copy": f"{len(interviews)} 鏉℃墽琛屽姩浣滐紝{len(pending_approvals)} 鏉″緟瀹¤姹傘€?,
            "state": "Active" if interviews or pending_approvals else "Waiting",
            "tone": "green" if interviews else "blue",
        },
        {
            "title": "璇佹嵁鍥炴祦",
            "copy": f"{len(events)} 鏉″璁′簨浠讹紝瀹¤閾?{'鏈夋晥' if integrity.get('valid') else '寰呭鏍?}銆?,
            "state": "Valid" if integrity.get("valid") else "Review",
            "tone": "green" if integrity.get("valid") else "amber",
        },
    ]
    return {
        "steps": steps,
        "rail": [
            ("鏀堕泦鏉愭枡", has_resume and has_jd),
            ("鐢熸垚鍒ゆ柇", settings.has_llm_config),
            ("鎵ц鍔ㄤ綔", bool(interviews or pending_approvals)),
            ("瀹¤澶嶆牳", bool(integrity.get("valid"))),
        ],
        "next_action": next_action,
        "interviews": interviews,
        "approvals": approvals,
        "pending_approvals": pending_approvals,
        "events": events,
        "integrity": integrity,
    }


def render_workflow_loop(jd_input: str) -> dict:
    snapshot = workflow_snapshot(jd_input)
    st.markdown('<div class="po-section">Closed Loop</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="po-loop-rail">'
        + "".join(render_rail_item(label, ready) for label, ready in snapshot["rail"])
        + "</div>",
        unsafe_allow_html=True,
    )
    step_cols = st.columns(4)
    for idx, step in enumerate(snapshot["steps"], start=1):
        with step_cols[idx - 1]:
            st.markdown(
                render_step(idx, step["title"], step["copy"], step["state"], step["tone"]),
                unsafe_allow_html=True,
            )
    st.markdown(
        f"""
        <div class="po-next-action">
          <strong>涓嬩竴姝ュ缓璁?/strong>
          <span>{escape(snapshot["next_action"])}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return snapshot


def render_topline() -> None:
    warnings = enterprise_warnings(settings)
    llm_tone = "green" if settings.has_llm_config else "amber"
    readiness_tone = "green" if not warnings else "amber"
    st.markdown(
        f"""
        <div class="po-topline">
          <div>
            <div class="po-kicker">HRBP Operations Console</div>
            <h1 class="po-title">{escape(settings.app_name)}</h1>
            <div class="po-subtitle">
              闈㈠悜浼佷笟鍐呴儴 PeopleOps 鐨?AI 宸ヤ綔鍙帮細涓诲璇濊礋璐ｆ彁闂笌鍔ㄤ綔锛屼晶杈规爮鍙鐞嗘潗鏂欏拰璇佹嵁銆?            </div>
          </div>
          <div class="po-status-stack">
            {pill("LLM " + ("Configured" if settings.has_llm_config else "Degraded"), llm_tone)}
            {pill("Mode " + settings.tool_execution_mode.upper(), "blue")}
            {pill("Readiness " + ("Clear" if not warnings else "Review"), readiness_tone)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_access() -> None:
    if st.session_state.get("authenticated"):
        return

    st.markdown(
        """
        <div class="po-panel">
          <div class="po-panel-title">鍙楁帶璁块棶</div>
          <p class="po-panel-copy">璇疯緭鍏ヨ闂彛浠よ繘鍏?PeopleOps Intelligence Agent銆?/p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    password = st.text_input("璁块棶鍙ｄ护", type="password")
    if st.button("杩涘叆宸ヤ綔鍙?, type="primary"):
        if verify_password(password, settings.access_password):
            st.session_state["authenticated"] = True
            write_audit_event("auth.login_success", {"session_id": st.session_state["thread_id"]})
            st.rerun()
        write_audit_event("auth.login_failed", {"session_id": st.session_state["thread_id"]})
        st.error("璁块棶鍙ｄ护涓嶆纭€?)
    st.stop()


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown('<div class="po-section">Context</div>', unsafe_allow_html=True)
        uploaded_resumes = st.file_uploader(
            "瀵煎叆绠€鍘嗘枃浠?,
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
            help="鏀寔 PDF銆乄ord DOCX銆乀XT銆丮arkdown锛屽彲涓€娆″鍏ュ浠藉€欓€変汉鏉愭枡銆?,
        )

        if uploaded_resumes:
            try:
                extracted_parts = []
                file_names = []
                with st.spinner("姝ｅ湪鎻愬彇绠€鍘嗘枃鏈?.."):
                    for uploaded_resume in uploaded_resumes:
                        text_content = cached_extract_document_text(
                            uploaded_resume.getvalue(),
                            uploaded_resume.name,
                        )
                        if text_content:
                            file_names.append(uploaded_resume.name)
                            extracted_parts.append(f"銆愭枃浠讹細{uploaded_resume.name}銆慭n{text_content}")

                combined_text = "\n\n".join(extracted_parts).strip()
                st.session_state["extracted_resume_text"] = combined_text
                st.session_state["resume_file_names"] = file_names
                if combined_text:
                    write_audit_event(
                        "resume.uploaded",
                        {
                            "session_id": st.session_state["thread_id"],
                            "filenames": file_names,
                            "content_hash": stable_hash(combined_text),
                            "char_count": len(combined_text),
                        },
                    )
                    st.success(f"宸插鍏?{len(file_names)} 涓枃浠?)
                else:
                    st.warning("鏈彁鍙栧埌鍙敤鏂囨湰锛屽彲鑳芥槸鎵弿浠躲€佸浘鐗囧瀷绠€鍘嗘垨绌烘枃浠躲€?)
            except Exception as exc:
                st.session_state["extracted_resume_text"] = ""
                st.session_state["resume_file_names"] = []
                write_audit_event(
                    "resume.upload_failed",
                    {"session_id": st.session_state["thread_id"], "error": str(exc)},
                )
                st.error(f"绠€鍘嗚В鏋愬け璐ワ細{exc}")
        else:
            st.session_state["extracted_resume_text"] = ""
            st.session_state["resume_file_names"] = []

        jd_input = st.text_area(
            "宀椾綅鎻忚堪 JD",
            height=230,
            placeholder="绮樿创宀椾綅鑱岃矗銆佷换鑱岃姹傘€佹妧鑳芥爤銆佸勾闄愯姹傜瓑淇℃伅...",
        )

        if st.session_state["extracted_resume_text"]:
            with st.expander("绠€鍘嗘枃鏈瑙?, expanded=False):
                st.text(st.session_state["extracted_resume_text"][:3000])

        st.markdown('<div class="po-section">Evidence</div>', unsafe_allow_html=True)
        render_auto_evidence_preview()

        st.markdown('<div class="po-section">Runtime</div>', unsafe_allow_html=True)
        render_runtime_signals()
        return jd_input


def render_metrics() -> None:
    interviews = list_interview_actions(limit=100)
    approvals = list_approval_requests(limit=100)
    integrity = verify_audit_integrity()
    connectors = connector_inventory()
    configured_connectors = [item for item in connectors if item["status"] == "configured"]
    session_short_id = st.session_state["thread_id"].replace("peopleops_session_", "")

    cols = st.columns(5)
    with cols[0]:
        st.metric("浼氳瘽", session_short_id)
    with cols[1]:
        st.metric("绠€鍘嗘枃浠?, len(st.session_state["resume_file_names"]))
    with cols[2]:
        st.metric("鎵ц鍔ㄤ綔", len(interviews))
    with cols[3]:
        st.metric("寰呭璇锋眰", len([item for item in approvals if item["status"] == "PENDING"]))
    with cols[4]:
        st.metric("瀹¤閾?, "Valid" if integrity.get("valid") else "Review")

    st.markdown(
        f"""
        <div class="po-panel">
          <div class="po-panel-title">Enterprise posture</div>
          <p class="po-panel-copy">
            Tenant: {escape(settings.default_tenant_id)} 路 DB: {escape(settings.database_backend)} 路 Vector: {escape(settings.vector_backend)} 路
            Connectors configured: {len(configured_connectors)}/{len(connectors)}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_governance_summary(snapshot: dict) -> None:
    connectors = connector_inventory()
    configured_connectors = [item for item in connectors if item["status"] == "configured"]
    integrity = snapshot["integrity"]
    st.markdown('<div class="po-section">Evidence Summary</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="po-evidence-grid">
          <div class="po-evidence-item">
            <div class="po-evidence-value">{len(snapshot["interviews"])}</div>
            <div class="po-evidence-label">Action Records</div>
          </div>
          <div class="po-evidence-item">
            <div class="po-evidence-value">{len(snapshot["pending_approvals"])}</div>
            <div class="po-evidence-label">Pending Approvals</div>
          </div>
          <div class="po-evidence-item">
            <div class="po-evidence-value">{integrity.get("total_events", len(snapshot["events"]))}</div>
            <div class="po-evidence-label">Audit Events</div>
          </div>
        </div>
        <div class="po-panel">
          <div class="po-panel-title">Closure status</div>
          <p class="po-panel-copy">
            Audit chain: {"valid" if integrity.get("valid") else "needs review"} 路
            Connectors configured: {len(configured_connectors)}/{len(connectors)} 路
            Tool mode: {escape(settings.tool_execution_mode)}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_connector_panel() -> None:
    st.markdown('<div class="po-section">Connector Readiness</div>', unsafe_allow_html=True)
    connectors = connector_inventory()
    for connector in connectors[:6]:
        missing = connector.get("missing_env") or []
        detail = "configured" if connector["status"] == "configured" else f"missing {len(missing)} env vars"
        st.markdown(
            f"""
            <div class="po-ledger-row">
              <div class="po-ledger-key">{escape(str(connector["category"]))}</div>
              <div class="po-ledger-value">{escape(str(connector["name"]))} 路 {escape(str(connector["capability"]))} 路 {escape(detail)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_activity_panel(snapshot: dict) -> None:
    render_governance_summary(snapshot)
    action_col, approval_col, audit_col = st.columns(3)
    with action_col:
        st.markdown('<div class="po-section">Recent Actions</div>', unsafe_allow_html=True)
        actions = snapshot["interviews"][:5]
        if actions:
            for action in actions:
                st.markdown(
                    f"""
                    <div class="po-ledger-row">
                      <div class="po-ledger-key">#{escape(str(action['id']))}</div>
                      <div class="po-ledger-value">{escape(str(action['status']))} 路 {escape(str(action['candidate_name']))} 路 {escape(str(action['interview_time']))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="po-empty">鏆傛棤鎵ц鍔ㄤ綔銆?/div>', unsafe_allow_html=True)

    with approval_col:
        st.markdown('<div class="po-section">Approval Queue</div>', unsafe_allow_html=True)
        approvals = snapshot["approvals"][:5]
        if approvals:
            for approval in approvals:
                st.markdown(
                    f"""
                    <div class="po-ledger-row">
                      <div class="po-ledger-key">#{escape(str(approval['id']))}</div>
                      <div class="po-ledger-value">{escape(str(approval['status']))} 路 {escape(str(approval['action_type']))} 路 {escape(str(approval['subject_ref']))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="po-empty">鏆傛棤寰呭鐞嗗鎵广€?/div>', unsafe_allow_html=True)

    with audit_col:
        st.markdown('<div class="po-section">Audit Trail</div>', unsafe_allow_html=True)
        events = snapshot["events"][-5:]
        if events:
            for event in reversed(events):
                st.markdown(
                    f"""
                    <div class="po-ledger-row">
                      <div class="po-ledger-key">{escape(str(event.get('event_type', 'event')))}</div>
                      <div class="po-ledger-value">{escape(str(event.get('timestamp', '')[:19]))} 路 {escape(str(event.get('actor') or 'local'))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="po-empty">鏆傛棤瀹¤浜嬩欢銆?/div>', unsafe_allow_html=True)
    render_connector_panel()


def render_primary_chat(jd_input: str) -> None:
    st.markdown(
        """
        <div class="po-agent-hero">
          <h2 class="po-agent-title">PeopleOps Intelligence Assistant</h2>
          <p class="po-agent-copy">
            缁熶竴澶勭悊鍒跺害闂瓟銆佺畝鍘?JD 鍖归厤鍜屽€欓€変汉璺熻繘鍔ㄤ綔锛涘紩鐢ㄥ拰鐣欑棔浼氬湪渚ц竟鏍忎笌娌荤悊鍖鸿嚜鍔ㄦ洿鏂般€?          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("primary_agent_prompt_form", clear_on_submit=True):
        user_input = st.text_area(
            "杈撳叆浣犵殑闂",
            placeholder="杈撳叆闂鎴栦换鍔★紝渚嬪锛氬嚭宸姤閿€鏈変粈涔堟爣鍑嗭紵杩欎唤绠€鍘嗗拰 JD 鍖归厤鍚楋紵",
            label_visibility="collapsed",
        )
        _, send_col = st.columns([5, 1])
        with send_col:
            submitted = st.form_submit_button("鍙戦€?, type="primary", use_container_width=True)

    st.markdown('<div class="po-chat-feed-label">Conversation</div>', unsafe_allow_html=True)
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if submitted and user_input.strip():
        user_input = user_input.strip()
        st.session_state.messages.append({"role": "user", "content": user_input})
        write_audit_event(
            "chat.user_message",
            {"session_id": st.session_state["thread_id"], "input_text": user_input},
        )
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            try:
                runtime = get_agent_app()
                if runtime is None:
                    raise RuntimeError("Agent runtime dependency is unavailable. Install requirements.txt to enable chat.")
                inputs = {
                    "input_text": user_input,
                    "resume_text": st.session_state["extracted_resume_text"],
                    "jd_text": jd_input.strip(),
                    "intent": "",
                    "reply": "",
                    "history": st.session_state.messages,
                }
                config = {"configurable": {"thread_id": st.session_state["thread_id"]}}
                output = runtime.invoke(inputs, config)
                full_response = output.get("reply") or "鎶辨瓑锛岀郴缁熸湭鑳界敓鎴愭湁鏁堝洖澶嶃€?
                render_stream(full_response)
                st.session_state.messages.append({"role": "assistant", "content": full_response})
                write_audit_event(
                    "chat.assistant_message",
                    {
                        "session_id": st.session_state["thread_id"],
                        "intent": output.get("intent", ""),
                        "reply_preview": full_response[:500],
                    },
                )
            except Exception as exc:
                write_audit_event(
                    "chat.error",
                    {"session_id": st.session_state["thread_id"], "error": str(exc)},
                )
                st.error(f"杩愯鍙戠敓閿欒锛歿exc}")


init_state()
require_access()
render_topline()
jd_text = render_sidebar()
render_primary_chat(jd_text)

with st.expander("Operational status", expanded=False):
    render_metrics()
    workflow_state = render_workflow_loop(jd_text)

tabs = st.tabs(["Governance Evidence"])
with tabs[0]:
    render_activity_panel(workflow_state)
