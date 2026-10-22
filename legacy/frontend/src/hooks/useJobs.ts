import { useCallback, useEffect, useState } from "react";
import { listJobs, type ListJobsParams } from "../api/jobs";
import type { Job } from "../types/job";

export function useJobs(params: ListJobsParams) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { status, q, skip, limit } = params;

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listJobs({ status, q, skip, limit });
      setJobs(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, [status, q, skip, limit]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { jobs, total, loading, error, reload };
}
