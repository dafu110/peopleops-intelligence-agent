import os
import importlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from core.audit import read_audit_events, verify_audit_integrity, write_audit_event
from core.auth import Principal, has_permission
from core.config import enterprise_warnings, get_settings
from core.database import list_approval_requests, list_interview_actions, list_tool_compensations, update_approval_status
from core.matcher import normalize_analysis
from core.pdf_utils import extract_document_text
from core.security import hash_password, redact_payload, redact_pii, verify_password
from core.tools import (
    ToolExecutionResult,
    ToolSpec,
    compensate_tool_execution,
    execute_tool,
    list_registered_tools,
    parse_interview_window,
    register_tool,
    schedule_interview,
    update_candidate_stage,
)
from core.tenancy import TenantContext


class MatcherNormalizationTests(unittest.TestCase):
    def test_normalize_analysis_clamps_score_and_lists(self):
        result = normalize_analysis({"score": 120, "pros": "Python experience", "cons": ["No people management"]})

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["pros"], ["Python experience"])
        self.assertEqual(result["cons"], ["No people management"])


class CandidateAssistanceSafetyTests(unittest.TestCase):
    def test_candidate_assistance_redacts_pii_and_removes_decision_language(self):
        from core.candidate_assistance import render_candidate_assistance

        reply = render_candidate_assistance(
            resume_text="候选人邮箱 alice@example.com，有 Python 项目经验。",
            jd_text="需要 Python API 经验。",
            analysis={
                "pros": ["建议录用：具备 Python 项目经验"],
                "cons": ["缺少 API 规模与线上稳定性证据"],
            },
        )

        self.assertNotIn("alice@example.com", reply)
        self.assertNotIn("建议录用", reply)
        self.assertIn("证据来源", reply)
        self.assertIn("待确认项", reply)
        self.assertIn("HRBP", reply)

    def test_candidate_assistance_refuses_when_resume_or_jd_is_missing(self):
        from core.candidate_assistance import render_candidate_assistance

        reply = render_candidate_assistance(resume_text="", jd_text="需要 Python", analysis={})

        self.assertIn("缺少候选人简历", reply)
        self.assertIn("不形成匹配结论", reply)

    def test_candidate_assistance_removes_protected_trait_language(self):
        from core.candidate_assistance import render_candidate_assistance

        reply = render_candidate_assistance(
            resume_text="候选人有 Python 经验。",
            jd_text="需要 Python 经验。",
            analysis={"pros": ["年龄较小，适合高强度岗位"], "cons": []},
        )

        self.assertNotIn("年龄较小", reply)
        self.assertIn("受保护特征", reply)


class SecurityTests(unittest.TestCase):
    def test_redact_pii_masks_common_identifiers(self):
        text = "phone 13812345678, email test@example.com, id 110101199003071234"

        redacted = redact_pii(text)

        self.assertNotIn("13812345678", redacted)
        self.assertNotIn("test@example.com", redacted)
        self.assertNotIn("110101199003071234", redacted)
        self.assertIn("[PHONE_REDACTED]", redacted)
        self.assertIn("[EMAIL_REDACTED]", redacted)
        self.assertIn("[ID_CARD_REDACTED]", redacted)

    def test_verify_password_allows_empty_expected_password(self):
        self.assertTrue(verify_password("", None))
        self.assertTrue(verify_password("secret", "secret"))
        self.assertFalse(verify_password("wrong", "secret"))

    def test_redact_payload_masks_nested_values(self):
        payload = {"candidate": {"email": "test@example.com", "items": ["13812345678"]}}

        redacted = redact_payload(payload)

        self.assertEqual(redacted["candidate"]["email"], "[EMAIL_REDACTED]")
        self.assertEqual(redacted["candidate"]["items"][0], "[PHONE_REDACTED]")


class DocumentImportTests(unittest.TestCase):
    def test_extract_document_text_supports_plain_text(self):
        result = extract_document_text("Candidate has Python experience".encode("utf-8"), "resume.txt")

        self.assertIn("Python", result)


class AgentWorkflowPlanningTests(unittest.TestCase):
    def test_execution_plan_reflects_intent_and_blockers(self):
        from core.workflow import build_execution_plan, keyword_intent

        self.assertEqual(keyword_intent("请安排明天下午两点面试"), "action_tool")

        action_plan, action_stop = build_execution_plan("action_tool", {"input_text": "安排面试"})
        self.assertEqual(action_plan[0]["step"], "select_governed_tool")
        self.assertEqual(action_plan[2]["step"], "execute_governed_tool")
        self.assertIn("idempotency", action_plan[2]["description"])
        self.assertIn("tool attempt", action_stop)

        resume_plan, resume_stop = build_execution_plan("resume", {"resume_text": ""})
        self.assertEqual(resume_plan[0]["status"], "blocked")
        self.assertIn("missing-resume", resume_stop)

        rag_plan, rag_stop = build_execution_plan("rag", {"input_text": "请假制度"})
        self.assertEqual(rag_plan[0]["step"], "retrieve_policy_evidence")
        self.assertIn("cited answer", rag_stop)


class IsolatedRuntimeMixin:
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._old_env = {
            key: os.environ.get(key)
            for key in (
                "APP_DB_PATH",
                "AUDIT_LOG_PATH",
                "EMAIL_DRAFT_DIR",
                "CALENDAR_DIR",
                "ATS_EXPORT_DIR",
                "TOOL_EXECUTION_MODE",
                "ENTERPRISE_MODE",
                "REQUIRE_ACCESS_PASSWORD",
                "ACCESS_PASSWORD",
                "ALLOW_INSECURE_LOCAL_AUTH",
                "ACCESS_PASSWORD_MIN_LENGTH",
                "AUDIT_HASH_CHAIN_ENABLED",
                "API_RATE_LIMIT_PER_MINUTE",
                "DEFAULT_TENANT_ID",
                "DEFAULT_ORG_ID",
                "DEFAULT_DEPARTMENT_ID",
                "DATABASE_BACKEND",
                "DATABASE_URL",
                "VECTOR_BACKEND",
                "VECTOR_STORE_URL",
                "OBJECT_STORAGE_URI",
                "APPROVAL_REQUIRED_ACTIONS",
                "CONFIGURED_CONNECTOR_ENV",
                "TOOL_DEFAULT_TIMEOUT_SECONDS",
                "TOOL_DEFAULT_RETRIES",
                "TRUSTED_SSO_ENABLED",
                "TRUSTED_SSO_USER_HEADER",
                "TRUSTED_SSO_ROLE_HEADER",
                "TRUSTED_SSO_TENANT_HEADER",
                "TRUSTED_SSO_ORG_HEADER",
                "TRUSTED_SSO_DEPARTMENT_HEADER",
                "OIDC_ENABLED",
                "OIDC_ISSUER",
                "OIDC_AUDIENCE",
                "OIDC_JWKS_URL",
                "OIDC_HS256_SECRET",
                "OIDC_ROLE_CLAIM",
                "OIDC_DEFAULT_ROLE",
                "RAG_MIN_PASS_RATE",
                "RAG_MIN_KEYWORD_COVERAGE",
                "RAG_MIN_CITATION_CORRECTNESS",
            )
        }
        root = Path(self._tmpdir.name)
        os.environ["APP_DB_PATH"] = str(root / "peopleops.sqlite3")
        os.environ["AUDIT_LOG_PATH"] = str(root / "audit" / "events.jsonl")
        os.environ["EMAIL_DRAFT_DIR"] = str(root / "email_drafts")
        os.environ["CALENDAR_DIR"] = str(root / "calendar")
        os.environ["ATS_EXPORT_DIR"] = str(root / "ats_exports")
        os.environ["TOOL_EXECUTION_MODE"] = "local"
        os.environ.pop("ENTERPRISE_MODE", None)
        os.environ.pop("REQUIRE_ACCESS_PASSWORD", None)
        os.environ.pop("ACCESS_PASSWORD", None)
        os.environ["ALLOW_INSECURE_LOCAL_AUTH"] = "true"
        os.environ.pop("ACCESS_PASSWORD_MIN_LENGTH", None)
        os.environ.pop("AUDIT_HASH_CHAIN_ENABLED", None)
        os.environ.pop("API_RATE_LIMIT_PER_MINUTE", None)
        os.environ.pop("DEFAULT_TENANT_ID", None)
        os.environ.pop("DEFAULT_ORG_ID", None)
        os.environ.pop("DEFAULT_DEPARTMENT_ID", None)
        os.environ.pop("DATABASE_BACKEND", None)
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("VECTOR_BACKEND", None)
        os.environ.pop("VECTOR_STORE_URL", None)
        os.environ.pop("OBJECT_STORAGE_URI", None)
        os.environ.pop("APPROVAL_REQUIRED_ACTIONS", None)
        os.environ.pop("CONFIGURED_CONNECTOR_ENV", None)
        os.environ.pop("TOOL_DEFAULT_TIMEOUT_SECONDS", None)
        os.environ.pop("TOOL_DEFAULT_RETRIES", None)
        os.environ.pop("TRUSTED_SSO_ENABLED", None)
        os.environ.pop("TRUSTED_SSO_USER_HEADER", None)
        os.environ.pop("TRUSTED_SSO_ROLE_HEADER", None)
        os.environ.pop("TRUSTED_SSO_TENANT_HEADER", None)
        os.environ.pop("TRUSTED_SSO_ORG_HEADER", None)
        os.environ.pop("TRUSTED_SSO_DEPARTMENT_HEADER", None)
        os.environ.pop("OIDC_ENABLED", None)
        os.environ.pop("OIDC_ISSUER", None)
        os.environ.pop("OIDC_AUDIENCE", None)
        os.environ.pop("OIDC_JWKS_URL", None)
        os.environ.pop("OIDC_HS256_SECRET", None)
        os.environ.pop("OIDC_ROLE_CLAIM", None)
        os.environ.pop("OIDC_DEFAULT_ROLE", None)
        os.environ.pop("RAG_MIN_PASS_RATE", None)
        os.environ.pop("RAG_MIN_KEYWORD_COVERAGE", None)
        os.environ.pop("RAG_MIN_CITATION_CORRECTNESS", None)
        get_settings.cache_clear()

    def tearDown(self):
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        self._tmpdir.cleanup()


class ToolExecutionTests(IsolatedRuntimeMixin, unittest.TestCase):
    def test_parse_interview_window_handles_iso_time(self):
        now = datetime(2026, 6, 18, 9, 0, tzinfo=timezone(timedelta(hours=8), name="Asia/Shanghai"))

        window = parse_interview_window("2026-06-20 14:30", now=now)

        self.assertIsNotNone(window)
        self.assertEqual(window[0].strftime("%Y-%m-%d %H:%M"), "2026-06-20 14:30")
        self.assertEqual(window[1].strftime("%Y-%m-%d %H:%M"), "2026-06-20 15:30")

    def test_schedule_interview_returns_auditable_local_result(self):
        result = schedule_interview("Alice", "2026-06-20 14:00", candidate_email="candidate@example.com")

        self.assertEqual(result.tool_name, "schedule_interview")
        self.assertIn(result.status, {"DRY_RUN", "PERSISTED", "SUCCESS"})
        self.assertIn("execution_mode", result.metadata)
        self.assertGreaterEqual(len(list_interview_actions(limit=1)), 1)
        calendar_path = Path(result.metadata["calendar_event_path"])
        self.assertTrue(calendar_path.exists())
        calendar_text = calendar_path.read_text(encoding="utf-8")
        self.assertIn("DTSTART;TZID=Asia/Shanghai:20260620T140000", calendar_text)
        self.assertIn("DTEND;TZID=Asia/Shanghai:20260620T150000", calendar_text)
        self.assertTrue(Path(result.metadata["ats_export_path"]).exists())

    def test_schedule_interview_can_require_manual_approval(self):
        os.environ["TOOL_EXECUTION_MODE"] = "approval"
        get_settings.cache_clear()

        result = schedule_interview("Bob", "2026-06-21 10:00", candidate_email="bob@example.com")

        self.assertEqual(result.status, "PENDING_APPROVAL")
        self.assertEqual(result.metadata["email_draft_path"], "dry_run")
        self.assertEqual(result.metadata["calendar_event_path"], "dry_run")
        self.assertEqual(result.metadata["ats_export_path"], "dry_run")
        self.assertIsInstance(result.metadata["approval_request_id"], int)
        self.assertEqual(list_interview_actions(limit=1)[0]["status"], "PENDING_APPROVAL")
        self.assertEqual(list_approval_requests(limit=1)[0]["status"], "DRAFT")

    def test_approval_status_transitions_are_enforced(self):
        os.environ["TOOL_EXECUTION_MODE"] = "approval"
        get_settings.cache_clear()
        result = schedule_interview("Dana", "2026-06-21 15:00", candidate_email="dana@example.com")
        approval_id = result.metadata["approval_request_id"]

        submitted = update_approval_status(approval_id, tenant_id="default", status="PENDING", approved_by="requester")
        self.assertEqual(submitted["status"], "PENDING")
        approved = update_approval_status(approval_id, tenant_id="default", status="APPROVED", approved_by="reviewer")
        self.assertEqual(approved["status"], "APPROVED")
        executed = update_approval_status(approval_id, tenant_id="default", status="EXECUTED", approved_by="reviewer")
        self.assertEqual(executed["status"], "EXECUTED")

        with self.assertRaises(ValueError):
            update_approval_status(approval_id, tenant_id="default", status="REJECTED", approved_by="reviewer")

    def test_schedule_interview_records_tenant_scope(self):
        result = schedule_interview(
            "Carol",
            "2026-06-22 11:00",
            tenant_id="tenant-a",
            org_id="org-a",
            department_id="recruiting",
        )

        self.assertEqual(result.metadata["tenant_id"], "tenant-a")
        self.assertEqual(list_interview_actions(limit=5, tenant_id="tenant-a")[0]["org_id"], "org-a")
        self.assertEqual(list_interview_actions(limit=5, tenant_id="tenant-b"), [])

    def test_execute_tool_replays_success_for_same_idempotency_key(self):
        first = execute_tool(
            "schedule_interview",
            {"candidate_name": "Ivy", "interview_time": "2026-06-25 10:00", "candidate_email": "ivy@example.com"},
            idempotency_key="fixed-tool-key",
        )
        second = execute_tool(
            "schedule_interview",
            {"candidate_name": "Ivy", "interview_time": "2026-06-25 10:00", "candidate_email": "ivy@example.com"},
            idempotency_key="fixed-tool-key",
        )

        self.assertEqual(first.metadata["action_id"], second.metadata["action_id"])
        self.assertEqual(len(list_interview_actions(limit=10)), 1)
        self.assertEqual(second.metadata["idempotency_key"], "fixed-tool-key")

    def test_execute_tool_records_structured_failure(self):
        def failing_tool(**kwargs):
            raise RuntimeError("connector unavailable")

        register_tool(
            ToolSpec(
                name="test_failure_tool",
                description="Failure fixture",
                handler=failing_tool,
                max_retries=0,
            )
        )

        result = execute_tool("test_failure_tool", {}, idempotency_key="failure-key")

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.metadata["error"]["code"], "RuntimeError")
        self.assertFalse(result.metadata["error"]["retryable"])

    def test_compensate_tool_execution_marks_interview_action(self):
        execute_tool(
            "schedule_interview",
            {"candidate_name": "June", "interview_time": "2026-06-27 14:00"},
            idempotency_key="compensate-key",
        )

        result = compensate_tool_execution("compensate-key", reason="candidate withdrew")

        self.assertEqual(result.status, "COMPENSATED")
        self.assertEqual(list_interview_actions(limit=1)[0]["status"], "COMPENSATED")
        self.assertEqual(list_tool_compensations(limit=1)[0]["status"], "SUCCEEDED")

    def test_update_candidate_stage_tool_updates_and_compensates(self):
        created = schedule_interview("Nora", "2026-06-28 16:00", candidate_email="nora@example.com")
        action_id = created.metadata["action_id"]

        updated = execute_tool(
            "update_candidate_stage",
            {"action_id": action_id, "next_status": "PASSED", "reason": "panel approved"},
            idempotency_key="stage-key",
        )

        self.assertEqual(updated.status, "PERSISTED")
        self.assertEqual(updated.metadata["previous_status"], "PERSISTED")
        self.assertEqual(list_interview_actions(limit=1)[0]["status"], "PASSED")

        compensated = compensate_tool_execution("stage-key", reason="score corrected")

        self.assertEqual(compensated.status, "COMPENSATED")
        self.assertEqual(list_interview_actions(limit=1)[0]["status"], "PERSISTED")

    def test_update_candidate_stage_validates_status(self):
        created = schedule_interview("Owen", "2026-06-29 10:00")

        with self.assertRaises(ValueError):
            update_candidate_stage(created.metadata["action_id"], "MAYBE")


class AuditTests(IsolatedRuntimeMixin, unittest.TestCase):
    def test_audit_events_include_hash_chain_and_redaction(self):
        first = write_audit_event("test.first", {"email": "test@example.com"})
        second = write_audit_event("test.second", {"phone": "13812345678"})
        events = read_audit_events(limit=2)

        self.assertEqual(len(events), 2)
        self.assertTrue(first["event_hash"])
        self.assertEqual(second["previous_event_hash"], first["event_hash"])
        self.assertEqual(events[0]["payload"]["email"], "[EMAIL_REDACTED]")
        self.assertEqual(events[1]["payload"]["phone"], "[PHONE_REDACTED]")

    def test_audit_integrity_detects_tampering(self):
        write_audit_event("test.first", {"email": "test@example.com"})
        self.assertTrue(verify_audit_integrity()["valid"])

        audit_path = get_settings().audit_log_path
        events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        events[0]["payload"]["email"] = "tampered@example.com"
        audit_path.write_text(json.dumps(events[0], ensure_ascii=False) + "\n", encoding="utf-8")

        result = verify_audit_integrity()
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["error"], "event_hash_mismatch")


class AuthorizationTests(unittest.TestCase):
    def test_role_permissions(self):
        self.assertTrue(has_permission(Principal("alice", "admin"), "users"))
        self.assertTrue(has_permission(Principal("bob", "hrbp"), "tool"))
        self.assertFalse(has_permission(Principal("viewer", "viewer"), "tool"))


class TenancyTests(unittest.TestCase):
    def test_tenant_context_sanitizes_header_values(self):
        scope = TenantContext.from_headers(
            tenant_id=" tenant/a ",
            org_id="org@main",
            department_id="people ops",
            default_tenant_id="default",
            default_org_id="default-org",
            default_department_id="peopleops",
        )

        self.assertEqual(scope.tenant_id, "tenanta")
        self.assertEqual(scope.org_id, "orgmain")
        self.assertEqual(scope.department_id, "peopleops")


class DatabaseAdapterTests(unittest.TestCase):
    def test_postgres_sql_translation_uses_named_parameters_and_returning_id(self):
        from core.database import _translate_sql

        sql, params = _translate_sql(
            "INSERT INTO interview_actions (tenant_id, candidate_name) VALUES (?, ?)",
            ("tenant-a", "Alice"),
        )

        self.assertIn(":p0", sql)
        self.assertIn(":p1", sql)
        self.assertIn("RETURNING id", sql)
        self.assertEqual(params["p0"], "tenant-a")
        self.assertEqual(params["p1"], "Alice")

    def test_postgres_sql_translation_handles_agent_task_upsert_without_returning_id(self):
        from core.database import _translate_sql

        sql, params = _translate_sql(
            "INSERT OR REPLACE INTO agent_task_runs (task_id, thread_id, status, input_text) VALUES (?, ?, ?, ?)",
            ("task-1", "thread-1", "RUNNING", "hello"),
        )

        self.assertIn("INSERT INTO agent_task_runs", sql)
        self.assertIn("ON CONFLICT (task_id) DO UPDATE", sql)
        self.assertNotIn("RETURNING id", sql)
        self.assertEqual(params["p0"], "task-1")

    def test_approval_state_machine_supports_draft_submission_and_failure_retry(self):
        from core.database import APPROVAL_TRANSITIONS

        self.assertEqual(APPROVAL_TRANSITIONS["DRAFT"], {"PENDING"})
        self.assertEqual(APPROVAL_TRANSITIONS["PENDING"], {"APPROVED", "REJECTED"})
        self.assertEqual(APPROVAL_TRANSITIONS["APPROVED"], {"EXECUTED", "FAILED"})
        self.assertEqual(APPROVAL_TRANSITIONS["FAILED"], {"PENDING"})


class ApiControlPlaneTests(IsolatedRuntimeMixin, unittest.TestCase):
    def test_operator_events_are_tenant_scoped_and_idempotent(self):
        from fastapi.testclient import TestClient
        from core.database import create_agent_task_run
        import api

        api = importlib.reload(api)
        create_agent_task_run(task_id="task-operator-event", thread_id="thread-1", input_text="candidate review")
        with TestClient(api.app) as client:
            first = client.post("/tasks/task-operator-event/operator-events", json={"event_type": "candidate.adopted"})
            second = client.post("/tasks/task-operator-event/operator-events", json={"event_type": "candidate.adopted"})

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(first.json()["id"], second.json()["id"])

    def test_health_and_audit_endpoints_do_not_require_agent_runtime(self):
        from fastapi.testclient import TestClient
        import api

        api = importlib.reload(api)
        with TestClient(api.app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")
            self.assertEqual(health.json()["database_backend"], "sqlite")
            self.assertIsInstance(health.json()["model_configured"], bool)
            self.assertEqual(health.json()["chat_model"], "deepseek-chat")
            self.assertEqual(health.json()["rag_thresholds"]["min_pass_rate"], 1.0)

            scorecard = client.get("/enterprise/scorecard")
            self.assertEqual(scorecard.status_code, 200)
            scorecard_json = scorecard.json()
            self.assertGreater(scorecard_json["score"], 0)
            self.assertLessEqual(scorecard_json["score"], scorecard_json["target"])
            self.assertGreaterEqual(scorecard_json["raw_score"], scorecard_json["score"])
            self.assertEqual(scorecard_json["launch_ready_threshold"], 95)
            self.assertIn(scorecard_json["grade"], {"A+", "A", "A-", "B+", "B", "C"})
            self.assertTrue(all("checks" in item for item in scorecard_json["dimensions"]))
            self.assertTrue(any(item["id"] == "engineering_operations" for item in scorecard_json["dimensions"]))

            audit = client.get("/audit/events")
            self.assertEqual(audit.status_code, 200)
            self.assertEqual(audit.json(), [])

            integrity = client.get("/audit/integrity")
            self.assertEqual(integrity.status_code, 200)
            self.assertTrue(integrity.json()["valid"])

            readiness = client.get("/readiness")
            self.assertEqual(readiness.status_code, 200)
            self.assertTrue(readiness.json()["ready"])

            connectors = client.get("/connectors")
            self.assertEqual(connectors.status_code, 200)
            self.assertGreaterEqual(len(connectors.json()["connectors"]), 5)

            operations = client.get("/operations/summary")
            self.assertEqual(operations.status_code, 200)
            self.assertIn("task_success_rate", operations.json())
            self.assertIn("tool_status_counts", operations.json())
            self.assertIn("operator_metrics", operations.json())

            os.environ["TOOL_EXECUTION_MODE"] = "approval"
            get_settings.cache_clear()
            created = schedule_interview("Erin", "2026-06-24 10:00", candidate_email="erin@example.com")
            approval_id = created.metadata["approval_request_id"]
            submitted = client.post(f"/approvals/{approval_id}/submit")
            self.assertEqual(submitted.status_code, 200)
            self.assertEqual(submitted.json()["status"], "PENDING")
            approved = client.post(f"/approvals/{approval_id}/approve")
            self.assertEqual(approved.status_code, 200)
            self.assertEqual(approved.json()["status"], "APPROVED")
            executed = client.post(f"/approvals/{approval_id}/execute")
            self.assertEqual(executed.status_code, 200)
            self.assertEqual(executed.json()["status"], "EXECUTED")
            rejected = client.post(f"/approvals/{approval_id}/reject")
            self.assertEqual(rejected.status_code, 409)

            me = client.get("/me", headers={"X-Tenant-ID": "tenant-a", "X-Org-ID": "org-a"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["tenant_id"], "default")

    def test_chat_returns_service_error_when_agent_runtime_is_missing(self):
        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        import api

        api = importlib.reload(api)
        original_get_agent_app = api.get_agent_app
        api.get_agent_app = lambda: (_ for _ in ()).throw(HTTPException(status_code=503, detail="Agent runtime unavailable"))
        try:
            with TestClient(api.app) as client:
                response = client.post("/chat", json={"message": "hello"})
        finally:
            api.get_agent_app = original_get_agent_app

        self.assertEqual(response.status_code, 503)

    def test_chat_returns_structured_evidence(self):
        from fastapi.testclient import TestClient
        import api

        class DummyAgent:
            def invoke(self, inputs, config):
                return {
                    "reply": "ok",
                    "intent": "rag",
                    "evidence": [{"source": "policy-page-1", "snippet": "annual leave"}],
                }

        api = importlib.reload(api)
        original_get_agent_app = api.get_agent_app
        api.get_agent_app = lambda: DummyAgent()
        try:
            with TestClient(api.app) as client:
                response = client.post("/chat", json={"message": "leave policy"})
        finally:
            api.get_agent_app = original_get_agent_app

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["task_id"].startswith("task_"))
        self.assertEqual(response.json()["evidence"][0]["source"], "policy-page-1")

        with TestClient(api.app) as client:
            tasks = client.get("/tasks")
            self.assertEqual(tasks.status_code, 200)
            self.assertEqual(tasks.json()[0]["status"], "SUCCEEDED")
            self.assertEqual(tasks.json()[0]["intent"], "rag")

            task_id = response.json()["task_id"]
            detail = client.get(f"/tasks/{task_id}")
            self.assertEqual(detail.status_code, 200)
            event_types = [item["event_type"] for item in detail.json()["events"]]
            self.assertEqual(event_types, ["task.created", "workflow.started", "workflow.completed"])
            self.assertEqual(detail.json()["events"][-1]["payload"]["intent"], "rag")
            self.assertIn("latency_ms", detail.json()["events"][-1]["payload"])
            self.assertIn("estimated_total_tokens", detail.json()["state"]["trace_metrics"])
            self.assertIn(detail.json()["state"]["trace_metrics"]["token_source"], {"local_estimate", "provider_usage"})

            events = client.get(f"/tasks/{task_id}/events")
            self.assertEqual(events.status_code, 200)
            self.assertEqual(events.json()[-1]["event_type"], "workflow.completed")

            operations = client.get("/operations/summary")
            self.assertEqual(operations.status_code, 200)
            self.assertIn("agent_trace_metrics", operations.json())
            self.assertGreaterEqual(operations.json()["agent_trace_metrics"]["estimated_total_tokens"], 1)

    def test_chat_request_validation_limits_empty_message(self):
        from fastapi import HTTPException
        from fastapi.testclient import TestClient
        import api

        api = importlib.reload(api)
        original_get_agent_app = api.get_agent_app
        api.get_agent_app = lambda: (_ for _ in ()).throw(HTTPException(status_code=503, detail="Agent runtime unavailable"))
        try:
            with TestClient(api.app) as client:
                response = client.post("/chat", json={"message": ""})
        finally:
            api.get_agent_app = original_get_agent_app

        self.assertEqual(response.status_code, 422)

    def test_tool_registry_and_execution_endpoints(self):
        from fastapi.testclient import TestClient
        import api

        api = importlib.reload(api)
        execute_tool(
            "schedule_interview",
            {"candidate_name": "Frank", "interview_time": "2026-06-26 09:00"},
            idempotency_key="api-tool-key",
        )

        with TestClient(api.app) as client:
            tools = client.get("/tools")
            self.assertEqual(tools.status_code, 200)
            self.assertEqual(tools.json()["tools"][0]["name"], "schedule_interview")

            executions = client.get("/tool-executions")
            self.assertEqual(executions.status_code, 200)
            self.assertEqual(executions.json()[0]["idempotency_key"], "api-tool-key")
            self.assertEqual(executions.json()[0]["status"], "SUCCEEDED")

            compensated = client.post(
                "/tool-executions/api-tool-key/compensate",
                json={"reason": "candidate asked to cancel"},
            )
            self.assertEqual(compensated.status_code, 200)
            self.assertEqual(compensated.json()["result"]["status"], "COMPENSATED")

            compensations = client.get("/tool-compensations")
            self.assertEqual(compensations.status_code, 200)
            self.assertEqual(compensations.json()[0]["status"], "SUCCEEDED")

    def test_document_extract_endpoint_returns_text(self):
        from fastapi.testclient import TestClient
        import api

        api = importlib.reload(api)
        with TestClient(api.app) as client:
            response = client.post(
                "/documents/extract",
                files={"file": ("resume.txt", b"Candidate has Python and HR analytics experience.", "text/plain")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filename"], "resume.txt")
        self.assertIn("Python", response.json()["text"])

    def test_trusted_sso_headers_map_to_principal_and_rbac(self):
        from fastapi.testclient import TestClient
        import api

        os.environ["TRUSTED_SSO_ENABLED"] = "true"
        get_settings.cache_clear()
        api = importlib.reload(api)

        with TestClient(api.app) as client:
            unauthorized = client.get("/me")
            self.assertEqual(unauthorized.status_code, 401)

            me = client.get(
                "/me",
                headers={
                    "X-Authenticated-User": "mei@example.com",
                    "X-Authenticated-Role": "hrbp",
                    "X-Authenticated-Tenant": "tenant-sso",
                    "X-Tenant-ID": "spoofed-tenant",
                },
            )
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["username"], "mei@example.com")
            self.assertEqual(me.json()["role"], "hrbp")
            self.assertEqual(me.json()["tenant_id"], "tenant-sso")

            audit = client.get(
                "/audit/events",
                headers={
                    "X-Authenticated-User": "mei@example.com",
                    "X-Authenticated-Role": "hrbp",
                },
            )
            self.assertEqual(audit.status_code, 403)

    def test_oidc_bearer_token_maps_to_principal_and_rbac(self):
        from fastapi.testclient import TestClient
        import api

        os.environ["OIDC_ENABLED"] = "true"
        os.environ["OIDC_HS256_SECRET"] = "test-secret"
        os.environ["OIDC_AUDIENCE"] = "peopleops-api"
        os.environ["OIDC_ISSUER"] = "https://issuer.example.com"
        get_settings.cache_clear()
        api = importlib.reload(api)
        token = jwt.encode(
            {
                "sub": "user-123",
                "email": "oidc@example.com",
                "role": "admin",
                "tenant_id": "tenant-oidc",
                "aud": "peopleops-api",
                "iss": "https://issuer.example.com",
            },
            "test-secret",
            algorithm="HS256",
        )

        with TestClient(api.app) as client:
            missing = client.get("/me")
            self.assertEqual(missing.status_code, 401)

            me = client.get("/me", headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": "spoofed-tenant"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["username"], "oidc@example.com")
            self.assertEqual(me.json()["role"], "admin")
            self.assertEqual(me.json()["tenant_id"], "tenant-oidc")

    def test_unconfigured_local_auth_is_disabled_without_explicit_opt_in(self):
        from fastapi.testclient import TestClient
        import api

        os.environ["ALLOW_INSECURE_LOCAL_AUTH"] = "false"
        get_settings.cache_clear()
        api = importlib.reload(api)

        with TestClient(api.app) as client:
            response = client.get("/me")

        self.assertEqual(response.status_code, 503)

    def test_api_rate_limit_can_be_enforced(self):
        from fastapi.testclient import TestClient
        import api

        os.environ["API_RATE_LIMIT_PER_MINUTE"] = "2"
        get_settings.cache_clear()
        api = importlib.reload(api)
        with TestClient(api.app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/health").status_code, 429)


class PasswordHashingTests(unittest.TestCase):
    def test_pbkdf2_password_hash_roundtrip_and_legacy_support(self):
        encoded = hash_password("secret", salt="fixed-salt", iterations=1000)

        self.assertTrue(encoded.startswith("pbkdf2_sha256$1000$fixed-salt$"))
        self.assertTrue(verify_password("secret", encoded))
        self.assertFalse(verify_password("wrong", encoded))
        self.assertTrue(verify_password("secret", "sha256:2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b"))


class EnterpriseConfigTests(IsolatedRuntimeMixin, unittest.TestCase):
    def test_enterprise_mode_requires_access_password(self):
        os.environ["ENTERPRISE_MODE"] = "true"
        os.environ["REQUIRE_ACCESS_PASSWORD"] = "true"
        get_settings.cache_clear()

        self.assertIn(
            "ACCESS_PASSWORD is required when REQUIRE_ACCESS_PASSWORD is enabled.",
            enterprise_warnings(),
        )

    def test_enterprise_mode_warns_about_reference_backends(self):
        os.environ["ENTERPRISE_MODE"] = "true"
        os.environ["REQUIRE_ACCESS_PASSWORD"] = "false"
        get_settings.cache_clear()

        warnings = enterprise_warnings()

        self.assertTrue(any("DATABASE_BACKEND=sqlite" in item for item in warnings))
        self.assertTrue(any("VECTOR_BACKEND=chroma" in item for item in warnings))

    def test_enterprise_mode_requires_urls_for_managed_backends(self):
        os.environ["ENTERPRISE_MODE"] = "true"
        os.environ["REQUIRE_ACCESS_PASSWORD"] = "false"
        os.environ["TRUSTED_SSO_ENABLED"] = "true"
        os.environ["DEFAULT_TENANT_ID"] = "acme"
        os.environ["DATABASE_BACKEND"] = "postgresql"
        os.environ["VECTOR_BACKEND"] = "qdrant"
        os.environ["OBJECT_STORAGE_URI"] = "s3://peopleops-artifacts"
        get_settings.cache_clear()

        warnings = enterprise_warnings()

        self.assertTrue(any("DATABASE_URL is required" in item for item in warnings))
        self.assertTrue(any("VECTOR_STORE_URL is required" in item for item in warnings))


class RagEvaluationTests(unittest.TestCase):
    def test_agent_golden_traces_cover_tools_and_plans(self):
        from scripts.evaluate_agent_traces import evaluate, load_dataset

        cases = load_dataset()

        self.assertGreaterEqual(len(cases), 10)
        self.assertIn("update_candidate_stage", {item["name"] for item in list_registered_tools()})
        self.assertEqual(evaluate(), 0)

    def test_candidate_assistance_safety_eval_passes(self):
        from scripts.evaluate_candidate_assistance import evaluate

        self.assertEqual(evaluate(), 0)

    def test_dataset_contains_representative_fixture_cases(self):
        from scripts.evaluate_rag import load_dataset

        cases = load_dataset()

        self.assertGreaterEqual(len(cases), 10)
        self.assertTrue(all(item.get("id") for item in cases))
        self.assertTrue(all(item.get("retrieved_context") for item in cases))
        self.assertTrue(any(item["id"] == "missing-policy-grounding" for item in cases))

    def test_score_case_detects_pii_and_forbidden_terms(self):
        from scripts.evaluate_rag import score_case

        metrics = score_case(
            "员工请假信息 test@example.com",
            ["policy-page-1"],
            ["请假"],
            forbidden_terms=["test@example.com"],
        )

        self.assertFalse(metrics["passed"])
        self.assertTrue(metrics["pii_leakage"])
        self.assertEqual(metrics["forbidden_hits"], ["test@example.com"])

    def test_generation_fixture_eval_passes(self):
        from scripts.evaluate_rag import evaluate_generation_fixture, generation_readiness

        readiness = generation_readiness()

        self.assertIn("ready", readiness)
        self.assertGreaterEqual(len(readiness["checks"]), 4)
        self.assertIn("embedding_model_offline_cache", {item["id"] for item in readiness["checks"]})
        self.assertEqual(evaluate_generation_fixture(), 0)

    def test_qdrant_backend_requires_vector_store_url(self):
        from core.rag_engine import QdrantPolicyRetriever

        old_vector_backend = os.environ.get("VECTOR_BACKEND")
        old_vector_url = os.environ.get("VECTOR_STORE_URL")
        os.environ["VECTOR_BACKEND"] = "qdrant"
        os.environ.pop("VECTOR_STORE_URL", None)
        get_settings.cache_clear()

        class DummyEmbeddings:
            def embed_query(self, text):
                return [0.1, 0.2]

        try:
            with self.assertRaises(RuntimeError):
                QdrantPolicyRetriever(DummyEmbeddings())
        finally:
            if old_vector_backend is None:
                os.environ.pop("VECTOR_BACKEND", None)
            else:
                os.environ["VECTOR_BACKEND"] = old_vector_backend
            if old_vector_url is None:
                os.environ.pop("VECTOR_STORE_URL", None)
            else:
                os.environ["VECTOR_STORE_URL"] = old_vector_url
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
