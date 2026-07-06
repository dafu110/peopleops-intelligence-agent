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
      "浣犲ソ锛屾垜鏄?PeopleOps Intelligence Assistant銆備綘鍙互涓婁紶绠€鍘嗐€佺矘璐?JD锛屾垨鐩存帴璇㈤棶鍒跺害銆佹姤閿€銆佽€冨嫟銆佺鍒╁拰鍊欓€変汉璺熻繘鍔ㄤ綔銆?,
  },
];

function statusTone(ok?: boolean) {
  return ok ? "status-pill ok" : "status-pill warn";
}

function readinessLabel(ok?: boolean) {
  return ok ? "鐢熶骇灏辩华" : "寰呭鏍?;
}

function auditLabel(ok?: boolean) {
  return ok ? "瀹¤鏈夋晥" : "寰呮鏌?;
}

function shortText(value: string | undefined, fallback = "鏆傛棤") {
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

function previewJson(value: unknown, fallback = "鏆傛棤璇︽儏") {
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
  if (!item.snippet) return "鏃犵墖娈?;
  if (hits.length >= 2) return "鍏抽敭璇嶅懡涓?;
  if (item.source) return "鍙拷婧?;
  return "寰呭鏍?;
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
    APPROVED: "宸查€氳繃",
    CANCELLED: "宸插彇娑?,
    COMPLETED: "宸插畬鎴?,
    CONFIGURED: "宸查厤缃?,
    ERROR: "閿欒",
    FAILED: "澶辫触",
    PENDING: "寰呭鎵?,
    READY: "灏辩华",
    REJECTED: "宸叉嫆缁?,
    RUNNING: "杩愯涓?,
    SUCCESS: "鎴愬姛",
    SUCCEEDED: "鎴愬姛",
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
      setError(err instanceof Error ? err.message : "鏃犳硶璇诲彇鍚庣鐘舵€?);
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
          content: response.reply || "绯荤粺娌℃湁杩斿洖鏈夋晥鍥炲銆?,
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
          content: "璇锋眰娌℃湁瀹屾垚銆傝妫€鏌ュ悗绔?API銆佽闂彛浠ゆ垨妯″瀷閰嶇疆銆?,
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
      setError(err instanceof Error ? err.message : "瀹℃壒鐘舵€佹洿鏂板け璐?);
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
    { label: "妯″瀷閰嶇疆", ok: Boolean(health?.model_configured), value: health?.chat_model || "--" },
    { label: "韬唤妯″紡", ok: Boolean(health), value: identityMode },
    { label: "鏁版嵁搴?, ok: health?.database_backend === "sqlite" || Boolean(health?.database_url_configured), value: health?.database_backend || "--" },
    { label: "鍚戦噺妫€绱?, ok: health?.vector_backend === "chroma" || Boolean(health?.vector_store_url_configured), value: health?.vector_backend || "--" },
    { label: "瀵硅薄瀛樺偍", ok: Boolean(health?.object_storage_configured) || !readiness?.enterprise_warnings?.some((item) => item.includes("OBJECT_STORAGE_URI")), value: health?.object_storage_configured ? "configured" : "local" },
    { label: "瀹¤閾?, ok: Boolean(auditValid), value: auditValid ? "valid" : "check" },
  ];
  const materialStatus = resumeFiles.length ? `${resumeFiles.length} 涓枃浠禶 : resumeText.trim() ? "宸茬矘璐寸畝鍘? : "寰呰ˉ鏉愭枡";
  const jdStatus = jdText.trim() ? "宀椾綅宸插氨缁? : "寰呰ˉ宀椾綅";
  const inspectorTabs = [
    { id: "overview" as const, label: "姒傝", icon: ShieldCheck },
    { id: "trace" as const, label: "杩借釜", icon: GitBranch },
    { id: "actions" as const, label: "鍔ㄤ綔", icon: Wrench },
    { id: "audit" as const, label: "瀹¤", icon: Database },
  ];
  const quickPrompts = [
    "杩欎唤绠€鍘嗗拰 JD 鐨勫尮閰嶅害濡備綍锛?,
    "鍑哄樊浣忓鎶ラ攢鏍囧噯鏄粈涔堬紵",
    "甯垜鐢熸垚鍊欓€変汉闈㈣瘯璺熻繘鍔ㄤ綔銆?,
  ];
  const overviewSignals = [
    { label: "鏉愭枡", value: materialStatus, tone: resumeText.trim() || resumeFiles.length ? "ok" : "warn" },
    { label: "宀椾綅", value: jdStatus, tone: jdText.trim() ? "ok" : "warn" },
    { label: "寰呭鎵?, value: approvals.filter((item) => item.status === "PENDING").length.toString(), tone: approvals.some((item) => item.status === "PENDING") ? "warn" : "ok" },
    { label: "瀹¤", value: auditLabel(auditValid), tone: auditValid ? "ok" : "warn" },
  ];
  const workflowSteps = [
    {
      label: "1",
      title: "鍑嗗鏉愭枡",
      body: materialStatus,
      ok: Boolean(resumeText.trim() || resumeFiles.length),
    },
    {
      label: "2",
      title: "琛ュ厖宀椾綅",
      body: jdStatus,
      ok: Boolean(jdText.trim()),
    },
    {
      label: "3",
      title: "鐢熸垚鍒ゆ柇涓庡姩浣?,
      body: lastTaskId ? "宸叉湁浠诲姟鍥炴斁" : "鍙戦€侀棶棰樺悗娌夋穩璇佹嵁",
      ok: Boolean(lastTaskId),
    },
  ];
  const pendingApprovals = approvals.filter((item) => item.status === "PENDING");
  const failedToolCount = operations?.tool_status_counts?.FAILED ?? toolExecutions.filter((item) => statusClass(item.status) === "danger").length;
  const tenantName = operations?.tenant_id || "default";
  const hasApiIssue = Boolean(error);
  const hasAuthGate = Boolean(health?.access_password_required && !accessPassword);
  const healthBanner = hasApiIssue
    ? { tone: "danger", title: "鍚庣杩炴帴寮傚父", body: error }
    : hasAuthGate
      ? { tone: "warn", title: "闇€瑕佽闂彛浠?, body: "杈撳叆璁块棶鍙ｄ护鍚庢墠鑳藉姞杞藉鎵广€佸璁°€佽繛鎺ュ櫒鍜屽伐鍏锋墽琛岃褰曘€? }
      : !ready
        ? { tone: "warn", title: "鐢熶骇灏辩华搴﹀緟澶嶆牳", body: readinessWarnings[0] || "褰撳墠鐜杩樻湁閰嶇疆椤归渶瑕佺‘璁ゃ€? }
        : null;
  const candidateRecords = [
    {
      name: resumeFiles[0]?.replace(/\.[^.]+$/, "") || (resumeText.trim() ? "褰撳墠鍊欓€変汉" : "寰呭鍏ュ€欓€変汉"),
      role: jdText.trim() ? "宸插叧鑱斿綋鍓?JD" : "寰呭叧鑱斿矖浣?,
      stage: lastTaskId ? "宸插垎鏋? : resumeText.trim() || resumeFiles.length ? "寰呭垎鏋? : "寰呭鍏?,
      fit: lastTaskId ? "宸茬敓鎴愬缓璁? : jdText.trim() && (resumeText.trim() || resumeFiles.length) ? "鍙紑濮嬪尮閰? : "璧勬枡涓嶅畬鏁?,
    },
    {
      name: "閿€鍞繍钀ョ粡鐞嗗€欓€夋睜",
      role: "绀轰緥闃熷垪",
      stage: "寰呭鍏?,
      fit: "杩炴帴 ATS 鍚庡悓姝?,
    },
    {
      name: "鐮斿彂鏁堣兘鍊欓€夋睜",
      role: "绀轰緥闃熷垪",
      stage: "寰呭鍏?,
      fit: "杩炴帴 ATS 鍚庡悓姝?,
    },
  ];
  const navigationItems = [
    { id: "workspace" as const, label: "宸ヤ綔鍙?, value: "Agent 涓灑", icon: Layers3 },
    { id: "candidates" as const, label: "鍊欓€変汉", value: `${resumeFiles.length || (resumeText.trim() ? 1 : 0)} 浠芥潗鏂檂, icon: Users },
    { id: "approvals" as const, label: "瀹℃壒", value: `${pendingApprovals.length} 寰呭鐞哷, icon: ClipboardList },
    { id: "connectors" as const, label: "杩炴帴鍣?, value: connectorSummary(connectors), icon: Plug },
    { id: "audit" as const, label: "瀹¤", value: auditLabel(auditValid), icon: ShieldCheck },
    { id: "settings" as const, label: "璁剧疆", value: "閰嶇疆涓績", icon: Settings },
  ];
  const usageItems = [
    { label: "浠诲姟", value: operations?.task_count ?? tasks.length },
    { label: "宸ュ叿璋冪敤", value: operations?.tool_execution_count ?? toolExecutions.length },
    { label: "瀹℃壒", value: approvals.length },
  ];
  const fallbackProductionChecks: ProductionCheckRecord[] = [
    {
      id: "postgresql",
      label: "PostgreSQL 瀹炰緥寤哄簱銆佽縼绉汇€佽鍐欏洖鏀?,
      status: health?.database_backend === "postgresql" && health?.database_url_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${health?.database_backend || "--"} / DATABASE_URL=${health?.database_url_configured ? "configured" : "missing"}`,
      next_step: "杩炴帴鍚庣 /production/checks 鑾峰彇瀹炴満鑱旇皟闂ㄧ銆?,
    },
    {
      id: "qdrant",
      label: "Qdrant 鎴栫敓浜у悜閲忓簱绱㈠紩鍐欏叆/妫€绱?,
      status: health?.vector_backend !== "chroma" && health?.vector_store_url_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${health?.vector_backend || "--"} / VECTOR_STORE_URL=${health?.vector_store_url_configured ? "configured" : "missing"}`,
      next_step: "閰嶇疆鐢熶骇鍚戦噺搴撳悗鎵ц绱㈠紩鍐欏叆銆佹绱㈠拰 RAG eval銆?,
    },
    {
      id: "object_storage",
      label: "S3/MinIO 瀵硅薄涓婁紶銆佷笅杞姐€佹潈闄愩€佺敓鍛藉懆鏈?,
      status: health?.object_storage_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: health?.object_storage_configured ? "OBJECT_STORAGE_URI configured" : "OBJECT_STORAGE_URI missing",
      next_step: "鎵ц put/get/delete 鍜岀敓鍛藉懆鏈熺瓥鐣ラ獙璇併€?,
    },
    {
      id: "oidc",
      label: "OIDC provider 鐪熷疄 token 鏍￠獙鍜岃鑹叉槧灏?,
      status: health?.oidc_enabled ? "configured" : "not_configured",
      verification: "configuration",
      detail: identityMode,
      next_step: "浣跨敤鐪熷疄 bearer token 璋冪敤 /me 楠岃瘉瑙掕壊鏄犲皠銆?,
    },
    {
      id: "external_tools",
      label: "ATS/鏃ュ巻鐪熷疄 API 鍑瘉銆佸け璐ラ噸璇曘€佸箓绛夈€佽ˉ鍋?,
      status: connectors.some((item) => item.status === "configured" && ["ats", "calendar", "collaboration"].includes(item.category)) ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${connectorSummary(connectors)} connectors configured`,
      next_step: "鎵ц娌欑 ATS 闃舵鍙樻洿銆佹棩鍘嗛個璇枫€佸け璐ラ噸璇曞拰琛ュ伩璁板綍楠岃瘉銆?,
    },
    {
      id: "network_ops",
      label: "鐢熶骇缃戠粶銆乀LS銆丆ORS銆佺綉鍏炽€佹棩蹇?鍛婅閾捐矾",
      status: health?.trusted_sso_enabled || health?.oidc_enabled ? "configured" : "not_configured",
      verification: "configuration",
      detail: `rate limit / identity / gateway readiness`,
      next_step: "鍦ㄧ敓浜х綉鍏抽獙璇?TLS銆丆ORS銆佽闂棩蹇楀拰鍛婅璺敱銆?,
    },
    {
      id: "e2e_demo",
      label: "鍏ㄩ摼璺鍒扮婕旂ず鍜屽洖婊氭紨缁?,
      status: "configured",
      verification: "runbook",
      detail: "Runbook exists; requires operator evidence.",
      next_step: "璺戜笂浼犮€侀棶绛斻€佸鎵广€佹墽琛屻€佸璁￠摼鍜屽洖婊氭紨缁冦€?,
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

        <section className="tenant-card" aria-label="绉熸埛淇℃伅">
          <div className="tenant-mark">
            <Building2 size={17} />
          </div>
          <div>
            <span>褰撳墠绉熸埛</span>
            <strong>{tenantName}</strong>
          </div>
          <em>Pro</em>
        </section>

        <nav className="side-nav" aria-label="浜у搧瀵艰埅">
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
            鍊欓€変汉涓庡矖浣嶄笂涓嬫枃
          </div>
          <label className="file-drop">
            <Upload size={18} />
            <span>{isExtracting ? "姝ｅ湪瑙ｆ瀽鏂囨。" : "涓婁紶绠€鍘嗘垨鏉愭枡"}</span>
            <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
          </label>
          <div className="file-list">
            {resumeFiles.length ? resumeFiles.map((name) => <span key={name}>{name}</span>) : "鏀寔 PDF銆丏OCX銆乀XT銆丮D锛屼笂浼犲悗浼氳皟鐢ㄥ悗绔В鏋愭枃鏈€?}
          </div>
          <textarea
            value={resumeText}
            onChange={(event) => setResumeText(event.target.value)}
            placeholder="鍊欓€変汉绠€鍘嗐€侀潰璇曡褰曟垨鍏抽敭鎽樿浼氬嚭鐜板湪杩欓噷銆?
            rows={7}
          />
          <textarea
            value={jdText}
            onChange={(event) => setJdText(event.target.value)}
            placeholder="绮樿创宀椾綅 JD銆佽兘鍔涜姹傘€佸勾闄愯姹傘€?
            rows={7}
          />
        </section>

        <section className="panel-section compact">
          <div className="section-title">
            <LockKeyhole size={16} />
            璁块棶涓庡悗绔?          </div>
          <form className="access-form" onSubmit={(event) => event.preventDefault()}>
            <input
              aria-label="璁块棶鍙ｄ护"
              autoComplete="current-password"
              value={accessPassword}
              onChange={(event) => setAccessPassword(event.target.value)}
              onBlur={(event) => refreshOperationalData(event.currentTarget.value)}
              type="password"
              placeholder="濡傛灉鍚敤 ACCESS_PASSWORD锛屽湪杩欓噷杈撳叆"
            />
          </form>
          <p className="subtle">API: {API_BASE}</p>
        </section>

        <section className="usage-card" aria-label="鏈湀鐢ㄩ噺">
          <div className="section-title">
            <BarChart3 size={16} />
            鏈湀鐢ㄩ噺
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
            <p>闈㈠悜澶氱鎴?PeopleOps 鍥㈤槦鐨?AI 宸ヤ綔鍙帮細闆嗕腑澶勭悊鏀跨瓥闂瓟銆佺畝鍘嗗尮閰嶃€佸€欓€変汉璺熻繘銆佸鎵瑰拰瀹¤杩借釜銆?/p>
          </div>
          <div className="header-ops">
            <div className="workspace-actions" aria-label="宸ヤ綔鍖哄姩浣?>
              <button type="button" title="閫氱煡">
                <AlertTriangle size={15} />
              </button>
              <button type="button" title="璁剧疆">
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

        <section className="workflow-strip" aria-label="棣栨浣跨敤娴佺▼">
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
            <h3>鍊欓€変汉鏉愭枡</h3>
          </div>
          <div className="mobile-material-actions">
            <label className="file-drop compact-drop">
              <Upload size={16} />
              <span>{isExtracting ? "瑙ｆ瀽涓? : "涓婁紶"}</span>
              <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
            </label>
            <a className="link-button" href="#candidate-context">
              缂栬緫鏉愭枡
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
              <span>{lastTaskId || threadId || "鏂颁細璇?}</span>
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
                <p className="typing-state">姝ｅ湪妫€绱㈠埗搴︺€佸€欓€変汉涓婁笅鏂囧拰鍙墽琛屽姩浣?..</p>
              </article>
            ) : null}
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            <div className="prompt-rail" aria-label="蹇嵎闂">
              {quickPrompts.map((item) => (
                <button key={item} type="button" onClick={() => setPrompt(item)}>
                  {item}
                </button>
              ))}
            </div>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="渚嬪锛氬嚭宸綇瀹挎姤閿€鏍囧噯鏄粈涔堬紵杩欎唤绠€鍘嗗拰 JD 鏄惁鍖归厤锛熷府鎴戝畨鎺掑€欓€変汉鏄庡ぉ涓嬪崍闈㈣瘯銆?
              rows={3}
            />
            <button type="submit" disabled={isSending || !prompt.trim()}>
              <Send size={16} />
              {isSending ? "澶勭悊涓? : "鍙戦€?}
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
                <h3>鍊欓€変汉妗堜欢</h3>
                <p>缁熶竴鏌ョ湅鍊欓€変汉鏉愭枡銆佸矖浣嶅叧鑱斻€佸尮閰嶇姸鎬佸拰涓嬩竴姝ュ姩浣溿€?/p>
              </div>
              <label className="module-action">
                <Upload size={15} />
                瀵煎叆鏉愭枡
                <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
              </label>
            </div>
            <div className="data-table candidate-table">
              <div className="table-row table-head">
                <span>鍊欓€変汉/闃熷垪</span>
                <span>宀椾綅</span>
                <span>闃舵</span>
                <span>鍖归厤鐘舵€?/span>
              </div>
              {candidateRecords.map((candidate) => (
                <button className="table-row" key={candidate.name} type="button" onClick={() => setActiveProductView("workspace")}>
                  <strong>{candidate.name}</strong>
                  <span>{candidate.role}</span>
                  <span className={`state-chip ${candidate.stage === "宸插垎鏋? ? "ok" : "warn"}`}>{candidate.stage}</span>
                  <span>{candidate.fit}</span>
                </button>
              ))}
            </div>
            {!resumeText.trim() && !resumeFiles.length ? (
              <EmptyState icon={Users} tone="warn" title="杩樻病鏈夌湡瀹炲€欓€変汉鏉愭枡" body="瀵煎叆绠€鍘嗘垨杩炴帴 ATS 鍚庯紝杩欓噷浼氬睍绀虹湡瀹炲€欓€変汉闃熷垪銆? />
            ) : null}
          </section>
        ) : null}

        {activeProductView === "approvals" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Approval Center</p>
                <h3>瀹℃壒涓績</h3>
                <p>闆嗕腑澶勭悊 Agent 鐢熸垚鐨勫閮ㄥ姩浣溿€佹墽琛屾巿鏉冨拰鍙ˉ鍋挎搷浣溿€?/p>
              </div>
              <div className="segmented-summary">
                <span>{pendingApprovals.length} 寰呭鎵?/span>
                <span>{approvals.filter((item) => item.status === "APPROVED").length} 宸查€氳繃</span>
                <span>{approvals.filter((item) => item.status === "REJECTED").length} 宸叉嫆缁?/span>
              </div>
            </div>
            <div className="approval-board">
              {[...approvals, ...interviews].slice(0, 10).map((item) => (
                <article className="approval-item" key={`${item.id}-${item.status}`}>
                  <div>
                    <span className={`state-chip ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                    <strong>{shortText(item.candidate_name || item.action_type || item.subject_ref, "鍊欓€変汉鍔ㄤ綔")}</strong>
                    <p>{item.interview_time ? `闈㈣瘯鏃堕棿锛?{formatDateTime(item.interview_time)}` : "绛夊緟 HRBP 瀹℃牳鍚庢墽琛屻€?}</p>
                  </div>
                  {item.action_type && item.status === "PENDING" ? (
                    <div className="row-actions">
                      <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "approve")}>
                        <Check size={13} />
                        閫氳繃
                      </button>
                      <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "reject")}>
                        <X size={13} />
                        鎷掔粷
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
              {!approvals.length && !interviews.length ? (
                <EmptyState icon={ClipboardList} title="鏆傛棤瀹℃壒椤? body="褰?Agent 闇€瑕佸彂閫侀偖浠躲€佸畨鎺掗潰璇曟垨璋冪敤澶栭儴绯荤粺鏃讹紝浼氳繘鍏ュ鎵逛腑蹇冦€? />
              ) : null}
            </div>
          </section>
        ) : null}

        {activeProductView === "connectors" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Integration Hub</p>
                <h3>杩炴帴鍣ㄤ笌宸ュ叿</h3>
                <p>绠＄悊 ATS銆佹棩鍘嗐€侀偖浠躲€佸悜閲忓簱鍜屽璞″瓨鍌ㄧ瓑浼佷笟绯荤粺鎺ュ叆鐘舵€併€?/p>
              </div>
              <span className="module-badge">{connectorSummary(connectors)} 宸查厤缃?/span>
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
                        <p>杈撳叆鍙ｄ护鎴栭厤缃幆澧冨彉閲忓悗鍚屾</p>
                      </div>
                      <span className="state-chip neutral">寰呴厤缃?/span>
                    </article>
                  ))}
                </>
              ) : null}
            </div>
            <section className="panel-card">
              <div className="section-title">
                <Wrench size={16} />
                宸ュ叿娉ㄥ唽琛?              </div>
              <div className="compact-list">
                {tools.slice(0, 8).map((tool) => (
                  <div key={tool.name}>
                    <strong>{tool.name}</strong>
                    <span>{tool.compensatable ? "鍙ˉ鍋? : "鏃犺ˉ鍋?}</span>
                  </div>
                ))}
                {!tools.length ? <EmptyState icon={Wrench} title="宸ュ叿鐩綍涓嶅彲瑙? body="杈撳叆璁块棶鍙ｄ护鍚庡彲璇诲彇宸ュ叿 registry銆? /> : null}
              </div>
            </section>
          </section>
        ) : null}

        {activeProductView === "audit" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">Governance</p>
                <h3>瀹¤涓庡悎瑙?/h3>
                <p>鏌ョ湅浠诲姟銆佸伐鍏疯皟鐢ㄣ€佸鎵瑰姩浣滃拰瀹¤閾惧畬鏁存€с€?/p>
              </div>
              <span className={`module-badge ${auditValid ? "ok" : "warn"}`}>{auditLabel(auditValid)}</span>
            </div>
            <div className="audit-layout">
              <section className="panel-card">
                <div className="section-title">
                  <Database size={16} />
                  瀹¤浜嬩欢
                </div>
                <div className="timeline">
                  {auditEvents.slice(0, 10).map((event, index) => (
                    <div className="timeline-row" key={`${event.event_type}-${index}`}>
                      <span>{event.event_type || "event"}</span>
                      <p>{shortText(event.timestamp, "local")}</p>
                    </div>
                  ))}
                  {!auditEvents.length ? <EmptyState icon={Database} title="鏆傛棤瀹¤浜嬩欢" body="杈撳叆璁块棶鍙ｄ护鍚庡彲鏌ョ湅褰撳墠绉熸埛鐨勫璁′簨浠躲€? /> : null}
                </div>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <ShieldCheck size={16} />
                  鍚堣妫€鏌?                </div>
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
                <h3>璁剧疆涓庡彂甯冩鏌?/h3>
                <p>闆嗕腑纭 API銆侀壌鏉冦€佹ā鍨嬨€佸伐鍏锋墽琛屾ā寮忓拰浠撳簱鍙戝竷鐘舵€併€?/p>
              </div>
              <span className="module-badge">绉熸埛 {tenantName}</span>
            </div>
            <div className="settings-grid">
              <section className="panel-card">
                <div className="section-title">
                  <Settings size={16} />
                  杩愯閰嶇疆
                </div>
                <dl className="fact-list">
                  <div>
                    <dt>API</dt>
                    <dd>{API_BASE}</dd>
                  </div>
                  <div>
                    <dt>韬唤妯″紡</dt>
                    <dd>{identityMode}</dd>
                  </div>
                  <div>
                    <dt>妯″瀷</dt>
                    <dd>{health?.chat_model || "--"}</dd>
                  </div>
                  <div>
                    <dt>宸ュ叿妯″紡</dt>
                    <dd>{health?.tool_execution_mode || "--"}</dd>
                  </div>
                </dl>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <GitBranch size={16} />
                  鍙戝竷鍓?Git 妫€鏌?                </div>
                <div className="release-checklist">
                  <p>褰撳墠浠撳簱瀛樺湪缁撴瀯杩佺Щ鐥曡抗锛氭棫鏍圭洰褰曟枃浠跺垹闄わ紝鏂?`backend/`銆乣frontend/`銆乣infra/` 鐩綍灏氶渶纭鍚庡啀缁熶竴 stage銆?/p>
                  <code>git status --short</code>
                  <code>git diff --stat</code>
                </div>
              </section>
              <section className="panel-card production-card">
                <div className="section-title">
                  <ShieldCheck size={16} />
                  瀹炴満鑱旇皟闂ㄧ
                  <span className="inline-loading">
                    楠岃瘉閫氳繃 {productionCheckSummary.verified} 路 寰呴獙璇?{productionCheckSummary.configured} 路 澶辫触 {productionCheckSummary.failed}
                  </span>
                </div>
                <div className="readiness-matrix">
                  {productionReadinessItems.map((item) => (
                    <article className={item.status} key={item.id}>
                      <span className={`state-chip ${item.status === "verified" ? "ok" : item.status === "failed" ? "danger" : "warn"}`}>
                        {item.status === "verified"
                          ? "瀹炴満閫氳繃"
                          : item.status === "configured"
                            ? "宸查厤缃緟楠岃瘉"
                            : item.status === "failed"
                              ? "楠岃瘉澶辫触"
                              : "鏈厤缃?}
                      </span>
                      <div>
                        <strong>{item.label}</strong>
                        <p>{item.detail}</p>
                        <em>{item.verification}{item.latency_ms ? ` 路 ${item.latency_ms}ms` : ""}</em>
                        <p className="next-step">{item.next_step}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <Activity size={16} />
                  瑙傛祴鎬ф憳瑕?                </div>
                <div className="ops-summary">
                  <div>
                    <strong>{operations ? `${Math.round(operations.task_success_rate * 100)}%` : "--"}</strong>
                    <span>浠诲姟鎴愬姛鐜?/span>
                  </div>
                  <div>
                    <strong>{failedToolCount}</strong>
                    <span>宸ュ叿澶辫触</span>
                  </div>
                  <div>
                    <strong>{readinessWarnings.length}</strong>
                    <span>涓婄嚎鍛婅</span>
                  </div>
                </div>
              </section>
            </div>
          </section>
        ) : null}
      </section>

      <aside className="evidence-panel">
        <div className="inspector-tabs" role="tablist" aria-label="杩愯渚ф爮">
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
                  浼樺厛澶勭悊
                </div>
                <div className="priority-list">
                  {pendingApprovals.length ? (
                    <button type="button" onClick={() => setActiveInspector("actions")}>
                      <span className="state-chip warn">寰呭鎵?/span>
                      <p>{pendingApprovals.length} 涓姩浣滈渶瑕佺‘璁?/p>
                    </button>
                  ) : null}
                  {failedToolCount ? (
                    <button type="button" onClick={() => setActiveInspector("actions")}>
                      <span className="state-chip danger">宸ュ叿澶辫触</span>
                      <p>{failedToolCount} 娆℃墽琛屽け璐ワ紝寤鸿澶嶆牳杩炴帴鍣ㄦ垨鍙傛暟</p>
                    </button>
                  ) : null}
                </div>
              </section>
            ) : null}

            <section className="panel-card priority-card">
              <div className="section-title">
                <ShieldCheck size={16} />
                杩愯鐘舵€?                {isRefreshingOps ? <span className="inline-loading">鍒锋柊涓?/span> : null}
              </div>
              <div className="metric-grid">
                <div>
                  <strong>{score ?? "--"}</strong>
                  <span>灏辩华鍒?/span>
                </div>
                <div>
                  <strong>{operations?.task_count ?? tasks.length}</strong>
                  <span>浠诲姟鏁?/span>
                </div>
                <div>
                  <strong>{connectorSummary(connectors)}</strong>
                  <span>杩炴帴鍣?/span>
                </div>
              </div>
              <dl className="fact-list">
                <div>
                  <dt>宸ュ叿妯″紡</dt>
                  <dd>{health?.tool_execution_mode || "--"}</dd>
                </div>
                <div>
                  <dt>鏁版嵁搴?/dt>
                  <dd>{health?.database_backend || "--"}</dd>
                </div>
                <div>
                  <dt>鍚戦噺搴?/dt>
                  <dd>{health?.vector_backend || "--"}</dd>
                </div>
              </dl>
              <div className="ops-summary">
                <div>
                  <strong>{operations ? `${Math.round(operations.task_success_rate * 100)}%` : "--"}</strong>
                  <span>浠诲姟鎴愬姛鐜?/span>
                </div>
                <div>
                  <strong>{operations?.tool_execution_count ?? toolExecutions.length}</strong>
                  <span>宸ュ叿鎵ц</span>
                </div>
                <div>
                  <strong>{operations?.tool_status_counts?.FAILED ?? 0}</strong>
                  <span>宸ュ叿澶辫触</span>
                </div>
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <AlertTriangle size={16} />
                涓婄嚎妫€鏌?              </div>
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
                <EmptyState icon={ShieldCheck} tone="ok" title="涓婄嚎妫€鏌ラ€氳繃" body="褰撳墠杩愯閰嶇疆娌℃湁闃诲鎬у氨缁憡璀︺€? />
              )}
            </section>
          </>
        ) : null}

        {activeInspector === "trace" ? (
          <>
            <section className="panel-card">
              <div className="section-title">
                <FileText size={16} />
                寮曠敤涓庝笂涓嬫枃
              </div>
              <div className="evidence-note">
                {latestUserQuestion
                  ? `鏈€杩戦棶棰橈細${shortText(latestUserQuestion)}`
                  : "鎻愪氦涓诲璇濆悗锛岃繖閲屽睍绀烘渶杩戦棶棰樺拰鍏宠仈璇佹嵁銆?}
              </div>
              <div className="citation-list">
                {latestAssistantEvidence.slice(0, 4).map((item, index) => (
                  <div className="citation-row evidence-card" key={`${item.source}-${index}`}>
                    <div className="evidence-card-head">
                      <strong>{item.source}</strong>
                      <span>{inferPageLabel(item.source)}</span>
                    </div>
                    <p>{shortText(item.snippet, "鏆傛棤寮曠敤鐗囨")}</p>
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
                  <EmptyState icon={FileText} title="绛夊緟璇佹嵁" body="鍙戦€佷竴娆℃斂绛栭棶绛斿悗锛岃繖閲屼細灞曠ず鏉ユ簮銆佺墖娈点€侀〉鐮佸拰鍏抽敭璇嶅懡涓€? />
                ) : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <GitBranch size={16} />
                浠诲姟鍥炴斁
              </div>
              <div className="timeline">
                {tasks.slice(0, 5).map((task) => (
                  <button className="timeline-button" type="button" key={task.task_id} onClick={() => selectTask(task.task_id)} disabled={loadingTaskId === task.task_id}>
                    <span>{loadingTaskId === task.task_id ? "璇诲彇涓? : statusLabel(task.status)}</span>
                    <p>{shortText(task.input_text)}</p>
                  </button>
                ))}
                {!tasks.length ? <EmptyState icon={GitBranch} title="鏆傛棤浠诲姟鍥炴斁" body="鍙戦€佷竴娆?Agent 璇锋眰鍚庝細鍑虹幇浠诲姟璁板綍鍜屼簨浠舵椂闂寸嚎銆? /> : null}
              </div>
              {selectedTask ? (
                <div className="event-list">
                  <div className="trace-summary">
                    <div>
                      <span>浠诲姟</span>
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
                鍔ㄤ綔涓庡鎵?              </div>
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
                            {pendingApprovalId === item.id ? "鎻愪氦涓? : "閫氳繃"}
                          </button>
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "reject")}>
                            <X size={13} />
                            鎷掔粷
                          </button>
                        </div>
                      ) : null}
                      {item.action_type && item.status === "APPROVED" ? (
                        <div className="row-actions">
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "execute")}>
                            <Play size={13} />
                            {pendingApprovalId === item.id ? "鎵ц涓? : "鎵ц"}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                {!approvals.length && !interviews.length ? (
                  <EmptyState icon={ClipboardList} title="鏆傛棤鍔ㄤ綔璁板綍" body="褰?Agent 鐢熸垚闈㈣瘯瀹夋帓銆佸鎵规垨琛ュ伩鍔ㄤ綔鍚庯紝浼氬湪杩欓噷鍑虹幇銆? />
                ) : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Wrench size={16} />
                宸ュ叿鐩綍
              </div>
              <div className="compact-list">
                {tools.slice(0, 5).map((tool) => (
                  <div key={tool.name}>
                    <strong>{tool.name}</strong>
                    <span>{tool.compensatable ? "鍙ˉ鍋? : "鏃犺ˉ鍋?}</span>
                  </div>
                ))}
                {!tools.length ? <EmptyState icon={Wrench} title="宸ュ叿鐩綍涓嶅彲瑙? body="杈撳叆璁块棶鍙ｄ护鍚庡彲璇诲彇宸ュ叿 registry锛屾垨纭鍚庣宸插惎鍔ㄣ€? /> : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Activity size={16} />
                鏈€杩戝伐鍏锋墽琛?              </div>
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
                        灏濊瘯 {execution.attempts} 娆?路 {shortText(execution.idempotency_key, "鏃犲箓绛夐敭")}
                      </p>
                    </div>
                  </button>
                ))}
                {!toolExecutions.length ? <EmptyState icon={Activity} title="鏆傛棤宸ュ叿鎵ц" body="瑙﹀彂涓€娆″€欓€変汉璺熻繘鍔ㄤ綔鍚庯紝浼氭樉绀烘墽琛岀姸鎬併€佽€楁椂鍜岃繑鍥炵粨鏋溿€? /> : null}
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
                      <span>{selectedToolExecution.attempts} 娆″皾璇?/span>
                    </div>
                    <div>
                      <Hash size={13} />
                      <span>{shortText(selectedToolExecution.idempotency_key, "鏃犲箓绛夐敭")}</span>
                    </div>
                  </div>
                  <div className="json-preview">
                    <strong>{selectedToolExecution.error_json ? "閿欒璇︽儏" : "杩斿洖缁撴灉"}</strong>
                    <pre>{previewJson(parseJsonSafe(selectedToolExecution.error_json || selectedToolExecution.response_json))}</pre>
                  </div>
                </div>
              ) : null}
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Plug size={16} />
                杩炴帴鍣?              </div>
              <div className="compact-list">
                {connectors.slice(0, 6).map((connector) => (
                  <div key={connector.name}>
                    <strong>{connector.name}</strong>
                    <span>{statusLabel(connector.status)}</span>
                  </div>
                ))}
                {!connectors.length ? <EmptyState icon={Plug} title="杩炴帴鍣ㄦ湭璇诲彇" body="闇€瑕佽闂潈闄愬悗鎵嶈兘璇诲彇杩炴帴鍣ㄧ洰褰曪紱鑻ュ凡杈撳叆鍙ｄ护锛岃纭鍚庣鏈嶅姟鍙敤銆? /> : null}
              </div>
            </section>
          </>
        ) : null}

        {activeInspector === "audit" ? (
          <section className="panel-card">
            <div className="section-title">
              <Database size={16} />
              瀹¤閾?            </div>
            <div className="timeline">
              {auditEvents.slice(0, 6).map((event, index) => (
                <div className="timeline-row" key={`${event.event_type}-${index}`}>
                  <span>{event.event_type || "event"}</span>
                  <p>{shortText(event.timestamp, "local")}</p>
                </div>
              ))}
              {!auditEvents.length ? <EmptyState icon={Database} title="瀹¤浜嬩欢鏈姞杞? body="杈撳叆璁块棶鍙ｄ护鍚庡彲鏌ョ湅瀹¤浜嬩欢锛涙病鏈変簨浠舵椂琛ㄧず褰撳墠绉熸埛鏆傛棤鍙睍绀鸿褰曘€? /> : null}
            </div>
          </section>
        ) : null}
      </aside>
    </main>
  );
}
