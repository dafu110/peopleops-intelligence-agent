from typing import Dict, List, Literal, TypedDict

from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .audit import write_audit_event
from .config import get_chat_model
from .database import create_agent_task_event
from .matcher import analyze_resume
from .rag_engine import ask_rag_with_evidence
from .security import redact_messages, redact_pii
from .tools import execute_tool


Intent = Literal["action_tool", "resume", "rag"]


class AgentState(TypedDict, total=False):
    input_text: str
    resume_text: str
    jd_text: str
    intent: str
    reply: str
    evidence: List[Dict[str, str]]
    history: List[Dict[str, str]]
    plan: List[Dict[str, str]]
    stop_condition: str
    model_usage: Dict[str, object]
    created_by: str
    tenant_id: str
    org_id: str
    department_id: str
    task_id: str


ACTION_KEYWORDS = [
    "邮件",
    "发件",
    "邀约",
    "通知",
    "发通知",
    "录用",
    "安排",
    "面试",
    "推进",
    "通过",
    "拒绝",
    "淘汰",
    "offer",
    "入职",
    "状态",
    "阶段",
]
RESUME_KEYWORDS = [
    "简历",
    "匹配",
    "评估",
    "候选人",
    "jd",
    "职位",
    "react",
    "vue",
    "python",
    "前端",
    "后端",
    "开发",
    "技术",
    "能力",
    "学过",
    "自学",
    "如果他",
    "要是",
]


def _record_task_event(state: AgentState, event_type: str, payload: Dict[str, object] | None = None) -> None:
    task_id = state.get("task_id", "")
    if not task_id:
        return
    create_agent_task_event(
        task_id=task_id,
        event_type=event_type,
        payload=payload or {},
        tenant_id=state.get("tenant_id", "default"),
        org_id=state.get("org_id", "default-org"),
        department_id=state.get("department_id", "peopleops"),
    )


def _usage_from_message(message: object, *, label: str) -> Dict[str, object]:
    usage = getattr(message, "usage_metadata", None) or {}
    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") if isinstance(response_metadata, dict) else {}
    input_tokens = int(usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or token_usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or token_usage.get("total_tokens") or input_tokens + output_tokens)
    if total_tokens <= 0:
        return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "sources": []}
    return {
        "calls": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "sources": [label],
    }


def _merge_model_usage(*items: Dict[str, object] | None) -> Dict[str, object]:
    merged = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "sources": []}
    sources: list[str] = []
    for item in items:
        if not item:
            continue
        merged["calls"] = int(merged["calls"]) + int(item.get("calls", 0))
        merged["input_tokens"] = int(merged["input_tokens"]) + int(item.get("input_tokens", 0))
        merged["output_tokens"] = int(merged["output_tokens"]) + int(item.get("output_tokens", 0))
        merged["total_tokens"] = int(merged["total_tokens"]) + int(item.get("total_tokens", 0))
        sources.extend([str(source) for source in item.get("sources", [])])
    merged["sources"] = sorted(set(sources))
    return merged


@tool
def schedule_interview_tool(candidate_name: str, interview_time: str, candidate_email: str = "") -> str:
    """当用户要求安排面试、发送面试邀约或通知候选人时调用，可提取候选人邮箱。"""
    return execute_tool(
        "schedule_interview",
        {
            "candidate_name": candidate_name,
            "interview_time": interview_time,
            "candidate_email": candidate_email or None,
        },
    ).to_markdown()


@tool
def update_candidate_stage_tool(action_id: int, next_status: str, reason: str = "") -> str:
    """当用户要求更新候选人面试动作状态、推进、拒绝、录用或标记 offer 时调用。"""
    return execute_tool(
        "update_candidate_stage",
        {
            "action_id": action_id,
            "next_status": next_status,
            "reason": reason,
        },
    ).to_markdown()


def keyword_intent(text: str) -> Intent:
    text_lower = text.lower()
    if any(keyword in text_lower for keyword in ACTION_KEYWORDS):
        return "action_tool"
    if any(keyword.lower() in text_lower for keyword in RESUME_KEYWORDS):
        return "resume"
    return "rag"


def _format_history(history: List[Dict[str, str]], limit: int = 6) -> str:
    safe_history = redact_messages(history[-limit:])
    if not safe_history:
        return "无"

    lines = []
    for msg in safe_history:
        role = "用户" if msg.get("role") == "user" else "助手"
        content = str(msg.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "无"


def parse_intent(state: AgentState):
    text = state.get("input_text", "").strip()
    history = state.get("history", [])

    system_prompt = """你是企业智能 HR Agent 的中央意图路由器。
请根据当前用户输入与历史对话，将意图分类为以下三类之一：

action_tool: 用户要执行行政动作，例如发邮件、发面试邀约、通知候选人、安排面试、录用。
resume: 用户要评估简历、对比 JD、筛选候选人，或延续上文追问候选人的技能、风险、评分变化。
rag: 用户询问公司制度、考勤、报销、请假、福利、企业文化等知识库内容。

你必须只输出 action_tool、resume、rag 三个单词之一。"""

    user_content = f"""【历史对话】
{_format_history(history)}

【当前用户输入】
{redact_pii(text)}

请输出分类结果："""

    try:
        llm = get_chat_model(temperature=0.0)
        response = llm.invoke([("system", system_prompt), ("user", user_content)])
        model_usage = _usage_from_message(response, label="intent_router")
        intent_result = response.content.strip().lower()

        if "action_tool" in intent_result:
            intent = "action_tool"
        elif "resume" in intent_result:
            intent = "resume"
        elif "rag" in intent_result:
            intent = "rag"
        else:
            intent = keyword_intent(text)
    except Exception as exc:
        print(f"[Router fallback] {exc}")
        intent = keyword_intent(text)
        model_usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "sources": []}

    write_audit_event("router.intent", {"input_text": text, "intent": intent})
    _record_task_event(state, "intent.parsed", {"intent": intent})
    return {"intent": intent, "model_usage": _merge_model_usage(state.get("model_usage"), model_usage)}


def build_execution_plan(intent: str, state: AgentState) -> tuple[List[Dict[str, str]], str]:
    if intent == "action_tool":
        return (
            [
                {"step": "select_governed_tool", "status": "pending", "description": "Choose schedule_interview or update_candidate_stage from the user request."},
                {"step": "extract_tool_args", "status": "pending", "description": "Extract candidate, email, interview time, action id, or target status."},
                {"step": "execute_governed_tool", "status": "pending", "description": "Run the selected tool with tenant scope, idempotency, and audit logging."},
                {"step": "return_tool_receipt", "status": "pending", "description": "Return the persisted action, approval, or missing-field guidance."},
            ],
            "Stop after one governed tool attempt or a clear missing-information response.",
        )
    if intent == "resume":
        resume_present = bool(state.get("resume_text", "").strip())
        return (
            [
                {"step": "validate_resume_context", "status": "ready" if resume_present else "blocked", "description": "Confirm resume text is available before scoring."},
                {"step": "score_resume_against_jd", "status": "pending", "description": "Generate structured score, advantages, and risks."},
                {"step": "surface_hiring_risks", "status": "pending", "description": "Call out missing information instead of inventing candidate history."},
            ],
            "Stop after a structured evaluation or a missing-resume instruction.",
        )
    return (
        [
            {"step": "retrieve_policy_evidence", "status": "pending", "description": "Search the enterprise policy index for relevant chunks."},
            {"step": "answer_from_sources", "status": "pending", "description": "Answer only from retrieved policy evidence."},
            {"step": "attach_citations", "status": "pending", "description": "Return evidence snippets and source labels for review."},
        ],
        "Stop after cited answer generation or a no-context response.",
    )


def prepare_execution_plan(state: AgentState):
    intent = state.get("intent", "rag")
    plan, stop_condition = build_execution_plan(intent, state)
    write_audit_event(
        "agent.plan",
        {
            "intent": intent,
            "plan_steps": [item["step"] for item in plan],
            "stop_condition": stop_condition,
        },
    )
    _record_task_event(
        state,
        "plan.created",
        {
            "intent": intent,
            "plan_steps": [item["step"] for item in plan],
            "stop_condition": stop_condition,
        },
    )
    return {"plan": plan, "stop_condition": stop_condition}


def handle_rag(state: AgentState):
    _record_task_event(state, "rag.started", {"question_chars": len(state.get("input_text", ""))})
    result = ask_rag_with_evidence(state["input_text"])
    _record_task_event(
        state,
        "rag.completed",
        {"evidence_count": len(result.get("evidence", [])), "reply_chars": len(result.get("reply", ""))},
    )
    return {
        "reply": result["reply"],
        "evidence": result.get("evidence", []),
    }


def handle_resume(state: AgentState):
    _record_task_event(
        state,
        "resume.started",
        {"resume_chars": len(state.get("resume_text", "")), "jd_chars": len(state.get("jd_text", ""))},
    )
    resume_content = state.get("resume_text", "").strip()
    jd_text = state.get("jd_text", "").strip()
    user_msg = state.get("input_text", "").strip()

    if not resume_content:
        _record_task_event(state, "resume.blocked", {"reason": "missing_resume"})
        return {
            "reply": "检测到尚未上传候选人简历。请先在左侧上传 PDF 简历，再发起简历评估。"
        }

    if not jd_text:
        jd_text = user_msg

    resume_with_context = (
        f"{redact_pii(resume_content)}\n\n"
        f"【本轮用户问题或补充条件】\n{redact_pii(user_msg) or '无'}"
    )
    result = analyze_resume(resume_text=resume_with_context, jd_text=redact_pii(jd_text))

    write_audit_event(
        "resume.analysis",
        {
            "input_text": user_msg,
            "score": result.get("score", 0),
            "pros_count": len(result.get("pros", [])),
            "cons_count": len(result.get("cons", [])),
        },
    )

    _record_task_event(
        state,
        "resume.completed",
        {"score": result.get("score", 0), "pros_count": len(result.get("pros", [])), "cons_count": len(result.get("cons", []))},
    )

    pros = "\n".join([f"{idx}. {item}" for idx, item in enumerate(result["pros"], start=1)])
    cons = "\n".join([f"{idx}. {item}" for idx, item in enumerate(result["cons"], start=1)])

    return {
        "reply": f"""### 候选人综合评估报告

**综合匹配度：{result.get("score", 0)} / 100**

#### 核心优势
{pros}

#### 风险与待确认项
{cons}
"""
    }


def handle_action_tool(state: AgentState):
    user_msg = state["input_text"]
    _record_task_event(state, "tool.started", {"tool_name": "schedule_interview|update_candidate_stage"})

    try:
        llm = get_chat_model(temperature=0.0)
        llm_with_tools = llm.bind_tools([schedule_interview_tool, update_candidate_stage_tool])
        ai_msg = llm_with_tools.invoke(
            f"""用户当前说的话：{redact_pii(user_msg)}。
如果需要发面试邀约，请调用 schedule_interview_tool 并提取候选人姓名、邮箱和面试时间。
如果需要更新候选人状态，请调用 update_candidate_stage_tool；action_id 必须来自用户明确给出的动作编号，next_status 只能使用 CONTACTED、INTERVIEW_SCHEDULED、INTERVIEW_COMPLETED、PASSED、REJECTED、OFFER_PENDING、HIRED、WITHDRAWN 之一。"""
        )
        model_usage = _merge_model_usage(state.get("model_usage"), _usage_from_message(ai_msg, label="tool_selector"))

        if ai_msg.tool_calls:
            tool_call = ai_msg.tool_calls[0]
            args = tool_call["args"]
            selected_tool = "update_candidate_stage" if "update_candidate_stage" in tool_call["name"] else "schedule_interview"
            result = execute_tool(
                selected_tool,
                args,
                created_by=state.get("created_by", "local-admin"),
                tenant_id=state.get("tenant_id", "default"),
                org_id=state.get("org_id", "default-org"),
                department_id=state.get("department_id", "peopleops"),
            )
            _record_task_event(
                state,
                "tool.completed",
                {
                    "tool_name": selected_tool,
                    "status": result.status,
                    "idempotency_key": result.metadata.get("idempotency_key"),
                },
            )
            return {"reply": result.to_markdown(), "model_usage": model_usage}
    except Exception as exc:
        write_audit_event("tool.error", {"input_text": user_msg, "error": str(exc)})
        _record_task_event(state, "tool.failed", {"tool_name": "schedule_interview|update_candidate_stage", "error": str(exc)})
        return {"reply": f"已识别到行政动作意图，但工具调用失败：{exc}"}

    return {
        "reply": "已识别到行政动作意图，但缺少必要信息。安排面试请补充候选人姓名和时间；更新状态请补充动作编号 action_id 和目标状态。",
        "model_usage": state.get("model_usage", {}),
    }


def finalize_response(state: AgentState):
    reply = state.get("reply", "")
    evidence = state.get("evidence", [])
    plan = state.get("plan", [])
    _record_task_event(
        state,
        "response.finalized",
        {
            "intent": state.get("intent", ""),
            "reply_chars": len(reply),
            "evidence_count": len(evidence),
            "plan_steps": len(plan),
            "stop_condition": state.get("stop_condition", ""),
        },
    )
    write_audit_event(
        "agent.response_finalized",
        {
            "intent": state.get("intent", ""),
            "reply_chars": len(reply),
            "evidence_count": len(evidence),
            "plan_steps": len(plan),
        },
    )
    return {"reply": reply, "evidence": evidence, "model_usage": state.get("model_usage", {})}


def router(state: AgentState):
    if state["intent"] == "action_tool":
        return "tool_node"
    if state["intent"] == "resume":
        return "resume_node"
    return "rag_node"


workflow = StateGraph(AgentState)
workflow.add_node("intent_node", parse_intent)
workflow.add_node("plan_node", prepare_execution_plan)
workflow.add_node("rag_node", handle_rag)
workflow.add_node("resume_node", handle_resume)
workflow.add_node("tool_node", handle_action_tool)
workflow.add_node("finalize_node", finalize_response)

workflow.set_entry_point("intent_node")
workflow.add_edge("intent_node", "plan_node")
workflow.add_conditional_edges(
    "plan_node",
    router,
    {
        "tool_node": "tool_node",
        "resume_node": "resume_node",
        "rag_node": "rag_node",
    },
)
workflow.add_edge("rag_node", "finalize_node")
workflow.add_edge("resume_node", "finalize_node")
workflow.add_edge("tool_node", "finalize_node")
workflow.add_edge("finalize_node", END)

agent_app = workflow.compile(checkpointer=MemorySaver())
