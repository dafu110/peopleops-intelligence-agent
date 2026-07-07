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
                    "你好，我是 PeopleOps Intelligence Assistant。你可以上传候选人简历并粘贴 JD 做匹配评估，"
                    "也可以询问员工手册、考勤、报销、福利等制度问题。"
                ),
            }
        ],
    )


def render_stream(text: str) -> None:
    placeholder = st.empty()
    displayed = ""
    for chunk in text:
        displayed += chunk
        placeholder.markdown(displayed + "▌")
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
              引用片段会根据主工作区最近一次提问自动刷新；这里不再单独提供检索入口。
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    evidence = get_policy_evidence(question)
    if not evidence:
        st.markdown('<div class="po-context-note">最近一次提问暂无可展示引用。</div>', unsafe_allow_html=True)
        return

    st.caption(f"基于最近提问：{question[:42]}{'...' if len(question) > 42 else ''}")
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
        ("知识库", "Ready" if settings.policy_pdf_path.exists() else "Missing PDF"),
        ("LLM", "Configured" if settings.has_llm_config else "Degraded"),
        ("访问控制", "Enabled" if settings.access_password else "Local Demo"),
        ("工具模式", settings.tool_execution_mode.upper()),
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
        next_action = "先在左侧导入候选人简历并粘贴 JD，形成可评估的上下文。"
    elif not has_resume:
        next_action = "JD 已就绪；继续导入简历后即可让 Agent 输出匹配报告。"
    elif not has_jd:
        next_action = "简历已就绪；补充 JD 后可获得更可信的匹配判断。"
    elif not interviews:
        next_action = "材料已齐；在下方对话中要求 Agent 做候选人匹配或生成候选人跟进动作。"
    elif pending_approvals:
        next_action = "已有待审动作；切到治理证据页查看审批队列和审计链。"
    else:
        next_action = "闭环已形成；可在治理证据页复核动作、产物和审计记录。"

    steps = [
        {
            "title": "输入材料",
            "copy": f"{resume_count} 份简历，JD {'已填写' if has_jd else '待填写'}。",
            "state": "Ready" if has_resume and has_jd else "Needs Input",
            "tone": "green" if has_resume and has_jd else "amber",
        },
        {
            "title": "Agent 判断",
            "copy": "自动路由到政策问答、简历匹配或行政动作工具。",
            "state": "Online" if settings.has_llm_config else "Degraded",
            "tone": "green" if settings.has_llm_config else "amber",
        },
        {
            "title": "执行动作",
            "copy": f"{len(interviews)} 条执行动作，{len(pending_approvals)} 条待审请求。",
            "state": "Active" if interviews or pending_approvals else "Waiting",
            "tone": "green" if interviews else "blue",
        },
        {
            "title": "证据回流",
            "copy": f"{len(events)} 条审计事件，审计链{'有效' if integrity.get('valid') else '待复核'}。",
            "state": "Valid" if integrity.get("valid") else "Review",
            "tone": "green" if integrity.get("valid") else "amber",
        },
    ]
    return {
        "steps": steps,
        "rail": [
            ("收集材料", has_resume and has_jd),
            ("生成判断", settings.has_llm_config),
            ("执行动作", bool(interviews or pending_approvals)),
            ("审计复核", bool(integrity.get("valid"))),
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
          <strong>下一步建议</strong>
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
              面向企业内部 PeopleOps 的 AI 工作台：主对话负责提问与动作，侧边栏只管理材料和证据。
            </div>
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
          <div class="po-panel-title">受控访问</div>
          <p class="po-panel-copy">请输入访问口令进入 PeopleOps Intelligence Agent。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    password = st.text_input("访问口令", type="password")
    if st.button("进入工作台", type="primary"):
        if verify_password(password, settings.access_password):
            st.session_state["authenticated"] = True
            write_audit_event("auth.login_success", {"session_id": st.session_state["thread_id"]})
            st.rerun()
        write_audit_event("auth.login_failed", {"session_id": st.session_state["thread_id"]})
        st.error("访问口令不正确。")
    st.stop()


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown('<div class="po-section">Context</div>', unsafe_allow_html=True)
        uploaded_resumes = st.file_uploader(
            "导入简历文件",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
            help="支持 PDF、Word DOCX、TXT、Markdown，可一次导入多份候选人材料。",
        )

        if uploaded_resumes:
            try:
                extracted_parts = []
                file_names = []
                with st.spinner("正在提取简历文本..."):
                    for uploaded_resume in uploaded_resumes:
                        text_content = cached_extract_document_text(
                            uploaded_resume.getvalue(),
                            uploaded_resume.name,
                        )
                        if text_content:
                            file_names.append(uploaded_resume.name)
                            extracted_parts.append(f"【文件：{uploaded_resume.name}】\n{text_content}")

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
                    st.success(f"已导入 {len(file_names)} 个文件")
                else:
                    st.warning("未提取到可用文本，可能是扫描件、图片型简历或空文件。")
            except Exception as exc:
                st.session_state["extracted_resume_text"] = ""
                st.session_state["resume_file_names"] = []
                write_audit_event(
                    "resume.upload_failed",
                    {"session_id": st.session_state["thread_id"], "error": str(exc)},
                )
                st.error(f"简历解析失败：{exc}")
        else:
            st.session_state["extracted_resume_text"] = ""
            st.session_state["resume_file_names"] = []

        jd_input = st.text_area(
            "岗位描述 JD",
            height=230,
            placeholder="粘贴岗位职责、任职要求、技能栈、年限要求等信息...",
        )

        if st.session_state["extracted_resume_text"]:
            with st.expander("简历文本预览", expanded=False):
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
        st.metric("会话", session_short_id)
    with cols[1]:
        st.metric("简历文件", len(st.session_state["resume_file_names"]))
    with cols[2]:
        st.metric("执行动作", len(interviews))
    with cols[3]:
        st.metric("待审请求", len([item for item in approvals if item["status"] == "PENDING"]))
    with cols[4]:
        st.metric("审计链", "Valid" if integrity.get("valid") else "Review")

    st.markdown(
        f"""
        <div class="po-panel">
          <div class="po-panel-title">Enterprise posture</div>
          <p class="po-panel-copy">
            Tenant: {escape(settings.default_tenant_id)} · DB: {escape(settings.database_backend)} · Vector: {escape(settings.vector_backend)} ·
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
                      <div class="po-ledger-value">{escape(str(approval['status']))} · {escape(str(approval['action_type']))} · {escape(str(approval['subject_ref']))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="po-empty">暂无待处理审批。</div>', unsafe_allow_html=True)

    with audit_col:
        st.markdown('<div class="po-section">Audit Trail</div>', unsafe_allow_html=True)
        events = snapshot["events"][-5:]
        if events:
            for event in reversed(events):
                st.markdown(
                    f"""
                    <div class="po-ledger-row">
                      <div class="po-ledger-key">{escape(str(event.get('event_type', 'event')))}</div>
                      <div class="po-ledger-value">{escape(str(event.get('timestamp', '')[:19]))} · {escape(str(event.get('actor') or 'local'))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="po-empty">暂无审计事件。</div>', unsafe_allow_html=True)
    render_connector_panel()


def render_primary_chat(jd_input: str) -> None:
    st.markdown(
        """
        <div class="po-agent-hero">
          <h2 class="po-agent-title">PeopleOps Intelligence Assistant</h2>
          <p class="po-agent-copy">
            统一处理制度问答、简历/JD 匹配和候选人跟进动作；引用和留痕会在侧边栏与治理区自动更新。
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("primary_agent_prompt_form", clear_on_submit=True):
        user_input = st.text_area(
            "输入你的问题",
            placeholder="输入问题或任务，例如：出差报销有什么标准？这份简历和 JD 匹配吗？",
            label_visibility="collapsed",
        )
        _, send_col = st.columns([5, 1])
        with send_col:
            submitted = st.form_submit_button("发送", type="primary", use_container_width=True)

    st.markdown('<div class="po-chat-feed-label">对话记录</div>', unsafe_allow_html=True)
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
                full_response = output.get("reply") or "抱歉，系统未能生成有效回复。"
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
                st.error(f"运行发生错误：{exc}")


init_state()
require_access()
render_topline()
jd_text = render_sidebar()
render_primary_chat(jd_text)

with st.expander("运行状态", expanded=False):
    render_metrics()
    workflow_state = render_workflow_loop(jd_text)

tabs = st.tabs(["治理证据"])
with tabs[0]:
    render_activity_panel(workflow_state)
