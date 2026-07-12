import { ChatMessage, ConnectorRecord, RagEvidence, TaskEvent } from "./api";

export type ProductView = "workspace" | "candidates" | "approvals" | "connectors" | "audit" | "settings";
export type InspectorView = "evidence" | "activity" | "approvals";

export const starterMessages: ChatMessage[] = [{
  role: "assistant",
  content: "我是 PeopleOps 智能助手。上传候选人材料和 JD，或直接询问制度、流程与候选人跟进行动。所有候选人分析仅提供可复核证据，不做录用或拒绝决定。",
}];

export function statusClass(status?: string) {
  const value = (status || "").toLowerCase();
  if (["success", "succeeded", "completed", "approved", "executed", "ok"].some((item) => value.includes(item))) return "ok";
  if (["fail", "error", "reject", "cancel"].some((item) => value.includes(item))) return "danger";
  if (["pending", "running", "draft", "review"].some((item) => value.includes(item))) return "warn";
  return "neutral";
}

export function statusLabel(status?: string) {
  const labels: Record<string, string> = { DRAFT: "草稿", PENDING: "待审批", APPROVED: "已通过", REJECTED: "已拒绝", EXECUTED: "已执行", FAILED: "失败", SUCCEEDED: "成功", RUNNING: "进行中", CONFIGURED: "已配置" };
  return labels[(status || "").toUpperCase()] || status || "--";
}

export function shortText(value?: string, fallback = "暂无") { return !value ? fallback : value.length > 72 ? `${value.slice(0, 72)}...` : value; }
export function formatDateTime(value?: string) { return value ? new Date(value).toLocaleString() : "--"; }
export function connectorSummary(items: ConnectorRecord[]) { return `${items.filter((item) => item.status === "configured").length}/${items.length}`; }
export function evidenceReliability(item: RagEvidence, question: string) { return item.source && item.snippet.includes(question.slice(0, 2)) ? "相关" : item.source ? "可追溯" : "待复核"; }
export function eventSummary(event: TaskEvent) { return Object.entries(event.payload || {}).slice(0, 2).map(([key, value]) => `${key}: ${String(value).slice(0, 36)}`).join(" · ") || event.event_type; }
export function getInitialProductView(): ProductView { return "workspace"; }
export function getInitialInspectorView(): InspectorView { return "evidence"; }
