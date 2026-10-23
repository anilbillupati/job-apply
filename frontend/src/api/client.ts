import type {
  AnthropicKeyStatus,
  GoogleKeyStatus,
  ApifyKey,
  ApifyStatus,
  AppSettings,
  ExpandPreview,
  JobDetail,
  JobPage,
  JobRow,
  KeyImportResult,
  KeyPool,
  KeyTest,
  KeyUsage,
  Meta,
  TestAllResult,
  Profile,
  Resume,
  Run,
  RunInput,
  SeenJobs,
} from "./types";

export const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = init.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

const json = (method: string, body?: unknown): RequestInit => ({ method, body: JSON.stringify(body ?? {}) });

export const api = {
  meta: () => request<Meta>("/meta"),

  uploadResumes: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return request<Resume>("/resumes", { method: "POST", body: fd });
  },
  resumes: () => request<Resume[]>("/resumes"),
  resume: (id: number) => request<Resume>(`/resumes/${id}`),
  updateProfile: (id: number, profile: Profile) => request<Resume>(`/resumes/${id}/profile`, json("PUT", profile)),

  suggestKeywords: (resume_id: number, roles: string[]) =>
    request<{ keywords: Record<string, string[]> }>("/keywords/suggest", json("POST", { resume_id, roles })),
  createRun: (body: RunInput) => request<Run>("/runs", json("POST", body)),
  updateRun: (id: number, body: RunInput) => request<Run>(`/runs/${id}`, json("PATCH", body)),
  runs: () => request<Run[]>("/runs"),
  run: (id: number) => request<Run>(`/runs/${id}`),
  startRun: (id: number) => request<Run>(`/runs/${id}/start`, json("POST")),
  cancelRun: (id: number) => request<Run>(`/runs/${id}/cancel`, json("POST")),
  expandRun: (id: number, confirm: boolean) => request<ExpandPreview>(`/runs/${id}/expand`, json("POST", { confirm })),

  jobs: (runId: number, params: Record<string, string | number | undefined>) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => v !== undefined && v !== "" && qs.set(k, String(v)));
    return request<JobPage>(`/runs/${runId}/jobs?${qs}`);
  },
  job: (id: number) => request<JobDetail>(`/jobs/${id}`),
  patchJob: (id: number, body: { user_state?: JobRow["user_state"]; user_note?: string | null }) =>
    request<JobRow>(`/jobs/${id}`, json("PATCH", body)),

  settings: () => request<AppSettings>("/settings"),
  saveSettings: (body: Partial<AppSettings>) => request<AppSettings>("/settings", json("PUT", body)),
  apifyStatus: (refresh = false) => request<ApifyStatus>(`/settings/apify${refresh ? "?refresh=true" : ""}`),

  keys: () => request<KeyPool>("/apify/keys"),
  addKey: (token: string, label: string) => request<ApifyKey>("/apify/keys", json("POST", { token, label: label || null })),
  importKeys: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<KeyImportResult>("/apify/keys/import", { method: "POST", body: fd });
  },
  updateKey: (id: number, body: { label?: string; active?: boolean }) =>
    request<ApifyKey>(`/apify/keys/${id}`, json("PATCH", body)),
  deleteKey: (id: number) => request<{ ok: boolean }>(`/apify/keys/${id}`, { method: "DELETE" }),
  testKey: (id: number) => request<KeyTest>(`/apify/keys/${id}/test`, json("POST")),
  testAllKeys: () => request<TestAllResult>("/apify/keys/test-all", json("POST")),
  keyUsage: (limit = 200) => request<KeyUsage[]>(`/apify/keys/usage?limit=${limit}`),

  anthropicKey: () => request<AnthropicKeyStatus>("/settings/anthropic"),
  saveAnthropicKey: (api_key: string) => request<AnthropicKeyStatus>("/settings/anthropic", json("PUT", { api_key })),
  removeAnthropicKey: () => request<AnthropicKeyStatus>("/settings/anthropic", { method: "DELETE" }),
  testAnthropicKey: () =>
    request<{ ok: boolean; detail: string; source?: string }>("/settings/anthropic/test", json("POST")),

  googleKey: () => request<GoogleKeyStatus>("/settings/google"),
  saveGoogleKey: (api_key: string) => request<GoogleKeyStatus>("/settings/google", json("PUT", { api_key })),
  removeGoogleKey: () => request<GoogleKeyStatus>("/settings/google", { method: "DELETE" }),
  testGoogleKey: () =>
    request<{ ok: boolean; detail: string; source?: string }>("/settings/google/test", json("POST")),

  seenJobs: () => request<SeenJobs>("/seen-jobs"),
  clearSeenJobs: () => request<{ ok: boolean; deleted: number }>("/seen-jobs", { method: "DELETE" }),
  excludedCompanies: () => request<{ companies: string[] }>("/settings/excluded-companies"),
  setExcludedCompanies: (companies: string[]) =>
    request<{ companies: string[] }>("/settings/excluded-companies", json("PUT", { companies })),
  excludeCompany: (company: string) =>
    request<{ companies: string[] }>("/settings/excluded-companies/add", json("POST", { companies: [company] })),

  uploadExcel: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ run_id: number; filename: string; total_imported: number }>("/excel/upload", {
      method: "POST",
      body: fd,
    });
  },
  templateUrl: () => `${API_BASE}/excel/template`,
  deleteRun: (runId: number) => request<{ ok: boolean }>(`/runs/${runId}`, { method: "DELETE" }),
  deleteJob: (jobId: number) => request<{ ok: boolean }>(`/jobs/${jobId}`, { method: "DELETE" }),

  exportUrl: (runId: number, full = false) => `${API_BASE}/runs/${runId}/export.xlsx?full=${full}`,
  eventsUrl: (runId: number) => `${API_BASE}/runs/${runId}/events`,
};
