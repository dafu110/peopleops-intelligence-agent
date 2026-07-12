"use client";

import {
  Activity,
  ArrowUp,
  Bot,
  Check,
  ChevronRight,
  ClipboardCheck,
  FileClock,
  FileText,
  FolderKanban,
  History,
  Link2,
  Menu,
  MoreHorizontal,
  Plug,
  RefreshCw,
  Settings,
  ShieldCheck,
  UserRound,
  X,
} from "lucide-react";
import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  API_BASE,
  ActionRecord,
  AuditEvent,
  ChatMessage,
  ConnectorRecord,
  HealthResponse,
  OperationsSummary,
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
  getReadiness,
  getTaskDetail,
  getTasks,
  getToolExecutions,
  getTools,
  recordOperatorEvent,
  sendChat,
  transitionApproval,
} from "../lib/api";
import { ContextPanel } from "../components/context-panel";
import { createChatSubmission } from "../lib/chat-workflow.mjs";
import { connectorSummary, eventSummary, formatDateTime, getInitialInspectorView, getInitialProductView, shortText, starterMessages, statusClass, statusLabel } from "../lib/ui-helpers";
import type { InspectorView, ProductView } from "../lib/ui-helpers";

const quickPrompts = ["这份简历和 JD 有哪些可复核证据？", "差旅住宿报销标准是什么？", "生成候选人跟进草稿（需审批）"];

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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [operations, setOperations] = useState<OperationsSummary | null>(null);
  const [approvals, setApprovals] = useState<ActionRecord[]>([]);
  const [interviews, setInterviews] = useState<ActionRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [tasks, setTasks] = useState<TaskRun[]>([]);
  const [tools, setTools] = useState<ToolRecord[]>([]);
  const [toolExecutions, setToolExecutions] = useState<ToolExecutionRecord[]>([]);
  const [connectors, setConnectors] = useState<ConnectorRecord[]>([]);
  const [selectedTask, setSelectedTask] = useState<TaskRun | null>(null);
  const [pendingApprovalId, setPendingApprovalId] = useState<number | null>(null);
  const [activeProductView, setActiveProductView] = useState<ProductView>(getInitialProductView);
  const [activeInspector, setActiveInspector] = useState<InspectorView>(getInitialInspectorView);
  const [contextOpen, setContextOpen] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const [onboardingDismissed, setOnboardingDismissed] = useState(false);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const contextDrawerRef = useRef<HTMLDivElement>(null);
  const contextTriggerRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const evidence = useMemo(() => [...messages].reverse().find((message) => message.role === "assistant" && message.evidence?.length)?.evidence || [], [messages]);
  const pendingApprovals = approvals.filter((item) => item.status === "PENDING");
  const auditValid = readiness?.audit_integrity?.valid;
  const ready = readiness?.ready;
  const taskCount = operations?.task_count ?? tasks.length;
  const inspectorHasDetail = Boolean(evidence.length || selectedTask || pendingApprovals.length);
  const configuredConnectorCount = connectors.filter((item) => item.status === "configured").length;
  const isDemoEnvironment = health?.tool_execution_mode === "local" || (health !== null && configuredConnectorCount === 0);
  const candidateContextReady = Boolean(resumeText.trim() && jdText.trim());
  const isDevelopment = process.env.NODE_ENV === "development";

  function openContext() {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setContextOpen(true);
  }

  function closeContext() {
    setContextOpen(false);
  }

  function selectProductView(view: ProductView) {
    if (view === "candidates") {
      openContext();
      return;
    }
    setActiveProductView(view);
    setMobileMoreOpen(false);
  }

  function startCandidateReview() {
    if (!candidateContextReady) {
      openContext();
      return;
    }
    setOnboardingDismissed(true);
    void submitMessage("这份简历和 JD 有哪些可复核证据？");
  }

  function startPolicyQuery() {
    setOnboardingDismissed(true);
    setPrompt("请说明差旅住宿报销的适用标准和引用依据。");
    window.requestAnimationFrame(() => {
      promptRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
      promptRef.current?.focus();
    });
  }

  async function refreshOperationalData(password = accessPassword) {
    setIsRefreshing(true);
    try {
      const [healthData, readinessData] = await Promise.all([getHealth(), getReadiness()]);
      setHealth(healthData);
      setReadiness(readinessData);
      const [approvalData, interviewData, auditData, taskData, toolData, executionData, connectorData, operationsData] = await Promise.all([
        getApprovals(password), getInterviews(password), getAuditEvents(password), getTasks(password), getTools(password), getToolExecutions(password), getConnectors(password), getOperationsSummary(password),
      ]);
      setApprovals(approvalData); setInterviews(interviewData); setAuditEvents(auditData); setTasks(taskData);
      setTools(toolData.tools); setToolExecutions(executionData); setConnectors(connectorData.connectors); setOperations(operationsData);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法连接后端服务");
    } finally { setIsRefreshing(false); }
  }

  useEffect(() => {
    refreshOperationalData(accessPassword);
    const timer = window.setInterval(() => refreshOperationalData(accessPassword), 45000);
    return () => window.clearInterval(timer);
  }, [accessPassword]);

  useEffect(() => {
    if (!contextOpen) {
      const previousFocus = previousFocusRef.current;
      if (!previousFocus) return;
      if (previousFocus.isConnected) previousFocus.focus();
      else contextTriggerRef.current?.focus();
      previousFocusRef.current = null;
      return;
    }

    const drawer = contextDrawerRef.current;
    if (!drawer) return;
    const activeDrawer: HTMLDivElement = drawer;
    const focusableSelector = "button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";
    const closeButton = activeDrawer.querySelector<HTMLElement>("[data-context-close]");
    window.requestAnimationFrame(() => closeButton?.focus());

    function handleContextKeydown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeContext();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = Array.from(activeDrawer.querySelectorAll<HTMLElement>(focusableSelector));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleContextKeydown);
    return () => document.removeEventListener("keydown", handleContextKeydown);
  }, [contextOpen]);

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    setResumeFiles(files.map((file) => file.name));
    if (!files.length) return;
    setIsExtracting(true); setError("");
    try {
      const parsed = await Promise.all(files.map((file) => extractDocument(file, accessPassword)));
      setResumeText(parsed.map((item) => `《${item.filename}》\n${item.text}`).join("\n\n"));
    } catch (err) { setError(err instanceof Error ? err.message : "文档解析失败"); }
    finally { setIsExtracting(false); }
  }

  async function submitMessage(message: string) {
    const submission = createChatSubmission({ prompt: message, messages, isSending });
    if (!submission) return;
    setMessages(submission.messages); setPrompt(""); setIsSending(true); setError("");
    try {
      const response = await sendChat({ message: submission.message, jdText, resumeText, history: submission.messages, threadId, accessPassword });
      setThreadId(response.thread_id); setLastTaskId(response.task_id);
      setMessages((current) => [...current, { role: "assistant", content: response.reply || "系统没有返回有效回复。", evidence: response.evidence || [] }]);
      const task = await getTaskDetail(response.task_id, accessPassword);
      setSelectedTask(task);
      if (response.evidence?.length) await recordOperatorEvent(response.task_id, "citation.shown", accessPassword).catch(() => undefined);
      await refreshOperationalData(accessPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent 请求失败");
      setMessages((current) => [...current, { role: "assistant", content: "请求没有完成。请检查 API、访问口令或模型配置。" }]);
    } finally { setIsSending(false); }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage(prompt);
  }

  async function handleApprovalAction(id: number, action: "submit" | "approve" | "reject" | "execute" | "retry") {
    setPendingApprovalId(id); setError("");
    try { await transitionApproval(id, action, accessPassword); await refreshOperationalData(accessPassword); }
    catch (err) { setError(err instanceof Error ? err.message : "审批更新失败"); }
    finally { setPendingApprovalId(null); }
  }

  async function selectTask(taskId: string) {
    try { setSelectedTask(await getTaskDetail(taskId, accessPassword)); setActiveInspector("activity"); }
    catch (err) { setError(err instanceof Error ? err.message : "无法读取任务详情"); }
  }

  const navigation = [
    { id: "workspace" as const, label: "对话", icon: Bot }, { id: "candidates" as const, label: "材料", icon: FolderKanban },
    { id: "approvals" as const, label: "审批", icon: ClipboardCheck }, { id: "audit" as const, label: "记录", icon: History },
    { id: "connectors" as const, label: "连接", icon: Plug }, { id: "settings" as const, label: "设置", icon: Settings },
  ];
  const primaryNavigation = navigation;
  const managementNavigation = navigation.filter((item) => item.id !== "workspace" && item.id !== "candidates");

  return (
    <main className={`codex-shell ${contextOpen ? "context-open" : ""}`}>
      <aside className="rail" aria-label="主导航">
        <button className="rail-logo" type="button" title="PeopleOps">P</button>
        <nav>{primaryNavigation.map((item) => { const Icon = item.icon; return <button aria-label={item.label} className={activeProductView === item.id || (item.id === "candidates" && contextOpen) ? "active" : ""} data-tooltip={item.label} key={item.id} onClick={() => selectProductView(item.id)} title={item.label} type="button"><Icon size={18} /><span>{item.label}</span></button>; })}<button aria-expanded={mobileMoreOpen} aria-label="管理功能" className={`mobile-more-trigger ${activeProductView !== "workspace" ? "active" : ""}`} data-tooltip="管理功能" onClick={() => setMobileMoreOpen((value) => !value)} title="管理功能" type="button"><MoreHorizontal size={19} /></button></nav>
        <button className="rail-user" type="button" title="本地管理员"><UserRound size={18} /></button>
      </aside>

      <section className="conversation-pane">
        <header className="topbar">
          <div><span className="product-name">PeopleOps</span><ChevronRight size={14} /><strong>{activeProductView === "workspace" ? "新对话" : navigation.find((item) => item.id === activeProductView)?.label}</strong></div>
          <div className="topbar-actions">
            <span className={health?.status === "ok" ? "live-dot" : "live-dot offline"}>{health?.status === "ok" ? "已连接" : "检查中"}</span>
            <button aria-label="刷新数据" onClick={() => refreshOperationalData()} title="刷新数据" type="button"><RefreshCw className={isRefreshing ? "spin" : ""} size={16} /></button>
            <button aria-label="打开任务材料" onClick={openContext} ref={contextTriggerRef} title="打开任务材料" type="button"><Menu size={17} /></button>
          </div>
        </header>

        {error ? <div className="error-banner"><X size={15} /> {error}</div> : null}

        {activeProductView === "workspace" ? <section className="chat-workspace">
          <div className="chat-title"><Bot size={19} /><div><h1>PeopleOps 智能助手</h1><p>基于证据协助 HRBP 完成制度问答、候选人复核和受控动作。</p></div></div>
          {!onboardingDismissed ? <section className="first-task-card" aria-labelledby="first-task-title">
            <div><span className="eyebrow">从这里开始</span><h2 id="first-task-title">选择一项任务</h2><p>日常工作只需从候选人匹配或制度咨询开始；材料、审批和记录会在任务过程中出现。</p></div>
            <div className="task-choice-grid"><button className="task-choice" disabled={isSending} onClick={startCandidateReview} type="button"><FileText size={20} /><span><strong>候选人匹配</strong><small>{candidateContextReady ? "材料已就绪，生成可复核匹配证据" : "添加材料和岗位说明后生成匹配证据"}</small></span><ChevronRight size={17} /></button><button className="task-choice" onClick={startPolicyQuery} type="button"><Bot size={20} /><span><strong>咨询制度与流程</strong><small>直接询问报销、考勤、福利与内部流程</small></span><ChevronRight size={17} /></button></div>
            <small className="onboarding-note">候选人结果只作为复核材料；需要审批的外部操作会另行确认。</small>
          </section> : null}
          <div className="conversation" aria-live="polite">
            {messages.map((message, index) => <article className={`chat-message ${message.role}`} key={`${message.role}-${index}`}><div className="chat-avatar">{message.role === "assistant" ? <Bot size={16} /> : <UserRound size={16} />}</div><div className="message-copy">{message.content}</div></article>)}
            {isSending ? <article className="chat-message assistant"><div className="chat-avatar"><Bot size={16} /></div><div className="message-copy thinking"><span /><span /><span /> 正在处理</div></article> : null}
          </div>
          {selectedTask?.intent === "resume" ? <div className="feedback-row"><span>这份证据包是否有帮助？</span><button onClick={() => lastTaskId && recordOperatorEvent(lastTaskId, "candidate.adopted", accessPassword)} type="button"><Check size={14} /> 采纳</button><button onClick={() => lastTaskId && recordOperatorEvent(lastTaskId, "candidate.rewritten", accessPassword)} type="button">已改写</button></div> : null}
          <form className="prompt-box" onSubmit={handleSubmit}>
            <textarea onChange={(event) => setPrompt(event.target.value)} placeholder="询问政策、候选人证据或准备一个受控动作..." ref={promptRef} rows={3} value={prompt} />
            <div className="prompt-footer"><div className="suggestions">{quickPrompts.map((item) => <button className={item.includes("草稿") ? "consequential" : ""} key={item} onClick={() => setPrompt(item)} type="button">{item}</button>)}</div><button aria-label="发送" className="send-button" disabled={isSending || !prompt.trim()} type="submit"><ArrowUp size={18} /></button></div>
          </form>
          <p className="action-note">候选人跟进行动仅会生成草稿；提交、审批和执行均需 HRBP 明确确认。</p>
          <p className="disclaimer">候选人分析仅作为 HRBP 复核材料；系统不会作出录用、拒绝或排序决定。</p>
        </section> : null}

        {activeProductView === "candidates" ? <section className="compact-view"><ViewHeader icon={FolderKanban} title="任务材料" note="这些材料只在当前对话中用于生成可复核证据。" /><div className="material-status"><FileText size={18} /><div><strong>{resumeFiles.length ? resumeFiles.join("、") : resumeText ? "已粘贴候选人材料" : "尚未添加候选人材料"}</strong><span>{jdText ? "岗位说明已就绪" : "尚未添加岗位说明"}</span></div><button onClick={openContext} type="button">编辑材料</button></div></section> : null}
        {activeProductView === "approvals" ? <section className="compact-view"><ViewHeader icon={ClipboardCheck} title="审批" note="外部动作必须由 HRBP 显式确认后才可执行。" />{[...approvals, ...interviews].slice(0, 12).map((item) => <ApprovalRow item={item} key={`${item.id}-${item.status}`} pending={pendingApprovalId === item.id} onAction={handleApprovalAction} />)}{!approvals.length && !interviews.length ? <Empty icon={ClipboardCheck} text="当前没有待处理审批。" /> : null}</section> : null}
        {activeProductView === "audit" ? <section className="compact-view"><ViewHeader icon={History} title="任务记录" note={auditValid ? "审计链校验通过" : "审计链待检查"} />{tasks.map((task) => <button className="list-row" key={task.task_id} onClick={() => selectTask(task.task_id)} type="button"><span className={`status ${statusClass(task.status)}`}>{statusLabel(task.status)}</span><strong>{shortText(task.input_text)}</strong><time>{formatDateTime(task.updated_at)}</time></button>)}{!tasks.length ? <Empty icon={History} text="尚无任务记录。" /> : null}</section> : null}
        {activeProductView === "connectors" ? <section className="compact-view"><ViewHeader icon={Plug} title="连接器" note={`${connectorSummary(connectors)} 已配置`} /><div className="connector-list">{connectors.map((item) => <div className="list-row" key={item.name}><Plug size={16} /><strong>{item.name}</strong><span>{item.category}</span><span className={`status ${statusClass(item.status)}`}>{statusLabel(item.status)}</span></div>)}</div></section> : null}
        {activeProductView === "settings" ? <section className="compact-view"><ViewHeader icon={Settings} title="系统设置" note="仅供管理员查看运行配置与连接详情。" /><dl className="settings-list">{isDevelopment ? <div><dt>API 地址</dt><dd>{API_BASE}</dd></div> : null}<div><dt>模型</dt><dd>{health?.chat_model || "--"}</dd></div><div><dt>工具模式</dt><dd>{health?.tool_execution_mode || "--"}</dd></div><div><dt>审计</dt><dd>{auditValid ? "哈希链有效" : "待检查"}</dd></div></dl></section> : null}
      </section>

      <aside className="inspector">
        {inspectorHasDetail ? <>
        <div className="inspector-head"><div><span>检查器</span><strong>{activeInspector === "evidence" ? "证据" : activeInspector === "activity" ? "活动" : "审批"}</strong></div></div>
        <div className="inspector-tabs"><button className={activeInspector === "evidence" ? "active" : ""} onClick={() => setActiveInspector("evidence")} type="button"><Link2 size={14} /> 证据</button><button className={activeInspector === "activity" ? "active" : ""} onClick={() => setActiveInspector("activity")} type="button"><Activity size={14} /> 活动</button><button className={activeInspector === "approvals" ? "active" : ""} onClick={() => setActiveInspector("approvals")} type="button"><FileClock size={14} /> 审批</button></div>
        {activeInspector === "evidence" ? <InspectorEvidence evidence={evidence} question={messages.filter((item) => item.role === "user").at(-1)?.content || ""} lastTaskId={lastTaskId} password={accessPassword} /> : null}
        {activeInspector === "activity" ? <InspectorActivity task={selectedTask} auditEvents={auditEvents} /> : null}
        {activeInspector === "approvals" ? <section className="inspector-list">{approvals.slice(0, 8).map((item) => <ApprovalRow item={item} key={item.id} pending={pendingApprovalId === item.id} onAction={handleApprovalAction} compact />)}{!approvals.length ? <Empty icon={FileClock} text="没有待审动作。" /> : null}</section> : null}
        </> : null}
        <div className="runtime-card"><div><ShieldCheck size={15} /><span>{isDemoEnvironment ? "演示环境" : "运行状态"}</span></div><p><span className="metric">{isDemoEnvironment ? "本地演示" : ready ? "核心服务就绪" : "待检查"}</span><span>{isDemoEnvironment ? "未连接外部 HR 系统" : `${configuredConnectorCount}/${connectors.length} 个连接器已配置`}</span></p><details className="runtime-details"><summary>查看运行详情</summary><p>{taskCount} 个任务 · {toolExecutions.length} 次工具执行 · 审计{auditValid ? "链有效" : "待检查"}</p></details></div>
      </aside>

      {mobileMoreOpen ? <div className="mobile-more-menu" role="menu">{managementNavigation.map((item) => { const Icon = item.icon; return <button key={item.id} onClick={() => selectProductView(item.id)} role="menuitem" type="button"><Icon size={16} /> {item.label}</button>; })}</div> : null}

      <div aria-hidden={!contextOpen} aria-label="任务材料" aria-modal="true" className="context-drawer" ref={contextDrawerRef} role="dialog"><ContextPanel accessPassword={accessPassword} handleFiles={handleFiles} isExtracting={isExtracting} jdText={jdText} onClose={closeContext} refreshOperationalData={refreshOperationalData} resumeFiles={resumeFiles} resumeText={resumeText} setAccessPassword={setAccessPassword} setJdText={setJdText} setResumeText={setResumeText} /></div>
    </main>
  );
}

function ViewHeader({ icon: Icon, title, note }: { icon: typeof Activity; title: string; note: string }) { return <header className="view-header"><Icon size={19} /><div><h1>{title}</h1><p>{note}</p></div></header>; }
function Empty({ icon: Icon, text }: { icon: typeof Activity; text: string }) { return <div className="empty"><Icon size={18} /><p>{text}</p></div>; }
function ApprovalRow({ item, pending, onAction, compact = false }: { item: ActionRecord; pending: boolean; onAction: (id: number, action: "submit" | "approve" | "reject" | "execute" | "retry") => void; compact?: boolean }) {
  const action = item.action_type;
  return <article className={`approval-row ${compact ? "compact" : ""}`}><div><span className={`status ${statusClass(item.status)}`}>{statusLabel(item.status)}</span><strong>{shortText(item.candidate_name || action || item.subject_ref, "候选人动作")}</strong><p>{item.interview_time ? formatDateTime(item.interview_time) : item.status === "DRAFT" ? "草稿尚未提交，不会触发外部动作" : "等待 HRBP 审核"}</p></div>{action && item.status === "DRAFT" ? <button disabled={pending} onClick={() => onAction(item.id, "submit")} type="button">提交审批</button> : null}{action && item.status === "PENDING" ? <div className="approval-actions"><button disabled={pending} onClick={() => onAction(item.id, "approve")} type="button">批准</button><button className="quiet" disabled={pending} onClick={() => onAction(item.id, "reject")} type="button">拒绝</button></div> : null}{action && item.status === "APPROVED" ? <button disabled={pending} onClick={() => onAction(item.id, "execute")} type="button">执行已批准动作</button> : null}{action && item.status === "FAILED" ? <button disabled={pending} onClick={() => onAction(item.id, "retry")} type="button">重试</button> : null}</article>;
}
function InspectorEvidence({ evidence, question, lastTaskId, password }: { evidence: ChatMessage["evidence"]; question: string; lastTaskId: string; password: string }) { return <section className="inspector-list">{evidence?.map((item, index) => <button className="evidence-row" key={`${item.source}-${index}`} onClick={() => lastTaskId && recordOperatorEvent(lastTaskId, "citation.opened", password).catch(() => undefined)} type="button"><span>来源 {index + 1}</span><strong>{item.source || "内部材料"}</strong><p>{item.snippet}</p><small>{question ? "已关联当前问题" : "可复核"}</small></button>)}{!evidence?.length ? <Empty icon={Link2} text="对话生成引用后，会在这里显示来源与证据片段。" /> : null}</section>; }
function InspectorActivity({ task, auditEvents }: { task: TaskRun | null; auditEvents: AuditEvent[] }) { const events = task?.events || []; return <section className="inspector-list">{events.map((item) => <div className="activity-row" key={item.id}><strong>{item.event_type}</strong><p>{eventSummary(item)}</p><time>{formatDateTime(item.created_at)}</time></div>)}{!events.length && auditEvents.slice(0, 6).map((item, index) => <div className="activity-row" key={index}><strong>{item.event_type || "audit"}</strong><p>{shortText(item.actor, "local")}</p><time>{formatDateTime(item.timestamp)}</time></div>)}{!events.length && !auditEvents.length ? <Empty icon={Activity} text="选择一条任务后，这里会显示完整执行轨迹。" /> : null}</section>; }
