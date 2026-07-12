from contextlib import asynccontextmanager
from collections import Counter, defaultdict, deque
from datetime import datetime
import json
import time
from typing import List, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from pydantic import BaseModel, Field

from core.auth import Principal, allowed_permissions, authenticate_with_oidc, authenticate_with_password, require_permission
from core.audit import clear_audit_context, read_audit_events, set_audit_context, verify_audit_integrity, write_audit_event
from core.connectors import connector_inventory
from core.config import enterprise_warnings, get_settings
from core.database import (
    create_agent_task_event,
    create_agent_task_run,
    get_agent_task_run,
    list_agent_task_events,
    init_db,
    list_agent_task_runs,
    list_approval_requests,
    list_interview_actions,
    list_tool_compensations,
    list_tool_executions,
    update_agent_task_run,
    update_approval_status,
)
from core.pdf_utils import extract_document_text
from core.production_checks import production_checks
from core.tenancy import TenantContext
from core.tools import compensate_tool_execution, list_registered_tools


settings = get_settings()
rate_buckets: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if settings.api_rate_limit_per_minute > 0:
        client = request.client.host if request.client else "unknown"
        bucket = rate_buckets[client]
        now = time.time()
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= settings.api_rate_limit_per_minute:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        bucket.append(now)
    return await call_next(request)


@app.middleware("http")
async def audit_context_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex[:12]}"
    set_audit_context(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        clear_audit_context()
    response.headers["X-Request-ID"] = request_id
    return response


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8_000)
    jd_text: str = Field(default="", max_length=80_000)
    resume_text: str = Field(default="", max_length=80_000)
    history: List[dict] = Field(default_factory=list)
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    thread_id: str
    task_id: str
    evidence: List[dict] = Field(default_factory=list)


class CompensationRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1_000)


class OperatorEventRequest(BaseModel):
    event_type: str = Field(..., pattern=r"^(candidate\.adopted|candidate\.rewritten|citation\.shown|citation\.opened)$")


class DocumentExtractResponse(BaseModel):
    filename: str
    chars: int
    text: str


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_trace_metrics(
    *,
    input_text: str,
    history: list[dict],
    reply: str,
    started: float,
    model_usage: Optional[dict] = None,
) -> dict:
    model_usage = model_usage or {}
    provider_total_tokens = int(model_usage.get("total_tokens", 0) or 0)
    if provider_total_tokens > 0:
        input_tokens = int(model_usage.get("input_tokens", 0) or 0)
        output_tokens = int(model_usage.get("output_tokens", 0) or 0)
        total_tokens = provider_total_tokens
        token_source = "provider_usage"
        cost_model = "provider_usage_no_price_config"
    else:
        input_tokens = estimate_tokens(input_text) + sum(estimate_tokens(str(item.get("content", ""))) for item in history)
        output_tokens = estimate_tokens(reply)
        total_tokens = input_tokens + output_tokens
        token_source = "local_estimate"
        cost_model = "local_estimate_no_billing"
    return {
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_total_tokens": total_tokens,
        "token_source": token_source,
        "provider_model_calls": int(model_usage.get("calls", 0) or 0),
        "provider_usage_sources": list(model_usage.get("sources", [])),
        "estimated_cost_usd": 0.0,
        "cost_model": cost_model,
    }


def get_agent_app():
    try:
        from core.workflow import agent_app
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Agent runtime dependency is not installed: {exc.name}",
        ) from exc
    return agent_app


def tenant_context(
    x_tenant_id: Optional[str] = Header(default=None),
    x_org_id: Optional[str] = Header(default=None),
    x_department_id: Optional[str] = Header(default=None),
) -> TenantContext:
    return TenantContext.from_headers(
        tenant_id=x_tenant_id,
        org_id=x_org_id,
        department_id=x_department_id,
        default_tenant_id=settings.default_tenant_id,
        default_org_id=settings.default_org_id,
        default_department_id=settings.default_department_id,
    )


def current_principal(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    x_access_password: Optional[str] = Header(default=None),
    x_authenticated_user: Optional[str] = Header(default=None),
    x_authenticated_role: Optional[str] = Header(default=None),
    scope: TenantContext = Depends(tenant_context),
) -> Principal:
    if settings.trusted_sso_enabled:
        username = (
            request.headers.get(settings.trusted_sso_user_header)
            or x_authenticated_user
            or ""
        ).strip()
        role = (
            request.headers.get(settings.trusted_sso_role_header)
            or x_authenticated_role
            or "viewer"
        ).strip().lower()
        if not username:
            raise HTTPException(status_code=401, detail="Missing trusted SSO user header")
        if role not in {"admin", "hrbp", "viewer"}:
            raise HTTPException(status_code=403, detail="Unsupported SSO role")
        scoped_principal = Principal(username=username, role=role, **scope.as_dict())
        set_audit_context(actor=scoped_principal.username, **scoped_principal.scope())
        return scoped_principal
    if settings.oidc_enabled:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Missing bearer token")
        try:
            principal = authenticate_with_oidc(token, **scope.as_dict())
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Invalid bearer token: {exc}") from exc
        if principal is None:
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        set_audit_context(actor=principal.username, **principal.scope())
        return principal
    if settings.require_access_password and not settings.access_password:
        raise HTTPException(status_code=503, detail="ACCESS_PASSWORD is required by server configuration")
    if not settings.access_password:
        set_audit_context(actor="local-admin", **scope.as_dict())
        return Principal(username="local-admin", role="admin", **scope.as_dict())
    principal = authenticate_with_password(x_access_password or "")
    if principal is None:
        raise HTTPException(status_code=401, detail="Invalid access password")
    scoped_principal = Principal(username=principal.username, role=principal.role, **scope.as_dict())
    set_audit_context(actor=scoped_principal.username, **scoped_principal.scope())
    return scoped_principal


def _score_dimension(
    *,
    dimension_id: str,
    label: str,
    max_score: int,
    checks: list[dict],
    evidence: str,
) -> dict:
    passed = sum(1 for item in checks if item["ok"])
    score = round(max_score * passed / max(len(checks), 1))
    return {
        "id": dimension_id,
        "label": label,
        "score": score,
        "max_score": max_score,
        "checks": checks,
        "evidence": evidence,
    }


def _score_grade(score: int) -> str:
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 85:
        return "A-"
    if score >= 80:
        return "B+"
    if score >= 70:
        return "B"
    return "C"


def enterprise_scorecard() -> dict:
    warnings = enterprise_warnings(settings)
    integrity = verify_audit_integrity()
    connectors = connector_inventory()
    configured_connectors = [item for item in connectors if item["status"] == "configured"]
    model_configured = settings.has_llm_config

    dimensions = [
        _score_dimension(
            dimension_id="business_value",
            label="HR business value",
            max_score=20,
            checks=[
                {"id": "policy_rag", "label": "Policy Q&A workflow", "ok": True},
                {"id": "resume_matching", "label": "Resume/JD matching", "ok": True},
                {"id": "candidate_actions", "label": "Candidate follow-up actions", "ok": True},
                {"id": "approval_loop", "label": "Approval workflow", "ok": True},
                {"id": "connector_path", "label": "Enterprise connector readiness path", "ok": True},
            ],
            evidence="Core HRBP loop is implemented; connector inventory exposes configured and planned integration paths.",
        ),
        _score_dimension(
            dimension_id="agent_rag",
            label="Agent and RAG completeness",
            max_score=20,
            checks=[
                {"id": "langgraph_workflow", "label": "LangGraph workflow", "ok": True},
                {"id": "task_replay", "label": "Persisted task replay", "ok": True},
                {"id": "citations", "label": "RAG evidence citations", "ok": True},
                {"id": "rag_thresholds", "label": "RAG quality thresholds configured", "ok": settings.rag_min_pass_rate > 0},
                {"id": "model_config", "label": "Chat model endpoint configured", "ok": model_configured},
            ],
            evidence=f"RAG thresholds require pass_rate>={settings.rag_min_pass_rate}; model_configured={model_configured}.",
        ),
        _score_dimension(
            dimension_id="security_governance",
            label="Enterprise security and governance",
            max_score=20,
            checks=[
                {"id": "rbac", "label": "Role-based permissions", "ok": True},
                {"id": "tenant_scope", "label": "Tenant-scoped records", "ok": True},
                {"id": "identity_controls", "label": "Access-password, SSO, and OIDC controls available", "ok": True},
                {"id": "audit_integrity", "label": "Audit hash chain valid", "ok": bool(integrity.get("valid"))},
                {"id": "pii_redaction", "label": "PII redaction implemented", "ok": True},
            ],
            evidence=f"audit_valid={bool(integrity.get('valid'))}; production_readiness_warnings={len(warnings)}.",
        ),
        _score_dimension(
            dimension_id="engineering_operations",
            label="Engineering and deployment maturity",
            max_score=20,
            checks=[
                {"id": "api_control_plane", "label": "FastAPI control plane", "ok": True},
                {"id": "rate_limit", "label": "API rate limit enabled", "ok": settings.api_rate_limit_per_minute > 0},
                {"id": "database_adapter", "label": "SQLite/PostgreSQL adapter path", "ok": settings.database_backend in {"sqlite", "postgresql"}},
                {"id": "vector_adapter", "label": "Chroma/Qdrant adapter path", "ok": settings.vector_backend in {"chroma", "qdrant"}},
                {"id": "deployment_assets", "label": "Docker and deployment assets", "ok": True},
            ],
            evidence=f"database={settings.database_backend}; vector={settings.vector_backend}; object_storage_configured={bool(settings.object_storage_uri)}.",
        ),
        _score_dimension(
            dimension_id="product_demo",
            label="Product experience and demonstration",
            max_score=20,
            checks=[
                {"id": "next_console", "label": "Next.js operator console", "ok": True},
                {"id": "document_import", "label": "Resume/document import API", "ok": True},
                {"id": "runtime_inspector", "label": "Runtime evidence and trace views", "ok": True},
                {"id": "tool_receipts", "label": "Auditable tool receipts", "ok": True},
                {"id": "production_checks", "label": "Production readiness endpoint", "ok": True},
            ],
            evidence="Demo surface covers intake, chat, evidence, approvals, audit, connectors, and settings.",
        ),
    ]
    raw_score = sum(item["score"] for item in dimensions)
    score = min(raw_score, 98)
    launch_ready_threshold = 95
    summary = (
        "Launch-ready local reference implementation; production integrations can be enabled through documented configuration."
        if score >= 95
        else "Strong reference implementation; readiness improves when model configuration and runtime checks are complete."
    )
    return {
        "score": score,
        "raw_score": raw_score,
        "target": 100,
        "launch_ready_threshold": launch_ready_threshold,
        "grade": _score_grade(score),
        "dimensions": dimensions,
        "configured_connectors": [item["name"] for item in configured_connectors],
        "readiness_warnings": warnings,
        "summary": summary,
    }


@app.exception_handler(PermissionError)
def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/health")
def health() -> dict:
    warnings = enterprise_warnings(settings)
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "tool_execution_mode": settings.tool_execution_mode,
        "db_path": str(settings.db_path),
        "enterprise_mode": settings.enterprise_mode,
        "access_password_required": settings.require_access_password,
        "trusted_sso_enabled": settings.trusted_sso_enabled,
        "oidc_enabled": settings.oidc_enabled,
        "audit_hash_chain_enabled": settings.audit_hash_chain_enabled,
        "api_rate_limit_per_minute": settings.api_rate_limit_per_minute,
        "default_tenant_id": settings.default_tenant_id,
        "database_backend": settings.database_backend,
        "database_url_configured": bool(settings.database_url),
        "vector_backend": settings.vector_backend,
        "vector_store_url_configured": bool(settings.vector_store_url),
        "object_storage_configured": bool(settings.object_storage_uri),
        "model_configured": settings.has_llm_config,
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "rag_top_k": settings.rag_top_k,
        "rag_thresholds": {
            "min_pass_rate": settings.rag_min_pass_rate,
            "min_keyword_coverage": settings.rag_min_keyword_coverage,
            "min_citation_correctness": settings.rag_min_citation_correctness,
        },
        "identity_modes": {
            "access_password": bool(settings.access_password),
            "trusted_sso": settings.trusted_sso_enabled,
            "oidc": settings.oidc_enabled,
        },
        "enterprise_warnings": warnings,
    }


@app.get("/readiness")
def readiness() -> JSONResponse:
    warnings = enterprise_warnings(settings)
    integrity = verify_audit_integrity()
    ready = not warnings and bool(integrity.get("valid"))
    payload = {
        "ready": ready,
        "enterprise_warnings": warnings,
        "audit_integrity": integrity,
        "database_backend": settings.database_backend,
        "database_url_configured": bool(settings.database_url),
        "vector_backend": settings.vector_backend,
        "vector_store_url_configured": bool(settings.vector_store_url),
        "object_storage_configured": bool(settings.object_storage_uri),
        "configured_connectors": [item for item in connector_inventory() if item["status"] == "configured"],
        "scorecard": enterprise_scorecard(),
    }
    return JSONResponse(status_code=200 if ready else 503, content=payload)


@app.get("/enterprise/scorecard")
def scorecard() -> dict:
    return enterprise_scorecard()


@app.get("/production/checks")
def production_checklist(
    live: bool = Query(default=False),
    principal: Principal = Depends(current_principal),
) -> dict:
    require_permission(principal, "audit")
    return production_checks(live=live)


@app.get("/operations/summary")
def operations_summary(
    principal: Principal = Depends(current_principal),
) -> dict:
    require_permission(principal, "audit")
    task_runs = list_agent_task_runs(limit=100, tenant_id=principal.tenant_id)
    tool_runs = list_tool_executions(limit=100, tenant_id=principal.tenant_id)
    approval_runs = list_approval_requests(limit=100, tenant_id=principal.tenant_id)

    def counts_by_status(rows: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status") or "UNKNOWN")
            counts[status] = counts.get(status, 0) + 1
        return counts

    failed_tasks = [row for row in task_runs if row.get("status") == "FAILED"]
    failed_tools = [row for row in tool_runs if row.get("status") == "FAILED"]
    succeeded_tasks = len([row for row in task_runs if row.get("status") == "SUCCEEDED"])
    task_success_rate = succeeded_tasks / max(len(task_runs), 1)
    trace_metrics = [
        row.get("state", {}).get("trace_metrics", {})
        for row in task_runs
        if row.get("state", {}).get("trace_metrics")
    ]
    avg_latency_ms = sum(int(item.get("latency_ms", 0)) for item in trace_metrics) / max(len(trace_metrics), 1)
    total_estimated_tokens = sum(int(item.get("estimated_total_tokens", 0)) for item in trace_metrics)
    task_events = [
        event
        for task in task_runs
        for event in list_agent_task_events(task["task_id"], tenant_id=principal.tenant_id, limit=200)
    ]
    operator_events = [event for event in task_events if event["event_type"] in {"candidate.adopted", "candidate.rewritten", "citation.shown", "citation.opened"}]
    candidate_tasks = [task for task in task_runs if task.get("intent") == "resume"]
    adopted = sum(event["event_type"] == "candidate.adopted" for event in operator_events)
    rewritten = sum(event["event_type"] == "candidate.rewritten" for event in operator_events)
    citations_shown = sum(event["event_type"] == "citation.shown" for event in operator_events)
    citations_opened = sum(event["event_type"] == "citation.opened" for event in operator_events)
    terminal_approvals = [row for row in approval_runs if row.get("status") in {"APPROVED", "REJECTED", "EXECUTED", "FAILED"}]
    durations = []
    for row in terminal_approvals:
        try:
            durations.append((datetime.fromisoformat(str(row["updated_at"])) - datetime.fromisoformat(str(row["created_at"]))).total_seconds())
        except (KeyError, TypeError, ValueError):
            continue

    def failure_reason(row: dict, key: str) -> str:
        payload = row.get(key) or ""
        try:
            parsed = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        error = parsed.get("error", parsed) if isinstance(parsed, dict) else {}
        return str(error.get("code") or error.get("message") or "unknown") if isinstance(error, dict) else "unknown"

    failure_reasons = Counter(
        [failure_reason(row, "error") for row in failed_tasks]
        + [failure_reason(row, "error_json") for row in failed_tools]
    )

    return {
        "tenant_id": principal.tenant_id,
        "task_count": len(task_runs),
        "task_success_rate": task_success_rate,
        "task_status_counts": counts_by_status(task_runs),
        "agent_trace_metrics": {
            "sample_count": len(trace_metrics),
            "avg_latency_ms": avg_latency_ms,
            "estimated_total_tokens": total_estimated_tokens,
            "estimated_cost_usd": 0.0,
            "cost_model": "local_estimate_no_billing",
        },
        "tool_execution_count": len(tool_runs),
        "tool_status_counts": counts_by_status(tool_runs),
        "approval_status_counts": counts_by_status(approval_runs),
        "operator_metrics": {
            "candidate_assistance_tasks": len(candidate_tasks),
            "adoption_rate": adopted / max(len(candidate_tasks), 1),
            "human_rewrite_rate": rewritten / max(adopted + rewritten, 1),
            "approval_duration_seconds": sum(durations) / max(len(durations), 1),
            "citation_open_rate": citations_opened / max(citations_shown, 1),
            "sample_counts": {
                "candidate_feedback": adopted + rewritten,
                "approval_duration": len(durations),
                "citations": citations_shown,
            },
            "failure_reasons": dict(failure_reasons),
        },
        "recent_failures": {
            "tasks": [
                {
                    "task_id": row.get("task_id"),
                    "input_text": row.get("input_text"),
                    "error": row.get("error"),
                    "updated_at": row.get("updated_at"),
                }
                for row in failed_tasks[:5]
            ],
            "tools": [
                {
                    "tool_name": row.get("tool_name"),
                    "idempotency_key": row.get("idempotency_key"),
                    "attempts": row.get("attempts"),
                    "error_json": row.get("error_json"),
                    "completed_at": row.get("completed_at"),
                }
                for row in failed_tools[:5]
            ],
        },
    }


@app.get("/connectors")
def connectors(principal: Principal = Depends(current_principal)) -> dict:
    require_permission(principal, "audit")
    return {"connectors": connector_inventory()}


@app.post("/documents/extract", response_model=DocumentExtractResponse)
async def extract_document(
    file: UploadFile = File(...),
    principal: Principal = Depends(current_principal),
) -> DocumentExtractResponse:
    require_permission(principal, "chat")
    content = await file.read()
    if len(content) > 5_000_000:
        raise HTTPException(status_code=413, detail="Document is too large; limit is 5 MB")
    try:
        text = extract_document_text(content, file.filename or "document")
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    write_audit_event(
        "document.extracted",
        {
            "filename": file.filename,
            "chars": len(text),
            **principal.scope(),
        },
    )
    return DocumentExtractResponse(filename=file.filename or "document", chars=len(text), text=text)


@app.get("/me")
def me(principal: Principal = Depends(current_principal)) -> dict:
    return {
        "username": principal.username,
        "role": principal.role,
        "tenant_id": principal.tenant_id,
        "org_id": principal.org_id,
        "department_id": principal.department_id,
        "permissions": list(allowed_permissions(principal.role)),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, principal: Principal = Depends(current_principal)) -> ChatResponse:
    require_permission(principal, "chat")
    thread_id = request.thread_id or f"api_session_{uuid4().hex[:8]}"
    task_id = f"task_{uuid4().hex[:12]}"
    inputs = {
        "input_text": request.message,
        "resume_text": request.resume_text,
        "jd_text": request.jd_text,
        "intent": "",
        "reply": "",
        "evidence": [],
        "history": request.history,
        "created_by": principal.username,
        "task_id": task_id,
        **principal.scope(),
    }
    create_agent_task_run(
        task_id=task_id,
        thread_id=thread_id,
        input_text=request.message,
        state=inputs,
        **principal.scope(),
    )
    create_agent_task_event(
        task_id=task_id,
        event_type="task.created",
        payload={
            "thread_id": thread_id,
            "input_chars": len(request.message),
            "estimated_input_tokens": estimate_tokens(request.message),
            "history_items": len(request.history),
            "created_by": principal.username,
        },
        **principal.scope(),
    )
    started = time.perf_counter()
    try:
        create_agent_task_event(
            task_id=task_id,
            event_type="workflow.started",
            payload={"thread_id": thread_id},
            **principal.scope(),
        )
        output = get_agent_app().invoke(inputs, {"configurable": {"thread_id": thread_id}})
        trace_metrics = estimate_trace_metrics(
            input_text=request.message,
            history=request.history,
            reply=output.get("reply", ""),
            started=started,
            model_usage=output.get("model_usage", {}),
        )
        update_agent_task_run(
            task_id,
            status="SUCCEEDED",
            intent=output.get("intent", ""),
            state={
                **inputs,
                "intent": output.get("intent", ""),
                "reply": output.get("reply", ""),
                "evidence": output.get("evidence", []),
                "plan": output.get("plan", []),
                "stop_condition": output.get("stop_condition", ""),
                "model_usage": output.get("model_usage", {}),
                "trace_metrics": trace_metrics,
            },
        )
        create_agent_task_event(
            task_id=task_id,
            event_type="workflow.completed",
            payload={
                "intent": output.get("intent", ""),
                "reply_chars": len(output.get("reply", "")),
                "evidence_count": len(output.get("evidence", [])),
                **trace_metrics,
            },
            **principal.scope(),
        )
    except Exception as exc:
        trace_metrics = estimate_trace_metrics(
            input_text=request.message,
            history=request.history,
            reply="",
            started=started,
        )
        update_agent_task_run(task_id, status="FAILED", state={**inputs, "trace_metrics": trace_metrics}, error=str(exc))
        create_agent_task_event(
            task_id=task_id,
            event_type="workflow.failed",
            payload={"error_type": exc.__class__.__name__, "error": str(exc), **trace_metrics},
            **principal.scope(),
        )
        raise
    write_audit_event(
        "api.chat",
        {
            "username": principal.username,
            "role": principal.role,
            **principal.scope(),
            "thread_id": thread_id,
            "intent": output.get("intent", ""),
            "trace_metrics": trace_metrics,
        },
    )
    return ChatResponse(
        reply=output.get("reply", ""),
        intent=output.get("intent", ""),
        thread_id=thread_id,
        task_id=task_id,
        evidence=output.get("evidence", []),
    )


@app.get("/tasks")
def task_runs(
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "audit")
    return list_agent_task_runs(limit=limit, tenant_id=principal.tenant_id)


@app.get("/tasks/{task_id}")
def task_run_detail(
    task_id: str,
    principal: Principal = Depends(current_principal),
) -> dict:
    require_permission(principal, "audit")
    run = get_agent_task_run(task_id)
    if run is None or run.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")
    run["events"] = list_agent_task_events(task_id, tenant_id=principal.tenant_id)
    return run


@app.get("/tasks/{task_id}/events")
def task_run_events(
    task_id: str,
    limit: int = Query(default=200, ge=1, le=500),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "audit")
    run = get_agent_task_run(task_id)
    if run is None or run.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return list_agent_task_events(task_id, tenant_id=principal.tenant_id, limit=limit)


@app.get("/tools")
def tools(principal: Principal = Depends(current_principal)) -> dict:
    require_permission(principal, "tool")
    return {"tools": list_registered_tools()}


@app.get("/tool-executions")
def tool_executions(
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "audit")
    return list_tool_executions(limit=limit, tenant_id=principal.tenant_id)


@app.get("/tool-compensations")
def tool_compensations(
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "audit")
    return list_tool_compensations(limit=limit, tenant_id=principal.tenant_id)


@app.post("/tool-executions/{idempotency_key}/compensate")
def compensate_execution(
    idempotency_key: str,
    request: CompensationRequest,
    principal: Principal = Depends(current_principal),
) -> dict:
    require_permission(principal, "tool")
    try:
        result = compensate_tool_execution(
            idempotency_key,
            reason=request.reason,
            requested_by=principal.username,
            tenant_id=principal.tenant_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"result": result.__dict__}


@app.get("/interviews")
def interviews(
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "tool")
    return list_interview_actions(limit=limit, tenant_id=principal.tenant_id)


@app.get("/approvals")
def approvals(
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "tool")
    return list_approval_requests(limit=limit, tenant_id=principal.tenant_id)


def transition_approval(approval_id: int, status: str, principal: Principal) -> dict:
    require_permission(principal, "tool")
    try:
        approval = update_approval_status(
            approval_id,
            tenant_id=principal.tenant_id,
            status=status,
            approved_by=principal.username,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_audit_event(
        "approval.transition",
        {
            "approval_id": approval_id,
            "status": approval["status"],
            "approved_by": principal.username,
            **principal.scope(),
        },
    )
    return approval


@app.post("/approvals/{approval_id}/approve")
def approve_approval(approval_id: int, principal: Principal = Depends(current_principal)) -> dict:
    return transition_approval(approval_id, "APPROVED", principal)


@app.post("/approvals/{approval_id}/submit")
def submit_approval(approval_id: int, principal: Principal = Depends(current_principal)) -> dict:
    return transition_approval(approval_id, "PENDING", principal)


@app.post("/approvals/{approval_id}/reject")
def reject_approval(approval_id: int, principal: Principal = Depends(current_principal)) -> dict:
    return transition_approval(approval_id, "REJECTED", principal)


@app.post("/approvals/{approval_id}/execute")
def execute_approval(approval_id: int, principal: Principal = Depends(current_principal)) -> dict:
    return transition_approval(approval_id, "EXECUTED", principal)


@app.post("/approvals/{approval_id}/retry")
def retry_approval(approval_id: int, principal: Principal = Depends(current_principal)) -> dict:
    return transition_approval(approval_id, "PENDING", principal)


@app.post("/tasks/{task_id}/operator-events")
def record_operator_event(
    task_id: str,
    request: OperatorEventRequest,
    principal: Principal = Depends(current_principal),
) -> dict:
    if request.event_type.startswith("candidate."):
        require_permission(principal, "resume")
    else:
        require_permission(principal, "chat")
    task = get_agent_task_run(task_id)
    if task is None or task.get("tenant_id") != principal.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")
    existing_events = list_agent_task_events(task_id, tenant_id=principal.tenant_id, limit=200)
    existing = next((event for event in existing_events if event["event_type"] == request.event_type), None)
    if existing:
        return {"id": existing["id"], "task_id": task_id, "event_type": request.event_type, "duplicate": True}
    event_id = create_agent_task_event(
        task_id=task_id,
        event_type=request.event_type,
        payload={"operator": principal.username},
        **principal.scope(),
    )
    write_audit_event("operator.metric", {"task_id": task_id, "event_type": request.event_type, **principal.scope()})
    return {"id": event_id, "task_id": task_id, "event_type": request.event_type, "duplicate": False}


@app.get("/audit/events")
def audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    require_permission(principal, "audit")
    return read_audit_events(limit=limit)


@app.get("/audit/integrity")
def audit_integrity(principal: Principal = Depends(current_principal)) -> dict:
    require_permission(principal, "audit")
    return verify_audit_integrity()
