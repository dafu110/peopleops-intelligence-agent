from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import json
from pathlib import Path
import re
import smtplib
import time
from typing import Any, Dict, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from .ats import LocalATSAdapter
from .audit import write_audit_event
from .config import get_settings
from .database import (
    claim_tool_execution,
    create_tool_compensation,
    create_approval_request,
    create_interview_action,
    get_interview_action,
    get_tool_execution_by_key,
    json_loads,
    update_interview_action_status,
    update_tool_compensation,
    update_tool_execution,
)
from .security import EMAIL_RE, redact_pii, stable_hash


try:
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
CN_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

CANDIDATE_STAGE_STATUSES = {
    "CONTACTED",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_COMPLETED",
    "PASSED",
    "REJECTED",
    "OFFER_PENDING",
    "HIRED",
    "WITHDRAWN",
}


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    status: str
    message: str
    metadata: Dict[str, Any]

    def to_markdown(self) -> str:
        details = "\n".join([f"- {key}: {value}" for key, value in self.metadata.items()])
        if details:
            details = f"\n\n{details}"
        return f"**[{self.status}] {self.tool_name}**\n\n{self.message}{details}"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Any
    schema_version: str = "1.0"
    mutating: bool = True
    timeout_seconds: Optional[float] = None
    max_retries: Optional[int] = None
    compensation_handler: Any = None


@dataclass(frozen=True)
class ToolError:
    code: str
    message: str
    retryable: bool
    remediation: str


TOOL_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> ToolSpec:
    TOOL_REGISTRY[spec.name] = spec
    return spec


def list_registered_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "schema_version": spec.schema_version,
            "mutating": spec.mutating,
            "compensatable": spec.compensation_handler is not None,
        }
        for spec in sorted(TOOL_REGISTRY.values(), key=lambda item: item.name)
    ]


def _tool_idempotency_key(tool_name: str, args: Dict[str, Any], scope: Dict[str, str]) -> str:
    payload = {"tool_name": tool_name, "args": args, "scope": scope}
    return f"{tool_name}:{stable_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True))}"


def _result_from_payload(payload: Dict[str, Any]) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_name=str(payload.get("tool_name", "")),
        status=str(payload.get("status", "UNKNOWN")),
        message=str(payload.get("message", "")),
        metadata=dict(payload.get("metadata") or {}),
    )


def _invoke_with_timeout(handler: Any, args: Dict[str, Any], timeout_seconds: float) -> ToolExecutionResult:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(handler, **args)
    try:
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    *,
    idempotency_key: Optional[str] = None,
    created_by: str = "local-admin",
    tenant_id: str = "default",
    org_id: str = "default-org",
    department_id: str = "peopleops",
) -> ToolExecutionResult:
    settings = get_settings()
    spec = TOOL_REGISTRY.get(tool_name)
    if spec is None:
        raise ValueError(f"Unknown tool: {tool_name}")

    scoped_args = {
        **args,
        "created_by": created_by,
        "tenant_id": tenant_id,
        "org_id": org_id,
        "department_id": department_id,
    }
    scope = {"tenant_id": tenant_id, "org_id": org_id, "department_id": department_id}
    key = idempotency_key or _tool_idempotency_key(tool_name, scoped_args, scope)
    request_payload = {
        "tool_name": tool_name,
        "schema_version": spec.schema_version,
        "args": {
            name: redact_pii(str(value)) if isinstance(value, str) else value
            for name, value in scoped_args.items()
        },
    }
    existing, claimed = claim_tool_execution(
        tool_name=tool_name,
        idempotency_key=key,
        tenant_id=tenant_id,
        org_id=org_id,
        department_id=department_id,
        request=request_payload,
    )
    if not claimed and existing.get("status") == "SUCCEEDED":
        write_audit_event("tool.idempotent_replay", {"tool_name": tool_name, "idempotency_key": key, **scope})
        return _result_from_payload(json_loads(existing.get("response_json")))
    if not claimed and existing.get("status") == "RUNNING":
        error = ToolError(
            code="duplicate_in_flight",
            message="A matching tool execution is already running.",
            retryable=True,
            remediation="Retry after the original execution completes.",
        )
        return ToolExecutionResult(
            tool_name=tool_name,
            status="RETRY_LATER",
            message=error.message,
            metadata={"idempotency_key": key, "error": asdict(error), **scope},
        )

    attempts = 0
    max_retries = spec.max_retries if spec.max_retries is not None else settings.tool_default_retries
    if spec.mutating:
        max_retries = 0
    timeout_seconds = spec.timeout_seconds if spec.timeout_seconds is not None else settings.tool_default_timeout_seconds
    last_error: Optional[ToolError] = None

    for attempt in range(max_retries + 1):
        attempts = attempt + 1
        started = time.perf_counter()
        try:
            result = _invoke_with_timeout(spec.handler, scoped_args, timeout_seconds)
            metadata = {
                **result.metadata,
                "idempotency_key": key,
                "attempts": attempts,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "schema_version": spec.schema_version,
            }
            result = ToolExecutionResult(result.tool_name, result.status, result.message, metadata)
            update_tool_execution(idempotency_key=key, status="SUCCEEDED", attempts=attempts, response=asdict(result))
            write_audit_event(
                "tool.execution_succeeded",
                {"tool_name": tool_name, "idempotency_key": key, "attempts": attempts, **scope},
            )
            return result
        except FutureTimeoutError:
            last_error = ToolError(
                code="timeout",
                message=f"Tool execution exceeded {timeout_seconds:.1f}s.",
                retryable=attempt < max_retries,
                remediation="Retry with the same idempotency key or increase TOOL_DEFAULT_TIMEOUT_SECONDS.",
            )
        except Exception as exc:
            last_error = ToolError(
                code=exc.__class__.__name__,
                message=str(exc),
                retryable=attempt < max_retries,
                remediation="Inspect tool inputs, connector credentials, and audit logs before retrying.",
            )
        if attempt < max_retries:
            time.sleep(min(0.1 * (2**attempt), 1.0))

    assert last_error is not None
    update_tool_execution(idempotency_key=key, status="FAILED", attempts=attempts, error=asdict(last_error))
    write_audit_event(
        "tool.execution_failed",
        {"tool_name": tool_name, "idempotency_key": key, "attempts": attempts, "error": asdict(last_error), **scope},
    )
    return ToolExecutionResult(
        tool_name=tool_name,
        status="FAILED",
        message=last_error.message,
        metadata={"idempotency_key": key, "attempts": attempts, "error": asdict(last_error), **scope},
    )


def compensate_tool_execution(
    idempotency_key: str,
    *,
    reason: str,
    requested_by: str = "local-admin",
    tenant_id: str = "default",
) -> ToolExecutionResult:
    execution = get_tool_execution_by_key(idempotency_key)
    if execution is None or execution.get("tenant_id") != tenant_id:
        raise KeyError(f"Tool execution not found: {idempotency_key}")
    if execution.get("status") != "SUCCEEDED":
        raise ValueError(f"Only SUCCEEDED executions can be compensated: {execution.get('status')}")

    tool_name = str(execution["tool_name"])
    spec = TOOL_REGISTRY.get(tool_name)
    if spec is None or spec.compensation_handler is None:
        raise ValueError(f"Tool does not support compensation: {tool_name}")

    scope = {
        "tenant_id": str(execution["tenant_id"]),
        "org_id": str(execution["org_id"]),
        "department_id": str(execution["department_id"]),
    }
    compensation_id = create_tool_compensation(
        tool_execution_key=idempotency_key,
        tool_name=tool_name,
        requested_by=requested_by,
        reason=reason,
        **scope,
    )
    try:
        response_payload = json_loads(execution.get("response_json"))
        result = spec.compensation_handler(response_payload, reason=reason, requested_by=requested_by, **scope)
        update_tool_compensation(compensation_id, status="SUCCEEDED", response=asdict(result))
        write_audit_event(
            "tool.compensation_succeeded",
            {
                "tool_name": tool_name,
                "idempotency_key": idempotency_key,
                "compensation_id": compensation_id,
                "reason": reason,
                **scope,
            },
        )
        return result
    except Exception as exc:
        error = ToolError(
            code=exc.__class__.__name__,
            message=str(exc),
            retryable=False,
            remediation="Review the original execution, generated artifacts, and external system state manually.",
        )
        update_tool_compensation(compensation_id, status="FAILED", error=asdict(error))
        write_audit_event(
            "tool.compensation_failed",
            {
                "tool_name": tool_name,
                "idempotency_key": idempotency_key,
                "compensation_id": compensation_id,
                "error": asdict(error),
                **scope,
            },
        )
        return ToolExecutionResult(
            tool_name=f"{tool_name}.compensate",
            status="FAILED",
            message=error.message,
            metadata={"compensation_id": compensation_id, "idempotency_key": idempotency_key, "error": asdict(error), **scope},
        )


def _safe_slug(value: str) -> str:
    return stable_hash(value or str(uuid4()))


def _extract_email(*values: str) -> Optional[str]:
    for value in values:
        match = EMAIL_RE.search(value or "")
        if match:
            return match.group(0)
    return None


def _cn_number_to_int(value: str) -> Optional[int]:
    if value.isdigit():
        return int(value)
    if value in CN_NUMBERS:
        return CN_NUMBERS[value]
    if value.startswith("十") and len(value) == 2:
        return 10 + CN_NUMBERS.get(value[1], 0)
    if value.endswith("十") and len(value) == 2:
        return CN_NUMBERS.get(value[0], 0) * 10
    if "十" in value and len(value) == 3:
        return CN_NUMBERS.get(value[0], 0) * 10 + CN_NUMBERS.get(value[2], 0)
    return None


def parse_interview_window(interview_time: str, *, now: Optional[datetime] = None) -> Optional[tuple[datetime, datetime]]:
    text = (interview_time or "").strip()
    if not text:
        return None

    current = now.astimezone(LOCAL_TZ) if now else datetime.now(LOCAL_TZ)
    date_value: Optional[datetime] = None

    iso_match = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    cn_date_match = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        date_value = datetime(year, month, day, tzinfo=LOCAL_TZ)
    elif cn_date_match:
        month, day = map(int, cn_date_match.groups())
        date_value = datetime(current.year, month, day, tzinfo=LOCAL_TZ)
    elif "后天" in text:
        date_value = current + timedelta(days=2)
    elif "明天" in text:
        date_value = current + timedelta(days=1)
    elif "今天" in text or "今日" in text:
        date_value = current

    time_match = re.search(r"(\d{1,2})\s*[:点时]\s*(\d{1,2})?", text)
    cn_time_match = re.search(r"([一二两三四五六七八九十]{1,3})\s*[点时]", text)
    hour: Optional[int] = None
    minute = 0
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
    elif cn_time_match:
        hour = _cn_number_to_int(cn_time_match.group(1))

    if hour is None or date_value is None:
        return None

    if any(flag in text for flag in ("下午", "晚上", "傍晚")) and hour < 12:
        hour += 12
    if "中午" in text and hour < 11:
        hour += 12

    start = date_value.replace(hour=hour, minute=minute, second=0, microsecond=0)
    end = start + timedelta(hours=1)
    return start, end


def _ics_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _escape_ics(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _build_email_message(candidate_name: str, interview_time: str, candidate_email: Optional[str]) -> EmailMessage:
    settings = get_settings()
    message = EmailMessage()
    message["Subject"] = f"面试邀约 - {candidate_name}"
    message["From"] = settings.smtp_from
    message["To"] = candidate_email or "candidate@example.com"
    message.set_content(
        f"""您好，{candidate_name}：

感谢您关注我们的岗位。现邀请您参加面试，时间为：{interview_time}。
请提前准备个人项目、AI Agent/RAG 相关经历，并回复确认是否方便。

PeopleOps Intelligence Agent
"""
    )
    return message


def _write_email_draft(candidate_name: str, interview_time: str, candidate_email: Optional[str]) -> Path:
    settings = get_settings()
    settings.email_draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = settings.email_draft_dir / f"interview_{_safe_slug(candidate_name + interview_time)}.eml"

    message = _build_email_message(candidate_name, interview_time, candidate_email)
    draft_path.write_text(message.as_string(), encoding="utf-8")
    return draft_path


def _send_email(candidate_name: str, interview_time: str, candidate_email: Optional[str]) -> str:
    settings = get_settings()
    if not settings.smtp_host:
        return "not_configured"
    if not candidate_email:
        return "missing_recipient"

    message = _build_email_message(candidate_name, interview_time, candidate_email)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return "sent"


def _write_calendar_event(candidate_name: str, interview_time: str) -> Path:
    settings = get_settings()
    settings.calendar_dir.mkdir(parents=True, exist_ok=True)
    event_id = _safe_slug(candidate_name + interview_time)
    event_path = settings.calendar_dir / f"interview_{event_id}.ics"
    window = parse_interview_window(interview_time)
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if window:
        start, end = window
        schedule_lines = (
            f"DTSTART;TZID=Asia/Shanghai:{_ics_datetime(start)}\n"
            f"DTEND;TZID=Asia/Shanghai:{_ics_datetime(end)}\n"
        )
    else:
        schedule_lines = "X-REQUESTED-TIME:" + _escape_ics(interview_time) + "\n"

    event_path.write_text(
        f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PeopleOps Intelligence Agent//Interview Scheduler//CN
CALSCALE:GREGORIAN
BEGIN:VEVENT
UID:{event_id}@peopleops-intelligence.local
DTSTAMP:{dtstamp}
{schedule_lines}SUMMARY:{_escape_ics("Interview with " + candidate_name)}
DESCRIPTION:{_escape_ics("Interview arranged by PeopleOps Intelligence Agent. Requested time: " + interview_time)}
END:VEVENT
END:VCALENDAR
""",
        encoding="utf-8",
    )
    return event_path


def schedule_interview(
    candidate_name: str,
    interview_time: str,
    *,
    candidate_email: Optional[str] = None,
    created_by: str = "local-admin",
    tenant_id: str = "default",
    org_id: str = "default-org",
    department_id: str = "peopleops",
) -> ToolExecutionResult:
    settings = get_settings()
    mode = settings.tool_execution_mode.lower()
    safe_candidate_name = redact_pii(candidate_name)
    safe_interview_time = redact_pii(interview_time)
    candidate_email = candidate_email or _extract_email(candidate_name, interview_time)
    safe_candidate_email = redact_pii(candidate_email or "")

    email_draft_path: Optional[Path] = None
    calendar_event_path: Optional[Path] = None
    ats_export_path: Optional[Path] = None
    approval_request_id: Optional[int] = None
    smtp_status = "not_attempted"
    status = "DRY_RUN"

    if mode in {"approval", "pending_approval"}:
        status = "PENDING_APPROVAL"
    elif mode in {"local", "live"}:
        email_draft_path = _write_email_draft(candidate_name, interview_time, candidate_email)
        calendar_event_path = _write_calendar_event(candidate_name, interview_time)
        status = "PERSISTED"
        if mode == "live":
            smtp_status = _send_email(candidate_name, interview_time, candidate_email)

    action_id = create_interview_action(
        tenant_id=tenant_id,
        org_id=org_id,
        department_id=department_id,
        candidate_name=safe_candidate_name,
        interview_time=safe_interview_time,
        status=status,
        email_draft_path=email_draft_path,
        calendar_event_path=calendar_event_path,
        created_by=created_by,
    )
    if status == "PENDING_APPROVAL":
        approval_request_id = create_approval_request(
            tenant_id=tenant_id,
            org_id=org_id,
            department_id=department_id,
            action_type="interview_invitation",
            subject_ref=f"interview_action:{action_id}",
            requested_by=created_by,
            payload={
                "candidate_ref": stable_hash(candidate_name),
                "candidate_email": safe_candidate_email,
                "interview_time": safe_interview_time,
                "required_actions": list(settings.approval_required_actions),
            },
        )
    if mode in {"local", "live"}:
        ats_export_path = LocalATSAdapter().sync_interview_action(
            {
                "action_id": action_id,
                "tenant_id": tenant_id,
                "org_id": org_id,
                "department_id": department_id,
                "candidate_name": safe_candidate_name,
                "candidate_email": safe_candidate_email,
                "interview_time": safe_interview_time,
                "status": status,
                "email_draft_path": str(email_draft_path) if email_draft_path else None,
                "calendar_event_path": str(calendar_event_path) if calendar_event_path else None,
                "created_by": created_by,
            }
        )

    result = ToolExecutionResult(
        tool_name="schedule_interview",
        status=status,
        message=f"已为候选人【{safe_candidate_name}】生成面试邀约动作，并写入本地 ATS 数据库。",
        metadata={
            "action_id": action_id,
            "interview_time": safe_interview_time,
            "candidate_email": safe_candidate_email or "not_provided",
            "execution_mode": mode,
            "email_draft_path": str(email_draft_path) if email_draft_path else "dry_run",
            "calendar_event_path": str(calendar_event_path) if calendar_event_path else "dry_run",
            "ats_export_path": str(ats_export_path) if ats_export_path else "dry_run",
            "smtp_status": smtp_status,
            "ats_record": "interview_actions",
            "approval_request_id": approval_request_id or "not_required",
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
        },
    )

    write_audit_event(
        "tool.schedule_interview",
        {
            "candidate_ref": stable_hash(candidate_name),
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
            "interview_time": safe_interview_time,
            "candidate_email": safe_candidate_email,
            "execution_mode": mode,
            "approval_request_id": approval_request_id,
            "smtp_status": smtp_status,
            "result": asdict(result),
        },
    )
    return result


def update_candidate_stage(
    action_id: int,
    next_status: str,
    *,
    reason: str = "",
    created_by: str = "local-admin",
    tenant_id: str = "default",
    org_id: str = "default-org",
    department_id: str = "peopleops",
) -> ToolExecutionResult:
    settings = get_settings()
    normalized_status = (next_status or "").strip().upper()
    if normalized_status not in CANDIDATE_STAGE_STATUSES:
        raise ValueError(
            "next_status must be one of: " + ", ".join(sorted(CANDIDATE_STAGE_STATUSES))
        )

    current = get_interview_action(int(action_id), tenant_id=tenant_id)
    if current is None:
        raise KeyError(f"Interview action not found: {action_id}")

    safe_reason = redact_pii(reason or "")
    mode = settings.tool_execution_mode.lower()
    approval_request_id: Optional[int] = None
    status = "DRY_RUN"
    updated = current

    if mode in {"approval", "pending_approval"}:
        status = "PENDING_APPROVAL"
        approval_request_id = create_approval_request(
            tenant_id=tenant_id,
            org_id=org_id,
            department_id=department_id,
            action_type="candidate_stage_update",
            subject_ref=f"interview_action:{action_id}",
            requested_by=created_by,
            payload={
                "action_id": action_id,
                "candidate_ref": stable_hash(str(current.get("candidate_name", ""))),
                "previous_status": current.get("status", "UNKNOWN"),
                "next_status": normalized_status,
                "reason": safe_reason,
                "required_actions": list(settings.approval_required_actions),
            },
        )
    elif mode in {"local", "live"}:
        updated = update_interview_action_status(
            int(action_id),
            tenant_id=tenant_id,
            status=normalized_status,
        )
        status = "PERSISTED"

    result = ToolExecutionResult(
        tool_name="update_candidate_stage",
        status=status,
        message=f"Candidate action #{action_id} stage update prepared: {current.get('status')} -> {normalized_status}.",
        metadata={
            "action_id": int(action_id),
            "previous_status": current.get("status", "UNKNOWN"),
            "next_status": normalized_status,
            "current_status": updated.get("status", current.get("status", "UNKNOWN")),
            "execution_mode": mode,
            "approval_request_id": approval_request_id or "not_required",
            "reason": safe_reason or "not_provided",
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
        },
    )

    write_audit_event(
        "tool.update_candidate_stage",
        {
            "action_id": int(action_id),
            "candidate_ref": stable_hash(str(current.get("candidate_name", ""))),
            "previous_status": current.get("status", "UNKNOWN"),
            "next_status": normalized_status,
            "execution_mode": mode,
            "approval_request_id": approval_request_id,
            "reason": safe_reason,
            **{"tenant_id": tenant_id, "org_id": org_id, "department_id": department_id},
        },
    )
    return result


def compensate_update_candidate_stage(
    original_result: Dict[str, Any],
    *,
    reason: str,
    requested_by: str,
    tenant_id: str,
    org_id: str,
    department_id: str,
) -> ToolExecutionResult:
    metadata = dict(original_result.get("metadata") or {})
    action_id = metadata.get("action_id")
    previous_status = metadata.get("previous_status")
    if not isinstance(action_id, int) or not previous_status:
        raise ValueError("Original update_candidate_stage result is missing action_id or previous_status.")

    updated = update_interview_action_status(action_id, tenant_id=tenant_id, status=str(previous_status))
    result = ToolExecutionResult(
        tool_name="update_candidate_stage.compensate",
        status="COMPENSATED",
        message=f"Candidate action #{action_id} was restored to {previous_status}.",
        metadata={
            "action_id": action_id,
            "reason": redact_pii(reason),
            "requested_by": requested_by,
            "restored_status": updated["status"],
            "previous_tool_status": original_result.get("status", "UNKNOWN"),
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
        },
    )
    write_audit_event(
        "tool.update_candidate_stage.compensated",
        {
            "action_id": action_id,
            "reason": reason,
            "requested_by": requested_by,
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
        },
    )
    return result


def compensate_schedule_interview(
    original_result: Dict[str, Any],
    *,
    reason: str,
    requested_by: str,
    tenant_id: str,
    org_id: str,
    department_id: str,
) -> ToolExecutionResult:
    metadata = dict(original_result.get("metadata") or {})
    action_id = metadata.get("action_id")
    if not isinstance(action_id, int):
        raise ValueError("Original schedule_interview result does not include an action_id.")

    updated = update_interview_action_status(action_id, tenant_id=tenant_id, status="COMPENSATED")
    result = ToolExecutionResult(
        tool_name="schedule_interview.compensate",
        status="COMPENSATED",
        message=f"Interview action #{action_id} was marked as compensated for audit review.",
        metadata={
            "action_id": action_id,
            "reason": redact_pii(reason),
            "requested_by": requested_by,
            "previous_status": original_result.get("status", "UNKNOWN"),
            "current_status": updated["status"],
            "email_draft_path": metadata.get("email_draft_path", "not_recorded"),
            "calendar_event_path": metadata.get("calendar_event_path", "not_recorded"),
            "ats_export_path": metadata.get("ats_export_path", "not_recorded"),
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
        },
    )
    write_audit_event(
        "tool.schedule_interview.compensated",
        {
            "action_id": action_id,
            "reason": reason,
            "requested_by": requested_by,
            "tenant_id": tenant_id,
            "org_id": org_id,
            "department_id": department_id,
        },
    )
    return result


register_tool(
    ToolSpec(
        name="schedule_interview",
        description="Create an interview invitation action with optional email draft, calendar artifact, ATS sync, and approval gate.",
        handler=schedule_interview,
        schema_version="1.0",
        mutating=True,
        compensation_handler=compensate_schedule_interview,
    )
)

register_tool(
    ToolSpec(
        name="update_candidate_stage",
        description="Update an existing candidate interview action stage with approval-mode support and compensation.",
        handler=update_candidate_stage,
        schema_version="1.0",
        mutating=True,
        compensation_handler=compensate_update_candidate_stage,
    )
)
