// Same-origin fetch — UI is served from :7000, API is at /api on the same origin.
// (Once codegen.sh is wired, this file is replaced by `import { client } from './generated/client'`.)

export type JobType = "compile" | "eval";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  program: string | null;
  version: string | null;
  dataset: string | null;
  split: string | null;
  parent_job_id: string | null;
  config_path: string | null;
  baked_sha: string | null;
  run_label: string;
  attempt: number;
  worker_id: string | null;
  lease_expires_at: string | null;
  emitted_run_number: number | null;
  export_run_number: number | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  summary: Record<string, unknown> | null;
  ui_url: string;
  traces_url: string;
}

export interface Artifact {
  id: string;
  job_id: string;
  relative_path: string;
  kind: string;
  size_bytes: number;
  sha256: string;
  attempt: number;
  created_at: string;
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  listJobs(params?: Record<string, string | undefined>): Promise<Job[]> {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params || {})) if (v) q.set(k, v);
    const s = q.toString();
    return fetchJSON<Job[]>(`/jobs${s ? `?${s}` : ""}`);
  },
  getJob(id: string): Promise<Job> {
    return fetchJSON<Job>(`/jobs/${id}`);
  },
  cancelJob(id: string): Promise<Job> {
    return fetchJSON<Job>(`/jobs/${id}/cancel`, { method: "POST" });
  },
  listArtifacts(id: string): Promise<Artifact[]> {
    return fetchJSON<Artifact[]>(`/jobs/${id}/artifacts`);
  },
  artifactsTarUrl(id: string): string {
    return `/api/jobs/${id}/artifacts.tar.gz`;
  },
  artifactUrl(jobId: string, artId: string): string {
    return `/api/jobs/${jobId}/artifacts/${artId}`;
  },
};
