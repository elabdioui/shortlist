// SPDX-License-Identifier: AGPL-3.0-or-later

import type {
  APIKeyCreate,
  APIKeyResponse,
  APIKeyTestResult,
  APIKeyUpdate,
  AnalysisRunResponse,
  AnonymizedPreviewResponse,
  AuthSessionResponse,
  AuthSetupRequest,
  CandidateDetail,
  CandidateUploadResponse,
  CriteriaGenerateResponse,
  CriteriaSetResponse,
  CriteriaSetUpdate,
  DecisionCreate,
  DecisionResponse,
  EstimateResponse,
  HumanDecision,
  JobCreate,
  JobResponse,
  JobUpdate,
  LoginRequest,
  ModelProfileCreate,
  ModelProfileResponse,
  PaginatedAuditLogs,
  PaginatedCandidates,
  PrivacySettingsResponse,
  PrivacySettingsUpdate,
  ProviderCreate,
  ProviderResponse,
  PurgeResultResponse,
  Recommendation,
  RunStartRequest,
  SetupStatusResponse,
  UsageLogResponse,
  UserCreate,
  UserResponse,
  UserUpdate,
} from "@/lib/api/types";

const CSRF_COOKIE_NAME = "shortlist_csrf";
const CSRF_HEADER_NAME = "X-CSRF-Token";
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let memoryCsrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  memoryCsrfToken = token;
}

export function getCsrfToken(): string | null {
  if (typeof document !== "undefined") {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const raw of cookies) {
      const [name, ...rest] = raw.trim().split("=");
      if (name === CSRF_COOKIE_NAME) {
        return decodeURIComponent(rest.join("="));
      }
    }
  }
  return memoryCsrfToken;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  data: unknown;

  constructor(status: number, detail: string, data?: unknown) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.data = data;
  }
}

interface FetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  let requestBody: BodyInit | undefined;
  if (options.body instanceof FormData) {
    requestBody = options.body;
  } else if (options.body !== undefined) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    requestBody = JSON.stringify(options.body);
  }

  if (MUTATING_METHODS.has(method)) {
    const csrf = getCsrfToken();
    if (csrf && !headers.has(CSRF_HEADER_NAME)) {
      headers.set(CSRF_HEADER_NAME, csrf);
    }
  }

  const response = await fetch(path, {
    ...options,
    method,
    headers,
    body: requestBody,
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json().catch(() => null) : await response.text();

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String((payload as { detail: unknown }).detail)
        : `HTTP ${response.status}`;
    throw new ApiError(response.status, detail, payload);
  }

  return payload as T;
}

export const authApi = {
  status: () => apiFetch<SetupStatusResponse>("/api/auth/status"),
  me: async (): Promise<UserResponse> => {
    const res = await apiFetch<AuthSessionResponse>("/api/auth/me");
    setCsrfToken(res.csrf_token);
    return res.user;
  },
  setup: async (payload: AuthSetupRequest) => {
    const res = await apiFetch<AuthSessionResponse>("/api/auth/setup", {
      method: "POST",
      body: payload,
    });
    setCsrfToken(res.csrf_token);
    return res;
  },
  login: async (payload: LoginRequest) => {
    const res = await apiFetch<AuthSessionResponse>("/api/auth/login", {
      method: "POST",
      body: payload,
    });
    setCsrfToken(res.csrf_token);
    return res;
  },
  logout: async () => {
    await apiFetch<void>("/api/auth/logout", { method: "POST" });
    setCsrfToken(null);
  },
};

export const jobsApi = {
  list: () => apiFetch<JobResponse[]>("/api/jobs"),
  get: (jobId: string) => apiFetch<JobResponse>(`/api/jobs/${jobId}`),
  create: (payload: JobCreate) =>
    apiFetch<JobResponse>("/api/jobs", { method: "POST", body: payload }),
  update: (jobId: string, payload: JobUpdate) =>
    apiFetch<JobResponse>(`/api/jobs/${jobId}`, { method: "PATCH", body: payload }),
  delete: (jobId: string) => apiFetch<void>(`/api/jobs/${jobId}`, { method: "DELETE" }),
  getCriteria: (jobId: string) => apiFetch<CriteriaSetResponse>(`/api/jobs/${jobId}/criteria`),
  generateCriteria: (jobId: string) =>
    apiFetch<CriteriaGenerateResponse>(`/api/jobs/${jobId}/criteria/generate`, {
      method: "POST",
    }),
  saveCriteria: (jobId: string, payload: CriteriaSetUpdate) =>
    apiFetch<CriteriaSetResponse>(`/api/jobs/${jobId}/criteria`, {
      method: "PUT",
      body: payload,
    }),
  uploadCandidates: (jobId: string, files: File[]) => {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file);
    }
    return apiFetch<CandidateUploadResponse>(`/api/jobs/${jobId}/candidates`, {
      method: "POST",
      body: formData,
    });
  },
  getEstimate: (jobId: string) => apiFetch<EstimateResponse>(`/api/jobs/${jobId}/estimate`),
  startRun: (jobId: string, payload: RunStartRequest = { resume_failed: false }) =>
    apiFetch<AnalysisRunResponse>(`/api/jobs/${jobId}/runs`, {
      method: "POST",
      body: payload,
    }),
  getRanking: (
    jobId: string,
    params?: {
      recommendation?: Recommendation | "";
      decision?: HumanDecision | "";
      search?: string;
      limit?: number;
      offset?: number;
    }
  ) => {
    const sp = new URLSearchParams();
    if (params?.recommendation) sp.set("recommendation", params.recommendation);
    if (params?.decision) sp.set("decision", params.decision);
    if (params?.search) sp.set("search", params.search);
    if (params?.limit != null) sp.set("limit", String(params.limit));
    if (params?.offset != null) sp.set("offset", String(params.offset));
    const qs = sp.toString();
    return apiFetch<PaginatedCandidates>(`/api/jobs/${jobId}/ranking${qs ? `?${qs}` : ""}`);
  },
  exportUrl: (jobId: string, format: "xlsx" | "csv") =>
    `/api/jobs/${jobId}/export?format=${format}`,
};

export const runsApi = {
  get: (runId: string) => apiFetch<AnalysisRunResponse>(`/api/runs/${runId}`),
  eventsUrl: (runId: string) => `/api/runs/${runId}/events`,
};

export const candidatesApi = {
  get: (candidateId: string) => apiFetch<CandidateDetail>(`/api/candidates/${candidateId}`),
  getAnonymizedPreview: (candidateId: string) =>
    apiFetch<AnonymizedPreviewResponse>(`/api/candidates/${candidateId}/anonymized-preview`),
  saveDecision: (candidateId: string, payload: DecisionCreate) =>
    apiFetch<DecisionResponse>(`/api/candidates/${candidateId}/decision`, {
      method: "POST",
      body: payload,
    }),
  delete: (candidateId: string) =>
    apiFetch<void>(`/api/candidates/${candidateId}`, { method: "DELETE" }),
  fileUrl: (candidateId: string) => `/api/candidates/${candidateId}/file`,
};

export const providersApi = {
  listProviders: () => apiFetch<ProviderResponse[]>("/api/providers"),
  createProvider: (payload: ProviderCreate) =>
    apiFetch<ProviderResponse>("/api/providers", { method: "POST", body: payload }),
  listKeys: () => apiFetch<APIKeyResponse[]>("/api/keys"),
  createKey: (payload: APIKeyCreate) =>
    apiFetch<APIKeyResponse>("/api/keys", { method: "POST", body: payload }),
  updateKey: (keyId: string, payload: APIKeyUpdate) =>
    apiFetch<APIKeyResponse>(`/api/keys/${keyId}`, { method: "PATCH", body: payload }),
  deleteKey: (keyId: string) => apiFetch<void>(`/api/keys/${keyId}`, { method: "DELETE" }),
  testKey: (keyId: string) =>
    apiFetch<APIKeyTestResult>(`/api/keys/${keyId}/test`, { method: "POST" }),
  listProfiles: () => apiFetch<ModelProfileResponse[]>("/api/profiles"),
  createProfile: (payload: ModelProfileCreate) =>
    apiFetch<ModelProfileResponse>("/api/profiles", { method: "POST", body: payload }),
};

export const privacyApi = {
  get: () => apiFetch<PrivacySettingsResponse>("/api/settings/privacy"),
  update: (payload: PrivacySettingsUpdate) =>
    apiFetch<PrivacySettingsResponse>("/api/settings/privacy", { method: "PUT", body: payload }),
  purge: () => apiFetch<PurgeResultResponse>("/api/settings/privacy/purge", { method: "POST" }),
};

export const logsApi = {
  listUsage: () => apiFetch<UsageLogResponse[]>("/api/usage-logs"),
  listAudit: (limit = 50, offset = 0) =>
    apiFetch<PaginatedAuditLogs>(`/api/audit-logs?limit=${limit}&offset=${offset}`),
};

export const usersApi = {
  list: () => apiFetch<UserResponse[]>("/api/users"),
  create: (payload: UserCreate) =>
    apiFetch<UserResponse>("/api/users", { method: "POST", body: payload }),
  update: (userId: string, payload: UserUpdate) =>
    apiFetch<UserResponse>(`/api/users/${userId}`, { method: "PATCH", body: payload }),
  delete: (userId: string) => apiFetch<void>(`/api/users/${userId}`, { method: "DELETE" }),
};
