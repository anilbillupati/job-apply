import type { ExtractionResult, Job, JobList, JobStatus, JobUpdate } from "../types/job";
import { request } from "./client";

export interface ListJobsParams {
  status?: JobStatus;
  q?: string;
  skip?: number;
  limit?: number;
}

export function listJobs(params: ListJobsParams = {}): Promise<JobList> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") query.set(key, String(value));
  });
  const qs = query.toString();
  return request<JobList>(`/jobs${qs ? `?${qs}` : ""}`);
}

export function getJob(id: number): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export function updateJob(id: number, data: JobUpdate): Promise<Job> {
  return request<Job>(`/jobs/${id}`, { method: "PATCH", body: JSON.stringify(data) });
}

export function deleteJob(id: number): Promise<void> {
  return request<void>(`/jobs/${id}`, { method: "DELETE" });
}

export function extractJob(url: string, save = true): Promise<ExtractionResult> {
  return request<ExtractionResult>("/extract", {
    method: "POST",
    body: JSON.stringify({ url, save }),
  });
}
