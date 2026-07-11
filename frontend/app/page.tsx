"use client";

import {
  Activity,
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  Clock3,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  Hash,
  Layers3,
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
  ReadinessResponse,
  TaskRun,
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
import { ContextPanel } from "../components/context-panel";
import { createChatSubmission } from "../lib/chat-workflow.mjs";
import {
  auditLabel,
  connectorSummary,
  eventSummary,
  evidenceReliability,
  formatDateTime,
  formatDuration,
  getInitialInspectorView,
  getInitialProductView,
  inferPageLabel,
  keywordHits,
  parseJsonSafe,
  previewJson,
  readinessLabel,
  shortText,
  starterMessages,
  statusClass,
  statusLabel,
  statusTone,
} from "../lib/ui-helpers";
import type { InspectorView, ProductView } from "../lib/ui-helpers";

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
  const [activeInspector, setActiveInspector] = useState<InspectorView>(() => getInitialInspectorView());
  const [selectedToolExecutionId, setSelectedToolExecutionId] = useState<number | null>(null);
  const [isRefreshingOps, setIsRefreshingOps] = useState(false);
  const [loadingTaskId, setLoadingTaskId] = useState("");
  const [pendingApprovalId, setPendingApprovalId] = useState<number | null>(null);
  const [activeProductView, setActiveProductView] = useState<ProductView>(() => getInitialProductView());
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
      setError(err instanceof Error ? err.message : "无法读取后端状态");
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
        textParts.push(`《${extracted.filename}》\n${extracted.text}`);
      }
      setResumeText(textParts.join("\n\n"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "文档解析失败");
    } finally {
      setIsExtracting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const submission = createChatSubmission({ prompt, messages, isSending });
    if (!submission) return;

    const { message, messages: nextMessages } = submission;
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
          content: response.reply || "系统没有返回有效回复。",
          evidence: response.evidence || [],
        },
      ]);
      await refreshOperationalData(accessPassword);
      const task = await getTaskDetail(response.task_id, accessPassword);
      setSelectedTask(task);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent 请求失败");
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: "请求没有完成。请检查后端 API、访问口令或模型配置。",
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
      setError(err instanceof Error ? err.message : "审批状态更新失败");
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
      setError(err instanceof Error ? err.message : "任务详情读取失败");
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
        ? "口令"
        : "本地";
  const deploymentChecks = [
    { label: "模型配置", ok: Boolean(health?.model_configured), value: health?.chat_model || "--" },
    { label: "身份模式", ok: Boolean(health), value: identityMode },
    { label: "数据库", ok: health?.database_backend === "sqlite" || Boolean(health?.database_url_configured), value: health?.database_backend || "--" },
    { label: "向量检索", ok: health?.vector_backend === "chroma" || Boolean(health?.vector_store_url_configured), value: health?.vector_backend || "--" },
    { label: "对象存储", ok: Boolean(health?.object_storage_configured) || !readiness?.enterprise_warnings?.some((item) => item.includes("OBJECT_STORAGE_URI")), value: health?.object_storage_configured ? "已配置" : "本地" },
    { label: "审计链", ok: Boolean(auditValid), value: auditValid ? "有效" : "检查" },
  ];
  const materialStatus = resumeFiles.length ? `${resumeFiles.length} 个文件` : resumeText.trim() ? "已粘贴简历" : "补充材料";
  const jdStatus = jdText.trim() ? "岗位已就绪" : "补充岗位";
  const inspectorTabs = [
    { id: "overview" as const, label: "概览", icon: ShieldCheck },
    { id: "trace" as const, label: "追溯", icon: GitBranch },
    { id: "actions" as const, label: "动作", icon: Wrench },
    { id: "audit" as const, label: "审计", icon: Database },
  ];
  const quickPrompts = [
    "这份简历和 JD 的匹配度如何？",
    "差旅住宿报销标准是什么？",
    "生成候选人面试跟进动作。",
  ];
  const overviewSignals = [
    { label: "材料", value: materialStatus, tone: resumeText.trim() || resumeFiles.length ? "ok" : "warn" },
    { label: "岗位", value: jdStatus, tone: jdText.trim() ? "ok" : "warn" },
    { label: "证据", value: latestAssistantEvidence.length ? `${latestAssistantEvidence.length} 条引用` : "待生成", tone: latestAssistantEvidence.length ? "ok" : "warn" },
  ];
  const workflowSteps = [
    {
      label: "1",
      title: "准备材料",
      body: materialStatus,
      ok: Boolean(resumeText.trim() || resumeFiles.length),
    },
    {
      label: "2",
      title: "补充岗位",
      body: jdStatus,
      ok: Boolean(jdText.trim()),
    },
    {
      label: "3",
      title: "生成判断与动作",
      body: lastTaskId ? "已有任务回放" : "发送问题后沉淀证据",
      ok: Boolean(lastTaskId),
    },
  ];
  const pendingApprovals = approvals.filter((item) => item.status === "PENDING");
  const failedToolCount = operations?.tool_status_counts?.FAILED ?? toolExecutions.filter((item) => statusClass(item.status) === "danger").length;
  const tenantName = operations?.tenant_id || "default";
  const hasApiIssue = Boolean(error);
  const hasAuthGate = Boolean(health?.access_password_required && !accessPassword);
  const healthBanner = hasApiIssue
    ? { tone: "danger", title: "后端连接异常", body: error }
    : hasAuthGate
      ? { tone: "warn", title: "需要访问口令", body: "输入访问口令后才能加载审批、审计事件、连接器和工具执行记录。" }
      : !ready
        ? { tone: "warn", title: "生产就绪度待复核", body: readinessWarnings[0] || "当前环境仍有配置项需要确认。" }
        : null;
  const candidateRecords = [
    {
      name: resumeFiles[0]?.replace(/\.[^.]+$/, "") || (resumeText.trim() ? "当前候选人" : "待导入候选人"),
      role: jdText.trim() ? "已关联当前 JD" : "待关联岗位",
      stage: lastTaskId ? "已分析" : resumeText.trim() || resumeFiles.length ? "待分析" : "待导入",
      fit: lastTaskId ? "已生成建议" : jdText.trim() && (resumeText.trim() || resumeFiles.length) ? "可开始匹配" : "资料不完整",
    },
    {
      name: "销售运营经理候选池",
      role: "示例队列",
      stage: "待导入",
      fit: "连接 ATS 后同步",
    },
    {
      name: "研发效能候选池",
      role: "示例队列",
      stage: "待导入",
      fit: "连接 ATS 后同步",
    },
  ];
  const navigationItems = [
    { id: "workspace" as const, label: "工作台", value: "Agent 中枢", icon: Layers3 },
    { id: "candidates" as const, label: "候选人", value: `${resumeFiles.length || (resumeText.trim() ? 1 : 0)} 份材料`, icon: Users },
    { id: "approvals" as const, label: "审批", value: `${pendingApprovals.length} 待处理`, icon: ClipboardList },
    { id: "connectors" as const, label: "连接器", value: connectorSummary(connectors), icon: Plug },
    { id: "audit" as const, label: "审计", value: auditLabel(auditValid), icon: ShieldCheck },
    { id: "settings" as const, label: "设置", value: "配置中心", icon: Settings },
  ];
  const usageItems = [
    { label: "任务", value: operations?.task_count ?? tasks.length },
    { label: "工具调用", value: operations?.tool_execution_count ?? toolExecutions.length },
    { label: "审批", value: approvals.length },
  ];
  const fallbackProductionChecks: ProductionCheckRecord[] = [
    {
      id: "postgresql",
      label: "PostgreSQL 实例、迁移与读写验证",
      status: health?.database_backend === "postgresql" && health?.database_url_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${health?.database_backend || "--"} / DATABASE_URL=${health?.database_url_configured ? "已配置" : "缺失"}`,
      next_step: "连接后端 /production/checks 获取实机联调门禁。",
    },
    {
      id: "qdrant",
      label: "Qdrant 或生产向量库写入/检索",
      status: health?.vector_backend !== "chroma" && health?.vector_store_url_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${health?.vector_backend || "--"} / VECTOR_STORE_URL=${health?.vector_store_url_configured ? "已配置" : "缺失"}`,
      next_step: "配置生产向量库后执行索引写入、检索和 RAG 评测。",
    },
    {
      id: "object_storage",
      label: "S3/MinIO 对象上传、下载、权限与生命周期",
      status: health?.object_storage_configured ? "configured" : "not_configured",
      verification: "configuration",
      detail: health?.object_storage_configured ? "OBJECT_STORAGE_URI 已配置" : "OBJECT_STORAGE_URI 缺失",
      next_step: "验证 put/get/delete 操作和生命周期策略。",
    },
    {
      id: "oidc",
      label: "OIDC 真实 token 校验与角色映射",
      status: health?.oidc_enabled ? "configured" : "not_configured",
      verification: "configuration",
      detail: identityMode,
      next_step: "使用真实 bearer token 调用 /me 验证角色映射。",
    },
    {
      id: "external_tools",
      label: "ATS/日历 API 凭证、重试、幂等与补偿",
      status: connectors.some((item) => item.status === "configured" && ["ats", "calendar", "collaboration"].includes(item.category)) ? "configured" : "not_configured",
      verification: "configuration",
      detail: `${connectorSummary(connectors)} 个连接器已配置`,
      next_step: "执行沙箱 ATS 阶段变更、日历邀请、失败重试和补偿记录验证。",
    },
    {
      id: "network_ops",
      label: "生产网络、TLS、CORS、网关、日志与告警",
      status: health?.trusted_sso_enabled || health?.oidc_enabled ? "configured" : "not_configured",
      verification: "configuration",
      detail: `限流 / 身份 / 网关就绪度`,
      next_step: "在生产网关验证 TLS、CORS、访问日志和告警路由。",
    },
    {
      id: "e2e_demo",
      label: "全链路端到端演示与回滚演练",
      status: "configured",
      verification: "runbook",
      detail: "Runbook 已存在；仍需操作者证据。",
      next_step: "跑通上传、问答、审批、执行、审计链和回滚演练。",
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
      <ContextPanel
        accessPassword={accessPassword}
        activeProductView={activeProductView}
        handleFiles={handleFiles}
        isExtracting={isExtracting}
        jdText={jdText}
        navigationItems={navigationItems}
        refreshOperationalData={refreshOperationalData}
        resumeFiles={resumeFiles}
        resumeText={resumeText}
        setAccessPassword={setAccessPassword}
        setActiveProductView={setActiveProductView}
        setJdText={setJdText}
        setResumeText={setResumeText}
        tenantName={tenantName}
        usageItems={usageItems}
      />

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <p className="eyebrow">HRBP 运营控制台</p>
            <h2>{health?.app_name || "PeopleOps Agent 工作台"}</h2>
            <p>把政策问答、简历匹配和候选人跟进收束到一个可追溯的 Agent 工作流。</p>
          </div>
          <div className="header-ops">
            <div className="workspace-actions" aria-label="工作区动作">
              <button type="button" title="通知">
                <AlertTriangle size={15} />
              </button>
              <button type="button" title="设置">
                <Settings size={15} />
              </button>
            </div>
            <div className="status-cluster">
              <span className={statusTone(Boolean(health?.status))}>
                <CheckCircle2 size={14} />
                API {health?.status ? statusLabel(health.status) : "检查中"}
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
        <section className="focus-panel" aria-label="演示路径">
          <div className="focus-copy">
            <p className="eyebrow">默认演示路径</p>
            <h3>先给 Agent 一个 HR 场景，再查看证据和动作。</h3>
          </div>
          <div className="focus-steps">
            {workflowSteps.map((step) => (
              <div className={step.ok ? "focus-step done" : "focus-step"} key={step.label}>
                <span>{step.label}</span>
                <strong>{step.title}</strong>
              </div>
            ))}
          </div>
          <div className="focus-signals" aria-label="关键状态">
            {overviewSignals.map((item) => (
              <span className={item.tone} key={item.label}>
                {item.label} · {item.value}
              </span>
            ))}
          </div>
        </section>

        {error ? (
          <div className="notice">
            <AlertTriangle size={16} />
            {error}
          </div>
        ) : null}

        <section className="mobile-material-card">
          <div>
            <p className="eyebrow">候选人上下文</p>
            <h3>候选人材料</h3>
          </div>
          <div className="mobile-material-actions">
            <label className="file-drop compact-drop">
              <Upload size={16} />
              <span>{isExtracting ? "解析中" : "上传"}</span>
              <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
            </label>
            <a className="link-button" href="#candidate-context">
              编辑材料
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
              <p className="eyebrow">AI 运营工作区</p>
              <h3>PeopleOps 智能助手</h3>
            </div>
            <div className="session-meta">
              <span>{lastTaskId || threadId || "新会话"}</span>
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
                <p className="typing-state">正在检索制度、候选人上下文和可执行动作...</p>
              </article>
            ) : null}
          </div>

          <form className="composer" onSubmit={handleSubmit}>
            <div className="prompt-rail" aria-label="快捷问题">
              {quickPrompts.map((item) => (
                <button key={item} type="button" onClick={() => setPrompt(item)}>
                  {item}
                </button>
              ))}
            </div>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="例如：出差住宿报销标准是什么？这份简历和 JD 是否匹配？帮我安排候选人明天下午面试。"
              rows={3}
            />
            <button type="submit" disabled={isSending || !prompt.trim()}>
              <Send size={16} />
              {isSending ? "处理中" : "发送"}
            </button>
          </form>
        </section>
          </>
        ) : null}

        {activeProductView === "candidates" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">候选人 CRM</p>
                <h3>候选人档案</h3>
                <p>统一查看候选人材料、岗位关联、匹配状态和下一步动作。</p>
              </div>
              <label className="module-action">
                <Upload size={15} />
                导入材料
                <input multiple type="file" accept=".pdf,.docx,.txt,.md,.markdown" onChange={handleFiles} />
              </label>
            </div>
            <div className="data-table candidate-table">
              <div className="table-row table-head">
                <span>候选人/队列</span>
                <span>岗位</span>
                <span>阶段</span>
                <span>匹配状态</span>
              </div>
              {candidateRecords.map((candidate) => (
                <button className="table-row" key={candidate.name} type="button" onClick={() => setActiveProductView("workspace")}>
                  <strong>{candidate.name}</strong>
                  <span>{candidate.role}</span>
                  <span className={`state-chip ${candidate.stage === "已分析" ? "ok" : "warn"}`}>{candidate.stage}</span>
                  <span>{candidate.fit}</span>
                </button>
              ))}
            </div>
            {!resumeText.trim() && !resumeFiles.length ? (
              <EmptyState icon={Users} tone="warn" title="还没有真实候选人材料" body="导入简历或连接 ATS 后，这里会展示真实候选人队列。" />
            ) : null}
          </section>
        ) : null}

        {activeProductView === "approvals" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">审批中心</p>
                <h3>审批中心</h3>
                <p>集中处理 Agent 生成的外部动作、执行授权和可补偿操作。</p>
              </div>
              <div className="segmented-summary">
                <span>{pendingApprovals.length} 待审批</span>
                <span>{approvals.filter((item) => item.status === "APPROVED").length} 已通过</span>
                <span>{approvals.filter((item) => item.status === "REJECTED").length} 已拒绝</span>
              </div>
            </div>
            <div className="approval-board">
              {[...approvals, ...interviews].slice(0, 10).map((item) => (
                <article className="approval-item" key={`${item.id}-${item.status}`}>
                  <div>
                    <span className={`state-chip ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                    <strong>{shortText(item.candidate_name || item.action_type || item.subject_ref, "候选人动作")}</strong>
                    <p>{item.interview_time ? `面试时间：${formatDateTime(item.interview_time)}` : "等待 HRBP 审核后执行。"}</p>
                  </div>
                  {item.action_type && item.status === "PENDING" ? (
                    <div className="row-actions">
                      <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "approve")}>
                        <Check size={13} />
                        通过
                      </button>
                      <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "reject")}>
                        <X size={13} />
                        拒绝
                      </button>
                    </div>
                  ) : null}
                </article>
              ))}
              {!approvals.length && !interviews.length ? (
                <EmptyState icon={ClipboardList} title="暂无审批项" body="当 Agent 需要发送邮件、安排面试或调用外部系统时，会进入审批中心。" />
              ) : null}
            </div>
          </section>
        ) : null}

        {activeProductView === "connectors" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">集成中心</p>
                <h3>连接器与工具</h3>
                <p>管理 ATS、日历、邮件、向量库和对象存储等企业系统接入状态。</p>
              </div>
              <span className="module-badge">{connectorSummary(connectors)} 已配置</span>
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
                    {["ATS", "日历", "邮件", "向量库"].map((name) => (
                    <article className="connector-card muted" key={name}>
                      <Plug size={16} />
                      <div>
                        <strong>{name}</strong>
                        <p>输入口令或配置环境变量后同步。</p>
                      </div>
                      <span className="state-chip neutral">待配置</span>
                    </article>
                  ))}
                </>
              ) : null}
            </div>
            <section className="panel-card">
              <div className="section-title">
                <Wrench size={16} />
                工具注册表
              </div>
              <div className="compact-list">
                {tools.slice(0, 8).map((tool) => (
                  <div key={tool.name}>
                    <strong>{tool.name}</strong>
                    <span>{tool.compensatable ? "可补偿" : "无补偿"}</span>
                  </div>
                ))}
                {!tools.length ? <EmptyState icon={Wrench} title="工具目录不可见" body="输入访问口令后可读取工具 registry。" /> : null}
              </div>
            </section>
          </section>
        ) : null}

        {activeProductView === "audit" ? (
          <section className="module-view">
            <div className="module-head">
              <div>
                <p className="eyebrow">治理与审计</p>
                <h3>审计与合规</h3>
                <p>查看任务、工具调用、审批动作和审计链完整性。</p>
              </div>
              <span className={`module-badge ${auditValid ? "ok" : "warn"}`}>{auditLabel(auditValid)}</span>
            </div>
            <div className="audit-layout">
              <section className="panel-card">
                <div className="section-title">
                  <Database size={16} />
                  审计事件
                </div>
                <div className="timeline">
                  {auditEvents.slice(0, 10).map((event, index) => (
                    <div className="timeline-row" key={`${event.event_type}-${index}`}>
                      <span>{event.event_type || "event"}</span>
                      <p>{shortText(event.timestamp, "local")}</p>
                    </div>
                  ))}
                  {!auditEvents.length ? <EmptyState icon={Database} title="暂无审计事件" body="输入访问口令后可查看当前租户的审计事件。" /> : null}
                </div>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <ShieldCheck size={16} />
                  合规检查
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
                <p className="eyebrow">管理设置</p>
                <h3>设置与发布检查</h3>
                <p>集中确认 API、鉴权、模型、工具执行模式和仓库发布状态。</p>
              </div>
              <span className="module-badge">租户 {tenantName}</span>
            </div>
            <div className="settings-grid">
              <section className="panel-card">
                <div className="section-title">
                  <Settings size={16} />
                  运行配置
                </div>
                <dl className="fact-list">
                  <div>
                    <dt>API</dt>
                    <dd>{API_BASE}</dd>
                  </div>
                  <div>
                    <dt>身份模式</dt>
                    <dd>{identityMode}</dd>
                  </div>
                  <div>
                    <dt>模型</dt>
                    <dd>{health?.chat_model || "--"}</dd>
                  </div>
                  <div>
                    <dt>工具模式</dt>
                    <dd>{health?.tool_execution_mode || "--"}</dd>
                  </div>
                </dl>
              </section>
              <section className="panel-card">
                <div className="section-title">
                  <GitBranch size={16} />
                  发布前 Git 检查
                </div>
                <div className="release-checklist">
                  <p>当前仓库包含结构迁移：旧根目录文件已移除，新 `backend/`、`frontend/`、`infra/` 目录需确认后再统一 stage。</p>
                  <code>git status --short</code>
                  <code>git diff --stat</code>
                </div>
              </section>
              <section className="panel-card production-card">
                <div className="section-title">
                  <ShieldCheck size={16} />
                  实机联调门禁
                  <span className="inline-loading">
                    验证通过 {productionCheckSummary.verified} | 待验证 {productionCheckSummary.configured} | 失败 {productionCheckSummary.failed}
                  </span>
                </div>
                <div className="readiness-matrix">
                  {productionReadinessItems.map((item) => (
                    <article className={item.status} key={item.id}>
                      <span className={`state-chip ${item.status === "verified" ? "ok" : item.status === "failed" ? "danger" : "warn"}`}>
                        {item.status === "verified"
                          ? "实机通过"
                          : item.status === "configured"
                            ? "已配置"
                            : item.status === "failed"
                              ? "验证失败"
                              : "未配置"}
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
                  观测性摘要
                </div>
                <div className="ops-summary">
                  <div>
                    <strong>{operations ? `${Math.round(operations.task_success_rate * 100)}%` : "--"}</strong>
                    <span>任务成功率</span>
                  </div>
                  <div>
                    <strong>{failedToolCount}</strong>
                    <span>工具失败</span>
                  </div>
                  <div>
                    <strong>{readinessWarnings.length}</strong>
                    <span>上线告警</span>
                  </div>
                </div>
              </section>
            </div>
          </section>
        ) : null}
      </section>

      <aside className="evidence-panel">
        <div className="inspector-tabs" role="tablist" aria-label="运行侧栏">
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
                  优先处理
                </div>
                <div className="priority-list">
                  {pendingApprovals.length ? (
                    <button type="button" onClick={() => setActiveInspector("actions")}>
                      <span className="state-chip warn">待审批</span>
                      <p>{pendingApprovals.length} 个动作需要确认</p>
                    </button>
                  ) : null}
                  {failedToolCount ? (
                    <button type="button" onClick={() => setActiveInspector("actions")}>
                      <span className="state-chip danger">工具失败</span>
                      <p>{failedToolCount} 次执行失败，建议复核连接器或参数。</p>
                    </button>
                  ) : null}
                </div>
              </section>
            ) : null}

            <section className="panel-card priority-card">
              <div className="section-title">
                <ShieldCheck size={16} />
                运行状态
                {isRefreshingOps ? <span className="inline-loading">刷新中</span> : null}
              </div>
              <div className="metric-grid">
                <div>
                  <strong>{score ?? "--"}</strong>
                  <span>就绪分</span>
                </div>
                <div>
                  <strong>{operations?.task_count ?? tasks.length}</strong>
                  <span>任务数</span>
                </div>
                <div>
                  <strong>{connectorSummary(connectors)}</strong>
                  <span>连接器</span>
                </div>
              </div>
              <dl className="fact-list">
                <div>
                  <dt>工具模式</dt>
                  <dd>{health?.tool_execution_mode || "--"}</dd>
                </div>
                <div>
                  <dt>数据库</dt>
                  <dd>{health?.database_backend || "--"}</dd>
                </div>
                <div>
                  <dt>向量库</dt>
                  <dd>{health?.vector_backend || "--"}</dd>
                </div>
              </dl>
              <div className="ops-summary">
                <div>
                  <strong>{operations ? `${Math.round(operations.task_success_rate * 100)}%` : "--"}</strong>
                  <span>任务成功率</span>
                </div>
                <div>
                  <strong>{operations?.tool_execution_count ?? toolExecutions.length}</strong>
                  <span>工具执行</span>
                </div>
                <div>
                  <strong>{operations?.tool_status_counts?.FAILED ?? 0}</strong>
                  <span>工具失败</span>
                </div>
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <AlertTriangle size={16} />
                上线检查
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
                <EmptyState icon={ShieldCheck} tone="ok" title="上线检查通过" body="当前运行配置没有阻塞性的就绪告警。" />
              )}
            </section>
          </>
        ) : null}

        {activeInspector === "trace" ? (
          <>
            <section className="panel-card">
              <div className="section-title">
                <FileText size={16} />
                引用与上下文
              </div>
              <div className="evidence-note">
                {latestUserQuestion
                  ? `最近问题：${shortText(latestUserQuestion)}`
                  : "提交一次对话后，这里会展示最近问题和关联证据。"}
              </div>
              <div className="citation-list">
                {latestAssistantEvidence.slice(0, 4).map((item, index) => (
                  <div className="citation-row evidence-card" key={`${item.source}-${index}`}>
                    <div className="evidence-card-head">
                      <strong>{item.source}</strong>
                      <span>{inferPageLabel(item.source)}</span>
                    </div>
                    <p>{shortText(item.snippet, "暂无引用片段")}</p>
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
                  <EmptyState icon={FileText} title="等待证据" body="发送一次政策问答后，这里会展示来源、片段、页码和关键词命中。" />
                ) : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <GitBranch size={16} />
                任务回放
              </div>
              <div className="timeline">
                {tasks.slice(0, 5).map((task) => (
                  <button className="timeline-button" type="button" key={task.task_id} onClick={() => selectTask(task.task_id)} disabled={loadingTaskId === task.task_id}>
                    <span>{loadingTaskId === task.task_id ? "读取中" : statusLabel(task.status)}</span>
                    <p>{shortText(task.input_text)}</p>
                  </button>
                ))}
                {!tasks.length ? <EmptyState icon={GitBranch} title="暂无任务回放" body="发送一次 Agent 请求后会出现任务记录和事件时间线。" /> : null}
              </div>
              {selectedTask ? (
                <div className="event-list">
                  <div className="trace-summary">
                    <div>
                      <span>任务</span>
                      <strong>{statusLabel(selectedTask.status)}</strong>
                    </div>
                    <div>
                      <span>Intent</span>
                      <strong>{selectedTask.intent || "--"}</strong>
                    </div>
                    <div>
                      <span>事件</span>
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
                动作与审批
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
                            {pendingApprovalId === item.id ? "提交中" : "通过"}
                          </button>
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "reject")}>
                            <X size={13} />
                            拒绝
                          </button>
                        </div>
                      ) : null}
                      {item.action_type && item.status === "APPROVED" ? (
                        <div className="row-actions">
                          <button type="button" disabled={pendingApprovalId === item.id} onClick={() => handleApprovalAction(item.id, "execute")}>
                            <Play size={13} />
                            {pendingApprovalId === item.id ? "执行中" : "执行"}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
                {!approvals.length && !interviews.length ? (
                  <EmptyState icon={ClipboardList} title="暂无动作记录" body="Agent 生成面试安排、审批或补偿动作后，会在这里出现。" />
                ) : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Wrench size={16} />
                工具目录
              </div>
              <div className="compact-list">
                {tools.slice(0, 5).map((tool) => (
                  <div key={tool.name}>
                    <strong>{tool.name}</strong>
                    <span>{tool.compensatable ? "可补偿" : "无补偿"}</span>
                  </div>
                ))}
                {!tools.length ? <EmptyState icon={Wrench} title="工具目录不可见" body="输入访问口令后可读取工具 registry，或确认后端已启动。" /> : null}
              </div>
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Activity size={16} />
                最近工具执行
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
                        尝试 {execution.attempts} 次 | {shortText(execution.idempotency_key, "无幂等键")}
                      </p>
                    </div>
                  </button>
                ))}
                {!toolExecutions.length ? <EmptyState icon={Activity} title="暂无工具执行" body="触发一次候选人跟进动作后，会显示执行状态、耗时和返回结果。" /> : null}
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
                      <span>{selectedToolExecution.attempts} 次尝试</span>
                    </div>
                    <div>
                      <Hash size={13} />
                      <span>{shortText(selectedToolExecution.idempotency_key, "无幂等键")}</span>
                    </div>
                  </div>
                  <div className="json-preview">
                    <strong>{selectedToolExecution.error_json ? "错误详情" : "返回结果"}</strong>
                    <pre>{previewJson(parseJsonSafe(selectedToolExecution.error_json || selectedToolExecution.response_json))}</pre>
                  </div>
                </div>
              ) : null}
            </section>

            <section className="panel-card">
              <div className="section-title">
                <Plug size={16} />
                连接器
              </div>
              <div className="compact-list">
                {connectors.slice(0, 6).map((connector) => (
                  <div key={connector.name}>
                    <strong>{connector.name}</strong>
                    <span>{statusLabel(connector.status)}</span>
                  </div>
                ))}
                {!connectors.length ? <EmptyState icon={Plug} title="连接器未读取" body="需要访问权限后才能读取连接器目录；若已输入口令，请确认后端服务可用。" /> : null}
              </div>
            </section>
          </>
        ) : null}

        {activeInspector === "audit" ? (
          <section className="panel-card">
            <div className="section-title">
              <Database size={16} />
              审计链
            </div>
            <div className="timeline">
              {auditEvents.slice(0, 6).map((event, index) => (
                <div className="timeline-row" key={`${event.event_type}-${index}`}>
                  <span>{event.event_type || "event"}</span>
                  <p>{shortText(event.timestamp, "local")}</p>
                </div>
              ))}
              {!auditEvents.length ? <EmptyState icon={Database} title="审计事件未加载" body="输入访问口令后可查看审计事件；没有事件时表示当前租户暂无可展示记录。" /> : null}
            </div>
          </section>
        ) : null}
      </aside>
    </main>
  );
}
