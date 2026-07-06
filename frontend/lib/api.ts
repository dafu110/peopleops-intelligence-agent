export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  evidence?: RagEvidence[];
};

export type RagEvidence = {
  source: string;
  snippet: string;
};

export type ChatResponse = {
  reply: string;
  intent: string;
  thread_id: string;
  task_id: string;
  evidence: RagEvidence[];
};

export type HealthResponse = {
  status: string;
  app_name: string;
  tool_execution_mode: string;
  database_backend: string;
  vector_backend: string;
  access_password_required: boolean;
  trusted_sso_enabled: boolean;
  oidc_enabled: boolean;
  database_url_configured: boolean;
  vector_store_url_configured: boolean;
  object_storage_configured: boolean;
  model_configured: boolean;
  chat_model: string;
  embedding_model: string;
  rag_top_k: number;
  rag_thresholds: {
    min_pass_rate: number;
    min_keyword_coverage: number;
    min_citation_correctness: number;
  };
  enterprise_warnings: string[];
  identity_modes: {
    access_password: boolean;
    trusted_sso: boolean;
    oidc: boolean;
  };
};

export type ReadinessResponse = {
  ready: boolean;
  enterprise_warnings: string[];
  audit_integrity: {
    valid?: boolean;
    total_events?: number;
    error?: string;
  };
  scorecard?: {
    score: number;
    target: number;
    grade: string;
    summary: string;
  };
  configured_connectors?: ConnectorRecord[];
};

export type ActionRecord = {
  id: number;
  status: string;
  candidate_name?: string;
  interview_time?: string;
  action_type?: string;
  subject_ref?: string;
};

export type AuditEvent = {
  event_type?: string;
  timestamp?: string;
  actor?: string;
  payload?: Record<string, unknown>;
};

export type TaskEvent = {
  id: number;
  task_id: string;
  event_type: string;
  payload?: Record<string, unknown>;
  created_at: string;
};

export type TaskRun = {
  task_id: string;
  thread_id: string;
  status: string;
  intent?: string;
  input_text: string;
  created_at: string;
  updated_at: string;
  events?: TaskEvent[];
};

export type ToolRecord = {
  name: string;
  description: string;
  schema_version: string;
  mutating: boolean;
  compensatable: boolean;
};

export type ToolExecutionRecord = {
  id: number;
  tool_name: string;
  idempotency_key: string;
  status: string;
  attempts: number;
  started_at: string;
  completed_at?: string;
  response_json?: string;
  error_json?: string;
};

export type ConnectorRecord = {
  name: string;
  category: string;
  status: string;
  env_vars?: string[];
};

export type DocumentExtractResponse = {
  filename: string;
  chars: number;
  text: string;
};

export type OperationsSummary = {
  tenant_id: string;
  task_count: number;
  task_success_rate: number;
  task_status_counts: Record<string, number>;
  tool_execution_count: number;
  tool_status_counts: Record<string, number>;
  approval_status_counts: Record<string, number>;
  recent_failures: {
    tasks: Array<Record<string, unknown>>;
    tools: Array<Record<string, unknown>>;
  };
};

export type ProductionCheckStatus = "not_configured" | "configured" | "verified" | "failed";

export type ProductionCheckRecord = {
  id: string;
  label: string;
  status: ProductionCheckStatus;
  verification: string;
  detail: string;
  next_step: string;
  latency_ms?: number | null;
};

export type ProductionChecksResponse = {
  live: boolean;
  summary: Record<ProductionCheckStatus, number>;
  checks: ProductionCheckRecord[];
};

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

type RequestOptions = RequestInit & {
  accessPassword?: string;
};

function applyAuthHeaders(headers: Headers, accessPassword?: string) {
  if (accessPassword) {
    headers.set("X-Access-Password", accessPassword);
  }
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  applyAuthHeaders(headers, options.accessPassword);

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(detail || "Request failed");
  }
  return payload as T;
}

export function getHealth() {
  return requestJson<HealthResponse>("/health");
}

export function getReadiness() {
  return requestJson<ReadinessResponse>("/readiness");
}

export function getInterviews(accessPassword: string) {
  return requestJson<ActionRecord[]>("/interviews?limit=8", { accessPassword });
}

export function getApprovals(accessPassword: string) {
  return requestJson<ActionRecord[]>("/approvals?limit=8", { accessPassword });
}

export function getAuditEvents(accessPassword: string) {
  return requestJson<AuditEvent[]>("/audit/events?limit=8", { accessPassword });
}

export function getTasks(accessPassword: string) {
  return requestJson<TaskRun[]>("/tasks?limit=8", { accessPassword });
}

export function getTaskDetail(taskId: string, accessPassword: string) {
  return requestJson<TaskRun>(`/tasks/${taskId}`, { accessPassword });
}

export function getTools(accessPassword: string) {
  return requestJson<{ tools: ToolRecord[] }>("/tools", { accessPassword });
}

export function getToolExecutions(accessPassword: string) {
  return requestJson<ToolExecutionRecord[]>("/tool-executions?limit=8", { accessPassword });
}

export function getConnectors(accessPassword: string) {
  return requestJson<{ connectors: ConnectorRecord[] }>("/connectors", { accessPassword });
}

export function getOperationsSummary(accessPassword: string) {
  return requestJson<OperationsSummary>("/operations/summary", { accessPassword });
}

export function getProductionChecks(accessPassword: string, live = false) {
  return requestJson<ProductionChecksResponse>(`/production/checks?live=${live ? "true" : "false"}`, { accessPassword });
}

export function transitionApproval(
  approvalId: number,
  action: "approve" | "reject" | "execute",
  accessPassword: string,
) {
  return requestJson<ActionRecord>(`/approvals/${approvalId}/${action}`, {
    method: "POST",
    accessPassword,
  });
}

export function sendChat(input: {
  message: string;
  jdText: string;
  resumeText: string;
  history: ChatMessage[];
  threadId?: string;
  accessPassword: string;
}) {
  return requestJson<ChatResponse>("/chat", {
    method: "POST",
    accessPassword: input.accessPassword,
    body: JSON.stringify({
      message: input.message,
      jd_text: input.jdText,
      resume_text: input.resumeText,
      history: input.history,
      thread_id: input.threadId || undefined,
    }),
  });
}

export async function extractDocument(file: File, accessPassword: string) {
  const headers = new Headers();
  applyAuthHeaders(headers, accessPassword);
  const formData = new FormData();
  formData.set("file", file);

  const response = await fetch(`${API_BASE}/documents/extract`, {
    method: "POST",
    headers,
    body: formData,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : response.statusText;
    throw new Error(detail || "Document extraction failed");
  }
  return payload as DocumentExtractResponse;
}
