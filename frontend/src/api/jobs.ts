import { apiFetch } from "./client";
import type { JobResponse } from "@/types/job";

export function getJob(jobId: string): Promise<JobResponse> {
  return apiFetch<JobResponse>(`/api/v1/jobs/${jobId}`);
}
