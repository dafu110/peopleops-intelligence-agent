import { ChatMessage, ConnectorRecord, RagEvidence, TaskEvent } from "./api";

export type ProductView = "workspace" | "candidates" | "approvals" | "connectors" | "audit" | "settings";
export type InspectorView = "overview" | "trace" | "actions" | "audit";

export const starterMessages: ChatMessage[] = [
  {
    role: "assistant",
    content:
      "你好，我是 PeopleOps 智能助手。你可以上传简历、粘贴 JD，或直接询问制度、报销、考勤、福利和候选人跟进动作。",
  },
];

export function statusTone(ok?: boolean) {
  return ok ? "status-pill ok" : "status-pill warn";
}

export function readinessLabel(ok?: boolean) {
  return ok ? "生产就绪" : "待复核";
}

export function auditLabel(ok?: boolean) {
  return ok ? "审计有效" : "待检查";
}

export function shortText(value: string | undefined, fallback = "暂无") {
  if (!value) return fallback;
  return value.length > 72 ? `${value.slice(0, 72)}...` : value;
}

export function connectorSummary(connectors: ConnectorRecord[]) {
  const configured = connectors.filter((item) => item.status === "configured").length;
  return `${configured}/${connectors.length}`;
}

export function parseJsonSafe(value?: string) {
  if (!value) return null;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
}

export function previewJson(value: unknown, fallback = "暂无详情") {
  if (value === null || value === undefined || value === "") return fallback;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return text.length > 520 ? `${text.slice(0, 520)}...` : text;
}

export function formatDateTime(value?: string) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatDuration(start?: string, end?: string) {
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

export function keywordHits(question: string, snippet: string) {
  const terms = searchTerms(question);
  const lowerSnippet = snippet.toLowerCase();
  return terms.filter((term) => lowerSnippet.includes(term)).slice(0, 5);
}

export function inferPageLabel(source: string) {
  const match = source.match(/(?:page|p)[-_ ]?(\d+)/i) || source.match(/#page=(\d+)/i);
  return match ? `p.${match[1]}` : "chunk";
}

export function evidenceReliability(item: RagEvidence, question: string) {
  const hits = keywordHits(question, item.snippet);
  if (!item.snippet) return "无片段";
  if (hits.length >= 2) return "关键词命中";
  if (item.source) return "可追溯";
  return "待复核";
}

export function statusClass(status?: string) {
  const normalized = (status || "").toLowerCase();
  if (["success", "succeeded", "completed", "approved", "ready", "ok"].some((term) => normalized.includes(term))) return "ok";
  if (["fail", "error", "reject", "cancel"].some((term) => normalized.includes(term))) return "danger";
  if (["pending", "running", "review", "check"].some((term) => normalized.includes(term))) return "warn";
  return "neutral";
}

export function statusLabel(status?: string) {
  const normalized = (status || "").toUpperCase();
  const labels: Record<string, string> = {
    APPROVED: "已通过",
    CANCELLED: "已取消",
    COMPLETED: "已完成",
    CONFIGURED: "已配置",
    ERROR: "错误",
    FAILED: "失败",
    PENDING: "待审批",
    READY: "就绪",
    REJECTED: "已拒绝",
    RUNNING: "运行中",
    SUCCESS: "成功",
    SUCCEEDED: "成功",
  };
  return labels[normalized] || status || "--";
}

export function eventSummary(event: TaskEvent) {
  const payload = event.payload || {};
  const keys = Object.keys(payload);
  if (!keys.length) return "无 payload";
  const preferred = ["intent", "tool_name", "status", "evidence_count", "reply_chars", "error"];
  const picked = preferred.filter((key) => key in payload);
  const displayKeys = picked.length ? picked : keys.slice(0, 3);
  return displayKeys.map((key) => `${key}: ${String(payload[key]).slice(0, 48)}`).join(" · ");
}

export function getInitialProductView(): ProductView {
  if (typeof window === "undefined") return "workspace";
  const view = new URLSearchParams(window.location.search).get("view");
  return ["workspace", "candidates", "approvals", "connectors", "audit", "settings"].includes(view || "")
    ? (view as ProductView)
    : "workspace";
}

export function getInitialInspectorView(): InspectorView {
  if (typeof window === "undefined") return "overview";
  const inspector = new URLSearchParams(window.location.search).get("inspector");
  return ["overview", "trace", "actions", "audit"].includes(inspector || "")
    ? (inspector as InspectorView)
    : "overview";
}
