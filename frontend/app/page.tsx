"use client";

import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  Building2,
  Check,
  CheckCircle2,
  Clock3,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  Hash,
  Layers3,
  LockKeyhole,
  MessageSquareText,
  Play,
  Plug,
  RotateCcw,
  SearchCheck,
  Send,
  Settings,
  ShieldCheck,
  Upload,
  Users,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  ActionRecord,
  AuditEvent,
  ChatMessage,
  ConnectorRecord,
  HealthResponse,
  OperationsSummary,
  ProductionCheckRecord,
  ProductionChecksResponse,
  RagEvidence,
  ReadinessResponse,
  TaskRun,
  TaskEvent,
  ToolExecutionRecord,
  ToolRecord,
  extractDocument,
  getApprovals,
  getAuditEvents,
  getConnectors,
  getHealth,
  getInterviews,
  getOperationsSummary,
  getProductionChecks,
  getReadiness,
  getTaskDetail,
  getTasks,
  getToolExecutions,
  getTools,
  sendChat,
  transitionApproval,
} from "../lib/api";

type ProductView = "workspace" | "candidates" | "approvals" | "connectors" | "audit" | "settings";

const starterMessages: ChatMessage[] = [
  {
    role: "assistant",
    content:
      "Hello, I am the PeopleOps Intelligence Assistant. Upload a resume, paste a JD, or ask about policy, reimbursement, attendance, benefits, and candidate follow-up actions.",
  },
];

function statusTone(ok?: boolean) {
  return ok ? "status-pill ok" : "status-pill warn";
}

function readinessLabel(ok?: boolean) {
  return ok ? "Production ready" : "Needs review";
}

function auditLabel(ok?: boolean) {
  return ok ? "Audit valid" : "Needs check";
}

function shortText(value: string | undefined, fallback = "None") {
  if (!value) return fallback;
  return value.length > 72 ? `${value.slice(0, 72)}...` : value;
}

function connectorSummary(connectors: ConnectorRecord[]) {
  const configured = connectors.filter((item) => item.status === "configured").length;
  return `${configured}/${connectors.length}`;
}

function parseJsonSafe(value?: string) {
  if (!value) return null;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

function previewJson(value: unknown, fallback = "No details") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return text.length > 520 ? `${text.slice(0, 520)}...` : text;
}

function formatDateTime(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDuration(start?: string, end?: string) {
  if (!start || !end) return "--";
  const delta = new Date(end).getTime() - new Date(start).getTime();
  if (!Number.isFinite(delta) || delta < 0) return "--";
  if (delta < 1000) return `${delta}ms`;
  return `${(delta / 1000).toFixed(1)}s`;
}

function normalizeKeyword(value: string) {
  return value.replace(/[^\p{L}\p{N}_-]/gu, "").trim().toLowerCase();
}

function searchTerms(question: string) {
  const normalized = normalizeKeyword(question);
  const cjkTerms = Array.from(question.matchAll(/[\u4e00-\u9fff]{2,}/g)).flatMap((match) => {
    const value = match[0];
    const terms = [value.slice(0, 6)];
    for (let index = 0; index < value.length - 1; index += 1) {
      terms.push(value.slice(index, index + 2));
    }
    return terms;
  });
  const wordTerms = question.split(/\s+/).map(normalizeKeyword);
  return Array.from(new Set([...wordTerms, ...cjkTerms, normalized])).filter((term) => term.length >= 2).slice(0, 18);
}

function keywordHits(question: string, snippet: string) {
  const terms = searchTerms(question);
  const lowerSnippet = snippet.toLowerCase();
  return terms.filter((term) => lowerSnippet.includes(term)).slice(0, 5);
}

function inferPageLabel(source: string) {
  const match = source.match(/(?:page|p)[-_ ]?(\d+)/i) || source.match(/#page=(\d+)/i);
  return match ? `p.${match[1]}` : "chunk";
}

function evidenceReliability(item: RagEvidence, question: string) {
  const hits = keywordHits(question, item.snippet);
  if (!item.snippet) return "No excerpt";
  if (hits.length >= 2) return "Keyword hit";
  if (item.source) return "Traceable";
  return "Needs review";
}

function statusClass(status?: string) {
  const normalized = (status || "").toLowerCase();
  if (["success", "succeeded", "completed", "approved", "ready", "ok"].some((term) => normalized.includes(term))) return "ok";
  if (["fail", "error", "reject", "cancel"].some((term) => normalized.includes(term))) return "danger";
  if (["pending", "running", "review", "check"].some((term) => normalized.includes(term))) return "warn";
  return "neutral";
}

function statusLabel(status?: string) {
  const normalized = (status || "").toUpperCase();
  const labels: Record<string, string> = {
    APPROVED: "Approved",
    CANCELLED: "Cancelled",
    COMPLETED: "Completed",
    CONFIGURED: "Configured",
    ERROR: "Error",
    FAILED: "Failed",
    PENDING: "Pending review",
    READY: "Ready",
    REJECTED: "Rejected",
    RUNNING: "Running",
    SUCCESS: "Success",
    SUCCEEDED: "Success",
  };
  return labels[normalized] || status || "--";
}

function eventSummary(event: TaskEvent) {
  const payload = event.payload || {};
  const keys = Object.keys(payload);
  if (!keys.length) return "鏃?payload";
  const preferred = ["intent", "tool_name", "status", "evidence_count", "reply_chars", "error"];
  const picked = preferred.filter((key) => key in payload);
  const displayKeys = picked.length ? picked : keys.slice(0, 3);
  return displayKeys.map((key) => `${key}: ${String(payload[key]).slice(0, 48)}`).join(" 路 ");
}

function EmptyState({
  icon: Icon,
  title,
  body,
  tone = "neutral",
}: {
  icon: LucideIcon;
  title: string;
  body: string;
  tone?: "neutral" | "warn" | "ok";
}) {
  return (
    <div className={`empty-state ${tone}`}>
      <Icon size={16} />
      <div>
        <strong>{title}</strong>
        <p>{body}</p>
      </div>
    </div>
  );
}

export default function Home() {
  const [accessPassword, setAccessPassword] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [resumeFiles, setResumeFiles] = useState<string[]>([]);
  const [jdText, setJdText] = useState("");
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>(starterMessages);
  const [threadId, setThreadId] = useState("");
  const [lastTaskId, setLastTaskId] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isExtracting, setIsExtracting] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [operations, setOperations] = useState<OperationsSummary | null>(null);
  const [interviews, setInterviews] = useState<ActionRecord[]>([]);
  const [approvals, setApprovals] = useState<ActionRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [tasks, setTasks] = useState<TaskRun[]>([]);
  const [selectedTask, setSelectedTask] = useState<TaskRun | null>(null);
  const [tools, setTools] = useState<ToolRecord[]>([]);
  const [toolExecutions, setToolExecutions] = useState<ToolExecutionRecord[]>([]);
  const [connectors, setConnectors] = useState<ConnectorRecord[]>([]);
  const [error, setError] = useState("");
  const [activeInspector, setActiveInspector] = useState<"overview" | "trace" | "actions" | "audit">("overview");
  const [selectedToolExecutionId, setSelectedToolExecutionId] = useState<number | null>(null);
  const [isRefreshingOps, setIsRefreshingOps] = useState(false);
  const [loadingTaskId, setLoadingTaskId] = useState("");
  const [pendingApprovalId, setPendingApprovalId] = useState<number | null>(null);
  const [activeProductView, setActiveProductView] = useState<ProductView>("workspace");
  const [productionChecks, setProductionChecks] = useState<ProductionChecksResponse | null>(null);

  const latestUserQuestion = useMemo(
    () => [...messages].reverse().find((message) => message.role === "user")?.content || "",
    [messages],
  );
  const latestAssistantEvidence = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant" && message.evidence?.length)?.evidence || [],
    [messages],
  );
  const selectedToolExecution = useMemo(
    () => toolExecutions.find((execution) => execution.id === selectedToolExecutionId) || toolExecutions[0] || null,
    [selectedToolExecutionId, toolExecutions],
  );

  async function refreshOperationalData(password = accessPassword) {
    setError("");
    setIsRefreshingOps(true);
    try {
      const [healthData, readinessData] = await Promise.all([
        getHealth(),
        getReadiness().catch((err) => {
          throw new Error(`Readiness: ${err.message}`);
        }),
      ]);
      setHealth(healthData);
      setReadiness(readinessData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to read backend status");
    }

    try {
      const [interviewData, approvalData, auditData, taskData, toolData, toolExecutionData, connectorData, operationsData, productionCheckData] = await Promise.all([
        getInterviews(password),
        getApprovals(password),
        getAuditEvents(password),
        getTasks(password),
        getTools(password),
        getToolExecutions(password),
        getConnectors(password),
        getOperationsSummary(password),
        getProductionChecks(password),
      ]);
      setInterviews(interviewData);
      setApprovals(approvalData);
      setAuditEvents(auditData);
      setTasks(taskData);
      setTools(toolData.tools);
      setToolExecutions(toolExecutionData);
      setConnectors(connectorData.connectors);
      setOperations(operationsData);
      setProductionChecks(productionCheckData);
    } catch {
      setInterviews([]);
      setApprovals([]);
      setAuditEvents([]);
      setTasks([]);
      setTools([]);
      setToolExecutions([]);
      setConnectors([]);
      setOperations(null);
      setProductionChecks(null);
    } finally {
      setIsRefreshingOps(false);
    }
  }

  useEffect(() => {
    refreshOperationalData(accessPassword);
    const timer = window.setInterval(() => refreshOperationalData(accessPassword), 45000);
    return () => window.clearInterval(timer);
  }, [accessPassword]);

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    setResumeFiles(files.map((file) => file.name));
    if (!files.length) return;

    setIsExtracting(true);
    setError("");
    const textParts: string[] = [];
    try {
      for (const file of files) {
        const extracted = await extractDocument(file, accessPassword);
        textParts.push(`銆?{extracted.filename}銆慭n${extracted.text}`);
      }
      setResumeText(textParts.join("\n\n"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "鏂囨。瑙ｆ瀽澶辫触");
    } finally {
      setIsExtracting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = prompt.trim();
    if (!message || isSending) return;

    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: message }];
    setMessages(nextMessages);
    setPrompt("");
    setIsSending(true);
    setError("");

    try {
      const response = await sendChat({
        message,
        jdText,
        resumeText,
        history: nextMessages,
        threadId,
        accessPassword,
      });
      setThreadId(response.thread_id);
      setLastTaskId(response.task_id);
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.reply || "The system did not return a valid response.",
          evidence: response.evidence || [],
        },
      ]);
      await refreshOperationalData(accessPassword);
      const task = await getTaskDetail(response.task_id, accessPassword);
      setSelectedTask(task);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent 璇锋眰澶辫触");
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: "The request did not complete. Check the backend API, access password, or model configuration.",
        },
      ]);
    } finally {
      setIsSending(false);
    }
  }

  async function handleApprovalAction(approvalId: number, action: "approve" | "reject" | "execute") {
    setError("");
    setPendingApprovalId(approvalId);
    try {
      await transitionApproval(approvalId, action, accessPassword);
      await refreshOperationalData(accessPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval status update failed");
    } finally {
      setPendingApprovalId(null);
    }
  }

  async function selectTask(taskId: string) {
    setError("");
    setLoadingTaskId(taskId);
    try {
      setSelectedTask(await getTaskDetail(taskId, accessPassword));
    } catch (err) {
      setError(err instanceof Error ? err.message : "浠诲姟璇︽儏璇诲彇澶辫触");
    } finally {
      setLoadingTaskId("");
    }
  }

  const ready = readiness?.ready;
  const auditValid = readiness?.audit_integrity?.valid;
  const score = readiness?.scorecard?.score;
  const readinessWarnings = readiness?.enterprise_warnings || health?.enterprise_warnings || [];
  const identityMode = health?.trusted_sso_enabled
    ? "SSO"
    : health?.oidc_enabled
      ? "OIDC"
      : health?.access_password_required
        ? "Password"
        : "Local";
  const deploymentChecks = [
    { label: "Model", ok: Boolean(health?.model_configured), value: health?.chat_model || "--" },
    { label: "Identity", ok: Boolean(health), value: identityMode },
    { label: "Database", ok: health?.database_backend === "sqlite" || Boolean(health?.database_url_configured), value: health?.database_backend || "--" },
    { label: "Vector search", ok: health?.vector_backend === "chroma" || Boolean(health?.vector_store_url_configured), value: health?.vector_backend || "--" },
    { label: "Object store", ok: Boolean(health?.object_storage_configured) || !readiness?.enterprise_warnings?.some((item) => item.includes("OBJECT_STORAGE_URI")), value: health?.object_storage_configured ? "configured" : "local" },
    { label: "Audit chain", ok: Boolean(auditValid), value: auditValid ? "valid" : "check" },
  ];
  const materialStatus = resumeFiles.length ? `${resumeFiles.length} files` : resumeText.trim() ? "Resume pasted" : "Add material";
  const jdStatus = jdText.trim() ? "Role ready" : "Add job context";
  const inspectorTabs = [
    { id: "overview" as const, label: "Overview", icon: ShieldCheck },
    { id: "trace" as const, label: "Trace", icon: GitBranch },
    { id: "actions" as const, label: "Actions", icon: Wrench },
    { id: "audit" as const, label: "Audit", icon: Database },
  ];
  const quickPrompts = [
    "How well does this resume match the JD?",
    "What is the travel reimbursement policy?",
    "Generate interview follow-up actions for this candidate.",
  ];
  const overviewSignals = [
    { label: "Material", value: materialStatus, tone: resumeText.trim() || resumeFiles.length ? "ok" : "warn" },
    { label: "Role", value: jdStatus, tone: jdText.trim() ? "ok" : "warn" },
    { label: "Approvals", value: approvals.filter((item) => item.status === "PENDING").length.toString(), tone: approvals.some((item) => item.status === "PENDING") ? "warn" : "ok" },
    { label: "Audit", value: auditLabel(auditValid), tone: auditValid ? "ok" : "warn" },
  ];
  const workflowSteps = [
    {
      label: "1",
      title: "Prepare material",
      body: materialStatus,
      ok: Boolean(resumeText.trim() || resumeFiles.length),
    },
    {
      label: "2",
      title: "Add role context",
      body: jdStatus,
      ok: Boolean(jdText.trim()),
    },
    {
      label: "3",
      title: "Generate judgment and actions",
      body: lastTaskId ? "Task replay available" : "Send a question to ground evidence",
      ok: Boolean(lastTaskId),
    },
  ];
  const pendingApprovals = approvals.filter((item) => item.status === "PENDING");
  const failedToolCount = operations?.tool_status_counts?.FAILED ?? toolExecutions.filter((item) => statusClass(item.status) === "danger").length;
  const tenantName = operations?.tenant_id || "default";
  const hasApiIssue = Boolean(error);
  const hasAuthGate = Boolean(health?.access_password_required && !accessPassword);
  const healthBanner = hasApiIssue
    ? { tone: "danger", title: "Backend connection issue", body: error }
    : hasAuthGate
      ? { tone: "warn", title: "Access password required", body: "Enter the access password to load approvals, audit events, connectors, and tool execution records." }
      : !ready
        ? { tone: "warn", title: "Production readiness needs review", body: readinessWarnings[0] || "This environment still has configuration items to confirm." }
        : null;
  const candidateRecords = [
    {
      name: resumeFiles[0]?.replace(/\.[^.]+$/, "") || (resumeText.trim() ? "Current candidate" : "Candidate pending import"),
      role: jdText.trim() ? "Linked to current JD" : "Role pending",
      stage: lastTaskId ? "Analyzed" : resumeText.trim() || resumeFiles.length ? "Ready to analyze" : "Pending import",
      fit: lastTaskId ? "Recommendation generated" : jdText.trim() && (resumeText.trim() || resumeFiles.length) ? "Ready to match" : "Incomplete material",
    },
    {
      name: "Sales operations manager pool",
      role: "Sample queue",
      stage: "Pending import",
      fit: "Sync after ATS connection",
    },
    {
      name: "Engineering productivity pool",
      role: "Sample queue",
      stage: "Pending import",
      fit: "Sync after ATS connection",
    },
  ];
  const navigationItems = [
    { id: "workspace" as const, label: "Workspace", value: "Agent console", icon: Layers3 },
    { id: "candidates" as const, label: "Candidates", value: `${resumeFiles.length || (resumeText.trim() ? 1 : 0)} materials`, icon: Users },
    { id: "approvals" as const, label: "Approvals", value: `${pendingApprovals.length} pending`, icon: ClipboardList },
    { id: "connectors" as const, label: "Connectors", value: connectorSummary(connectors), icon: Plug },
    { id: "audit" as const, label: "Audit", value: auditLabel(auditValid), icon: ShieldCheck },
    { id: "settings" as const, label: "Settings", value: "Config center", icon: Settings },
  ];
  const usageItems = [
    { label: "Tasks", value: operations?.task_count ?? tasks.length },
    { label: "Tool calls", value: operations?.tool_execution_count ?? toolExecutions.length },
    { label: "Approvals", value: approvals.length },
  ];
  const fallbackProductionChecks: ProductionCheckRecord[] = [
    {
      id: "postgresql",
      label: "PostgreSQL instance, migrations, and read/write verification",
      status: health?.database_backend === "postgresql" && health?.database_url_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${health?.database_backend || "--"} / DATABASE_URL=${health?.database_url_configured ? "configured" : "missing"}`,
      next_step: "Connect the backend /production/checks endpoint for live verification.",
    },
    {
      id: "qdrant",
      label: "Qdrant or production vector index write/search",
      status: health?.vector_backend !== "chroma" && health?.vector_store_url_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${health?.vector_backend || "--"} / VECTOR_STORE_URL=${health?.vector_store_url_configured ? "configured" : "missing"}`,
      next_step: "Configure the production vector store, then run index write, retrieval, and RAG eval checks.",
    },
    {
      id: "object_storage",
      label: "S3/MinIO object upload, download, permissions, and lifecycle",
      status: health?.object_storage_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: health?.object_storage_configured ? "OBJECT_STORAGE_URI configured" : "OBJECT_STORAGE_URI missing",
      next_step: "Verify put/get/delete operations and lifecycle policy behavior.",
    },
    {
      id: "oidc",
      label: "OIDC provider token validation and role mapping",
      status: health?.oidc_enabled ? "configured" : "not_configured",
      verification: "configuration",
      detail: identityMode,
      next_step: "Call /me with a real bearer token to verify role mapping.",
    },
    {
      id: "external_tools",
      label: "ATS/calendar API credentials, retries, idempotency, and compensation",
      status: connectors.some((item) => item.status === "configured" && ["ats", "calendar", "collaboration"].includes(item.category)) ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${connectorSummary(connectors)} connectors configured`,
      next_step: "Run sandbox ATS stage changes, calendar invites, retry checks, and compensation evidence.",
    },
    {
      id: "network_ops",
      label: "Production network, TLS, CORS, gateway, logs, and alerts",
      status: health?.trusted_sso_enabled || health?.oidc_enabled ? "configured" : "not_configured",
      verification: "configuration",
      detail: `rate limit / identity / gateway readiness`,
      next_step: "Verify TLS, CORS, access logs, and alert routes at the production gateway.",
    },
    {
      id: "e2e_demo",
      label: "End-to-end demo and rollback rehearsal",
      status: "configured",
      verification: "runbook",
      detail: "Runbook exists; requires operator evidence.",
      next_step: "Run upload, Q&A, approval, execution, audit chain, and rollback rehearsal.",
    },
  ];
  const productionReadinessItems = productionChecks?.checks || fallbackProductionChecks;
  const productionCheckSummary = productionChecks?.summary || productionReadinessItems.reduce(
    (summary, item) => {
      summary[item.status] += 1;
      return summary;
    },
    { not_configured: 0, configured: 0, verified: 0, failed: 0 } as ProductionChecksResponse["summary"],
  );

  return (
    <main className="app-shell">
      <aside className="context-panel" id="candidate-context">
        <div className="brand-block">
          <div className="brand-mark">P</div>
          <div>
            <p className="eyebrow">PeopleOps</p>
            <h1>Intelligence Console</h1>
          </div>
        </div>

        <section className="tenant-card" aria-label="Tenant information">
          <div className="tenant-mark">
            <Building2 size={17} />
          </div>
          <div>
            <span>Current tenant</span>
            <strong>{tenantName}</strong>
          </div>
          <em>Pro</em>
        </section>

        <nav className="side-nav" aria-label="Product navigation">
          {navigationItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                aria-current={activeProductView === item.id ? "page" : undefined}
                className={activeProductView === item.id ? "active" : ""}
                key={item.label}
                onClick={() => setActiveProductView(item.id)}
                type="button"
              >
                <Icon size={16} />
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </button>
            );
          })}
        </nav>

        <section className="panel-section">
          <div className="section-title">
            <BriefcaseBusiness size={16} />
            Candidate and role context
          </div>
          <label className="file-drop">
            <Upload size={18} />
            <span>{isExtracting ? "Parsing document" : "Upload resume or material"}</span>
            <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
          </label>
          <div className="file-list">
            {resumeFiles.length ? resumeFiles.map((name) => <span key={name}>{name}</span>) : "Supports PDF, DOCX, TXT, and MD. Uploads are parsed by the backend."}
          </div>
          <textarea
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            placeholder="Candidate resume, interview notes, or key summaries appear here."
            rows={7}
          />
          <textarea
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            placeholder="Paste the job description, capability requirements, and seniority expectations."
            rows={7}
          />
        </section>

        <section className="panel-section compact">
          <div className="section-title">
            <LockKeyhole size={16} />
            Access and backend
          </div>
          <form className="access-form" onSubmit={(event) => event.preventDefault()}>
            <input
              aria-label="Access password"
              autoComplete="current-password"
              value={accessPassword}
              onChange={(event) => setAccessPassword(event.target.value)}
              onBlur={(event) => refreshOperationalData(event.currentTarget.value)}
              type="password"
              placeholder="Access password"
            />
          </form>
          <p className="subtle">API: {API_BASE}</p>
        </section>

        <section className="usage-card" aria-label="Monthly usage">
          <div className="section-title">
            <BarChart3 size={16} />
            Monthly usage
          </div>
          <div className="usage-grid">
            {usageItems.map((item) => (
              <div key={item.label}>
                <strong>{item.value}</strong>
                <span>{item.label}</span>
              </div>
            ))}
          </div>
        </section>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">HRBP Operations Console</p>
            <h2>{health?.app_name || "PeopleOps Intelligence Agent"}</h2>
            <p>AI workbench for multi-tenant PeopleOps teams: policy Q&A, resume matching, candidate follow-up, approvals, and audit traceability.</p>
          </div>
          <div className="header-ops">
            <div className="workspace-actions" aria-label="Workspace actions">
              <button type="button" title="Notifications">
                <AlertTriangle size={15} />
              </button>
              <button type="button" title="Settings">
                <Settings size={15} />
              </button>
            </div>
            <div className="status-cluster">
              <span className={statusTone(Boolean(health?.status))}>
                <CheckCircle2 size={14} />
                API {health?.status || "checking"}
              </span>
              <span className={statusTone(ready)}>
                <ShieldCheck size={14} />
                {readinessLabel(ready)}
              </span>
              <span className={statusTone(auditValid)}>
                <Activity size={14} />
                {auditLabel(auditValid)}
              </span>
            </div>
          </div>
        </header>

        {healthBanner ? (
          <section className={`global-banner ${healthBanner.tone}`}>
            <AlertTriangle size={17} />
            <div>
              <strong>{healthBanner.title}</strong>
              <p>{healthBanner.body}</p>
            </div>
          </section>
        ) : null}

        {activeProductView === "workspace" ? (
          <>
        <section className="overview-strip" aria-label="杩愯惀鎬佸娍">
          {overviewSignals.map((item) => (
            <div className={`signal-card ${item.tone}`} key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </section>

        <section className="workflow-strip" aria-label="First-use workflow">
          {workflowSteps.map((step) => (
            <div className={step.ok ? "workflow-step done" : "workflow-step"} key={step.label}>
              <span>{step.label}</span>
              <div>
                <strong>{step.title}</strong>
                <p>{step.body}</p>
              </div>
            </div>
          ))}
        </section>

        {error ? (
          <div className="notice">
            <AlertTriangle size={16} />
            {error}
          </div>
        ) : null}

        <section className="mobile-material-card">
          <div>
            <p className="eyebrow">Candidate Context</p>
            <h3>Candidate material</h3>
          </div>
          <div className="mobile-material-actions">
            <label className="file-drop compact-drop">
              <Upload size={16} />
              <span>{isExtracting ? "Parsing" : "Upload"}</span>
              <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
            </label>
            <a className="link-button" href="#candidate-context">
              Edit material
            </a>
          </div>
          <div className="material-chips">
            <span>{materialStatus}</span>
            <span>{jdStatus}</span>
          </div>
        </section>

        <section className="chat-card">
          <div className="chat-card-head">
            <div>
              <p className="eyebrow">AI Operations Workspace</p>
              <h3>PeopleOps Intelligence Assistant</h3>
            </div>
            <div className="session-meta">
              <span>{lastTaskId || threadId || "New session"}</span>
              <strong>{tenantName}</strong>
            </div>
          </div>

          <div className="message-list">
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="message-avatar">
                  {message.role === "assistant" ? <Bot size={16} /> : <MessageSquareText size={16} />}
                </div>
                <p>{message.content}</p>
              </article>
            ))}
            {isSending ? (
              <article className="message assistant">
                <div className="message-avatar">
                  <Bot size={16} />
                </div>
                <p className="typing-state">Retrieving policy, candidate context, and executable actions...</p>
              </article>
            ) : null}
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            <div className="prompt-rail" aria-label="Quick questions">
              {quickPrompts.map((item) => (
                <button key={item} type="button" onClick={() => setPrompt(item)}>
                  {item}
                </button>
              ))}
            </div>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="For example: What is the lodging reimbursement standard? Does this resume match the JD? Help schedule a candidate interview tomorrow afternoon."
              rows={3}
            />
            <button type="submit" disabled={isSending || !prompt.trim()}>
              <Send size={16} />
              {isSending ? "Processing" : "Send"}
            </button>
          </form>
        </section>
          </>
        ) : null}

        {activeProductView === "candidates" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Candidate CRM</p>
                <h3>Candidate records</h3>
                <p>Review candidate material, role linkage, match status, and next actions in one place.</p>
              </div>
              <label className="module-action">
                <Upload size={15} />
                Import material
                <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
              </label>
            </div>
            <div className="data-table candidate-table">
              <div className="table-row table-head">
                <span>Candidate / Queue</span>
                <span>Role</span>
                <span>Stage</span>
                <span>Match status</span>
              </div>
              {candidateRecords.map((candidate) => (
                <button className="table-row" key={candidate.name} type="button" onClick={() => setActiveProductView("workspace")}>
                  <strong>{candidate.name}</strong>
                  <span>{candidate.role}</span>
                  <span className={`state-chip ${candidate.stage === "Analyzed" ? "ok" : "warn"}`}>{candidate.stage}</span>
                  <span>{candidate.fit}</span>
                </button>
              ))}
            </div>
            {!resumeText.trim() && !resumeFiles.length ? (
              <EmptyState icon={Users} tone="warn" title="No real candidate material yet" body="Import a resume or connect ATS to show a real candidate queue here." />
            ) : null}
          </section>
        ) : null}

        {activeProductView === "approvals" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Approval Center</p>
                <h3>Approval center</h3>
                <p>Review external actions generated by the agent, execution permissions, and compensating operations.</p>
              </div>
              <div className="segmented-summary">
                <span>{pendingApprovals.length} pending</span>
                <span>{approvals.filter((item) => item.status === "APPROVED").length} approved</span>
                <span>{approvals.filter((item) => item.status === "REJECTED").length} rejected</span>
              </div>
            </div>
            <div className="approval-board">
              {[...approvals, ...interviews].slice(0, 10).map((item) => (
                <article className="approval-item" key={`${item.id}-${item.status}`}>
                  <div>
                    <span className={`state-chip ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                    <strong>{shortText(item.candidate_name || item.action_type || item.subject_ref, "Candidate action")}</strong>
                    <p>{item.interview_time ? `Interview time: ${formatDateTime(item.interview_time)}` : "Waiting for HRBP review before execution."}</p>
                  </div>
                  {item.action_type && item.status === "PENDING" ? (
                    <div className="row-actions">
                      <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "approve")}>
                        <Check size={13} />
                        Approve
                      </button>
                      <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "reject")}>
                        <X size={13} />
                        Reject
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
              {!approvals.length && !interviews.length ? (
                <EmptyState icon={ClipboardList} title="No approval items" body="When the agent needs to send email, schedule interviews, or call external systems, items appear here." />
              ) : null}
            </div>
          </section>
        ) : null}

        {activeProductView === "connectors" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Integration Hub</p>
                <h3>Connectors and tools</h3>
                <p>Manage enterprise system connections for ATS, calendar, email, vector stores, and object storage.</p>
              </div>
              <span className="module-badge">{connectorSummary(connectors)} configured</span>
            </div>
            <div className="connector-grid">
              {connectors.map((connector) => (
                <article className="connector-card" key={connector.name}>
                  <Plug size={16} />
                  <div>
                    <strong>{connector.name}</strong>
                    <p>{connector.category || "enterprise connector"}</p>
                  </div>
                  <span className={`state-chip ${statusClass(connector.status)}`}>{statusLabel(connector.status)}</span>
                </article>
              ))}
              {!connectors.length ? (
                <>
                  {["ATS", "Calendar", "Email", "Vector Store"].map((name) => (
                    <article className="connector-card muted" key={name}>
                      <Plug size={16} />
                      <div>
                        <strong>{name}</strong>
                        <p>Sync after entering the access password or configuring environment variables.</p>
                      </div>
                      <span className="state-chip neutral">Pending config</span>
                    </article>
                  ))}
                </>
              ) : null}
            </div>
            <section className="panel-card">
              <div className="section-title">
                <Wrench size={16} />
                Tool registry
              </div>
              <div className="compact-list">
                {tools.slice(0, 8).map((tool) => (
                  <div key={tool.name}>
                    <strong>{tool.name}</strong>
                    <span>{tool.compensatable ? "Compensatable" : "No compensation"}</span>
                  </div>
                ))}
                {!tools.length ? <EmptyState icon={Wrench} title="Tool catalog unavailable" body="Enter the access password to read the tool registry." /> : null}
              </div>
            </section>
          </section>
        ) : null}

        {activeProductView === "audit" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Governance</p>
                <h3>Audit and compliance</h3>
                <p>Inspect tasks, tool calls, approval actions, and audit-chain integrity.</p>
              </div>
              <span className={`module-badge ${auditValid ? "ok" : "warn"}`}>{auditLabel(auditValid)}</span>
            </div>
            <div className="audit-layout">
              <section className="panel-card">
                <div className="section-title">
                  <Database size={16} />
                  Audit events
                </div>
                <div className="timeline">
                  {auditEvents.slice(0, 10).map((event, index) => (
                    <div className="timeline-row" key={`${event.event_type}-${index}`}>
                      <span>{event.event_type || "event"}</span>
                      <p>{shortText(event.timestamp, "local")}</p>
                    </div>
                  ))}
                  {!auditEvents.length ? <EmptyState icon={Database} title="No audit events" body="Enter the access password to view audit events for the current tenant." /> : null}
                </div>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <ShieldCheck size={16} />
                  Compliance checks
                </div>
                <div className="check-list">
                  {deploymentChecks.map((item) => (
                    <div key={item.label}>
                      <strong>{item.label}</strong>
                      <span className={item.ok ? "ok" : "warn"}>{item.value}</span>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </section>
        ) : null}

        {activeProductView === "settings" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Admin Settings</p>
                <h3>Settings and release checks</h3>
                <p>Confirm API, authorization, model, tool execution mode, and repository release status.</p>
              </div>
              <span className="module-badge">Tenant {tenantName}</span>
            </div>
            <div className="settings-grid">
              <section className="panel-card">
                <div className="section-title">
                  <Settings size={16} />
                  Runtime configuration
                </div>
                <dl className="fact-list">
                  <div>
                    <dt>API</dt>
                    <dd>{API_BASE}</dd>
                  </div>
                  <div>
                    <dt>Identity mode</dt>
                    <dd>{identityMode}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{health?.chat_model || "--"}</dd>
                  </div>
                  <div>
                    <dt>Tool mode</dt>
                    <dd>{health?.tool_execution_mode || "--"}</dd>
                  </div>
                </dl>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <GitBranch size={16} />
                  Pre-release Git checks
                </div>
                <div className="release-checklist">
                  <p>The current repository includes a structure migration: old root files were removed and new `backend/`, `frontend/`, and `infra/` folders should be reviewed before staging.</p>
                  <code>git status --short</code>
                  <code>git diff --stat</code>
                </div>
              </section>
              <section className="panel-card production-card">
                <div className="section-title">
                  <ShieldCheck size={16} />
                  Live integration gates
                  <span className="inline-loading">
                    Verified {productionCheckSummary.verified} | Pending {productionCheckSummary.configured} | Failed {productionCheckSummary.failed}
                  </span>
                </div>
                <div className="readiness-matrix">
                  {productionReadinessItems.map((item) => (
                    <article className={item.status} key={item.id}>
                      <span className={`state-chip ${item.status === "verified" ? "ok" : item.status === "failed" ? "danger" : "warn"}`}>
                        {item.status === "verified"
                          ? "Verified"
                          : item.status === "configured"
                            ? "Configured"
                            : item.status === "failed"
                              ? "Failed"
                              : "Not configured"}
                      </span>
                      <div>
                        <strong>{item.label}</strong>
                        <p>{item.detail}</p>
                        <em>{item.verification}{item.latency_ms ? ` | ${item.latency_ms}ms` : ""}</em>
                        <p className="next-step">{item.next_step}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <Activity size={16} />
                  Observability summary
                </div>
                <div className="ops-summary">
                  <div>
                    <strong>{operations ? `${Math.round(operations.task_success_rate * 100)}%` : "--"}</strong>
                    <span>Task success rate</span>
                  </div>
                  <div>
                    <strong>{failedToolCount}</strong>
                    <span>Tool failures</span>
                  </div>
                  <div>
                    <strong>{readinessWarnings.length}</strong>
                    <span>Launch warnings</span>
                  </div>
                </div>
              </section>
            </div>
          </section>
        ) : null}
      </section>

      <aside className="evidence-panel">
        <div className="inspector-tabs" role="tablist" aria-label="Runtime sidebar">
          {inspectorTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                aria-selected={activeInspector === tab.id}
                className={activeInspector === tab.id ? "active" : ""}
                key={tab.id}
                onClick={() => setActiveInspector(tab.id)}
                role="tab"
                type="button"
              >
                <Icon size={15} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {activeInspector === "overview" ? (
          <>
            {pendingApprovals.length || failedToolCount ? (
              <section className="panel-card attention-card">
                <div className="section-title">
                  <AlertTriangle size={16} />
                  Priority actions
                </div>
                <div className="priority-list">
                  {pendingApprovals.length ? (
                    <button type="button" onClick={() => setActiveInspector("actions")}>
                      <span className="state-chip warn">Pending review</span>
                      <p>{pendingApprovals.length} actions need confirmation</p>
                    </button>
                  ) : null}
                  {failedToolCount ? (
                    <button type="button" onClick={() => setActiveInspector("actions")}>
                      <span className="state-chip danger">Tool failures</span>
                      <p>{failedToolCount} executions failed. Review connector settings or parameters.</p>
                    </button>
                  ) : null}
                </div>
              </section>
            ) : null}

            <section className="panel-card priority-card">
              <div className="section-title">
                <ShieldCheck size={16} />
                Runtime status
                {isRefreshingOps ? <span className="inline-loading">Refreshing</span> : null}
              </div>
              <div className="metric-grid">
                <div>
                  <strong>{score ?? "--"}</strong>
                  <span>Readiness score</span>
                </div>
                <div>
                  <strong>{operations?.task_count ?? tasks.length}</strong>
                  <span>Tasks</span>
                </div>
                <div>
                  <strong>{connectorSummary(connectors)}</strong>
                  <span>Connectors</span>
                </div>
              </div>
              <dl className="fact-list">
                <div>
                  <dt>Tool mode</dt>
                  <dd>{health?.tool_execution_mode || "--"}</dd>
                </div>
                <div>
                  <dt>Database</dt>
                  <dd>{health?.database_backend || "--"}</dd>
                </div>
                <div>
                  <dt>Vector store</dt>
                  <dd>{health?.vector_backend || "--"}</dd>
                </div>
              </dl>
              <div className="ops-summary">
                <div>
                  <strong>{operations ? `${Math.round(operations.task_success_rate * 100)}%` : "--"}</strong>
                  <span>Task success rate</span>
                </div>
                <div>
                  <strong>{operations?.tool_execution_count ?? toolExecutions.length}</strong>
                  <span>Tool executions</span>
                </div>
                <div>
                  <strong>{operations?.tool_status_counts?.FAILED ?? 0}</strong>
                  <span>Tool failures</span>
                </div>
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <AlertTriangle size={16} />
                Launch checks
              </div>
              <div className="check-list">
                {deploymentChecks.map((item) => (
                  <div key={item.label}>
                    <strong>{item.label}</strong>
                    <span className={item.ok ? "ok" : "warn"}>{item.value}</span>
                  </div>
                ))}
              </div>
              {readinessWarnings.length ? (
                <div className="warning-list">
                  {readinessWarnings.slice(0, 4).map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              ) : (
                <EmptyState icon={ShieldCheck} tone="ok" title="Launch checks passed" body="The current runtime configuration has no blocking readiness warnings." />
              )}
            </section>
          </>
        ) : null}

        {activeInspector === "trace" ? (
          <>
            <section className="panel-card">
              <div className="section-title">
                <FileText size={16} />
                Citations and context
              </div>
              <div className="evidence-note">
                {latestUserQuestion
                  ? `Latest question: ${shortText(latestUserQuestion)}`
                  : "Submit a conversation to show the latest question and supporting evidence here."}
              </div>
              <div className="citation-list">
                {latestAssistantEvidence.slice(0, 4).map((item, index) => (
                  <div className="citation-row evidence-card" key={`${item.source}-${index}`}>
                    <div className="evidence-card-head">
                      <strong>{item.source}</strong>
                      <span>{inferPageLabel(item.source)}</span>
                    </div>
                    <p>{shortText(item.snippet, "No citation excerpt")}</p>
                    <div className="evidence-meta">
                      <span className={`state-chip ${keywordHits(latestUserQuestion, item.snippet).length ? "ok" : "neutral"}`}>
                        <SearchCheck size={12} />
                        {evidenceReliability(item, latestUserQuestion)}
                      </span>
                      {keywordHits(latestUserQuestion, item.snippet).map((hit) => (
                        <span key={hit}>{hit}</span>
                      ))}
                    </div>
                  </div>
                ))}
                {!latestAssistantEvidence.length ? (
                  <EmptyState icon={FileText} title="Waiting for evidence" body="After a policy Q&A request, sources, excerpts, pages, and keyword hits appear here." />
                ) : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <GitBranch size={16} />
                Task replay
              </div>
              <div className="timeline">
                {tasks.slice(0, 5).map((task) => (
                  <button className="timeline-button" type="button" key={task.task_id} onClick={() => selectTask(task.task_id)} disabled={loadingTaskId === task.task_id}>
                    <span>{loadingTaskId === task.task_id ? "Loading" : statusLabel(task.status)}</span>
                    <p>{shortText(task.input_text)}</p>
                  </button>
                ))}
                {!tasks.length ? <EmptyState icon={GitBranch} title="No task replay" body="Send an agent request to create task records and an event timeline." /> : null}
              </div>
              {selectedTask ? (
                <div className="event-list">
                  <div className="trace-summary">
                    <div>
                      <span>Task</span>
                      <strong>{statusLabel(selectedTask.status)}</strong>
                    </div>
                    <div>
                      <span>Intent</span>
                      <strong>{selectedTask.intent || "--"}</strong>
                    </div>
                    <div>
                      <span>Events</span>
                      <strong>{selectedTask.events?.length || 0}</strong>
                    </div>
                  </div>
                  {(selectedTask.events || []).map((event) => (
                    <div className="event-row trace-event-row" key={event.id}>
                      <div>
                        <strong>{event.event_type}</strong>
                        <p>{eventSummary(event)}</p>
                      </div>
                      <span>{formatDateTime(event.created_at)}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          </>
        ) : null}

        {activeInspector === "actions" ? (
          <>
            <section className="panel-card">
              <div className="section-title">
                <ClipboardList size={16} />
                Actions and approvals
              </div>
              <div className="timeline">
                {[...approvals, ...interviews].slice(0, 6).map((item) => (
                  <div className="timeline-row" key={`${item.id}-${item.status}`}>
                    <span>{statusLabel(item.status)}</span>
                    <div>
                      <p>{shortText(item.candidate_name || item.action_type || item.subject_ref)}</p>
                      {item.action_type && item.status === "PENDING" ? (
                        <div className="row-actions">
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "approve")}>
                            <Check size={13} />
                            {pendingApprovalId === item.id ? "Submitting" : "Approve"}
                          </button>
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "reject")}>
                            <X size={13} />
                            Reject
                          </button>
                        </div>
                      ) : null}
                      {item.action_type && item.status === "APPROVED" ? (
                        <div className="row-actions">
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "execute")}>
                            <Play size={13} />
                            {pendingApprovalId === item.id ? "Executing" : "Execute"}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                {!approvals.length && !interviews.length ? (
                  <EmptyState icon={ClipboardList} title="No action records" body="Interview scheduling, approvals, or compensating actions generated by the agent appear here." />
                ) : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Wrench size={16} />
                Tool catalog
              </div>
              <div className="compact-list">
                {tools.slice(0, 5).map((tool) => (
                  <div key={tool.name}>
                    <strong>{tool.name}</strong>
                    <span>{tool.compensatable ? "Compensatable" : "No compensation"}</span>
                  </div>
                ))}
                {!tools.length ? <EmptyState icon={Wrench} title="Tool catalog unavailable" body="Enter the access password to read the tool registry, or confirm the backend is running." /> : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Activity size={16} />
                Recent tool executions
              </div>
              <div className="timeline">
                {toolExecutions.slice(0, 6).map((execution) => (
                  <button
                    className={`timeline-button tool-execution-button ${selectedToolExecution?.id === execution.id ? "selected" : ""}`}
                    key={execution.id}
                    onClick={() => setSelectedToolExecutionId(execution.id)}
                    type="button"
                  >
                    <span className={`state-chip ${statusClass(execution.status)}`}>{statusLabel(execution.status)}</span>
                    <div>
                      <p>{execution.tool_name}</p>
                      <p className="subtle">
                        Attempts {execution.attempts} | {shortText(execution.idempotency_key, "No idempotency key")}
                      </p>
                    </div>
                  </button>
                ))}
                {!toolExecutions.length ? <EmptyState icon={Activity} title="No tool executions" body="Trigger a candidate follow-up action to show execution status, duration, and result here." /> : null}
              </div>
              {selectedToolExecution ? (
                <div className="tool-detail">
                  <div className="tool-detail-grid">
                    <div>
                      <Clock3 size={13} />
                      <span>{formatDuration(selectedToolExecution.started_at, selectedToolExecution.completed_at)}</span>
                    </div>
                    <div>
                      <RotateCcw size={13} />
                      <span>{selectedToolExecution.attempts} attempts</span>
                    </div>
                    <div>
                      <Hash size={13} />
                      <span>{shortText(selectedToolExecution.idempotency_key, "No idempotency key")}</span>
                    </div>
                  </div>
                  <div className="json-preview">
                    <strong>{selectedToolExecution.error_json ? "Error details" : "Result"}</strong>
                    <pre>{previewJson(parseJsonSafe(selectedToolExecution.error_json || selectedToolExecution.response_json))}</pre>
                  </div>
                </div>
              ) : null}
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Plug size={16} />
                Connectors
              </div>
              <div className="compact-list">
                {connectors.slice(0, 6).map((connector) => (
                  <div key={connector.name}>
                    <strong>{connector.name}</strong>
                    <span>{statusLabel(connector.status)}</span>
                  </div>
                ))}
                {!connectors.length ? <EmptyState icon={Plug} title="Connectors not loaded" body="Connector catalog access requires permission. If the password is set, confirm the backend is available." /> : null}
              </div>
            </section>
          </>
        ) : null}

        {activeInspector === "audit" ? (
          <section className="panel-card">
            <div className="section-title">
              <Database size={16} />
              Audit chain
            </div>
            <div className="timeline">
              {auditEvents.slice(0, 6).map((event, index) => (
                <div className="timeline-row" key={`${event.event_type}-${index}`}>
                  <span>{event.event_type || "event"}</span>
                  <p>{shortText(event.timestamp, "local")}</p>
                </div>
              ))}
              {!auditEvents.length ? <EmptyState icon={Database} title="Audit events not loaded" body="Enter the access password to view audit events. If there are no events, the current tenant has no displayable records yet." /> : null}
            </div>
          </section>
        ) : null}
      </aside>
    </main>
  );
}
