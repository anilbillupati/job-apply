import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { Progress, Run, RunStatus } from "@/api/types";

const ACTIVE: RunStatus[] = ["queued", "running", "cancelling"];

/** Subscribe to the run's SSE stream and merge updates into the ["run", id] query cache. */
export function useRunEvents(runId: number, status: RunStatus | undefined) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const active = !!status && ACTIVE.includes(status);

  useEffect(() => {
    if (!active) return;
    const es = new EventSource(api.eventsUrl(runId));
    es.onopen = () => setConnected(true);
    es.addEventListener("progress", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as {
        status: RunStatus;
        progress: Progress;
        cost_usd: number;
        error: string | null;
        round: number;
      };
      qc.setQueryData<Run>(["run", runId], (old) => (old ? { ...old, ...data } : old));
    });
    es.addEventListener("done", () => {
      es.close();
      setConnected(false);
      qc.invalidateQueries({ queryKey: ["run", runId] });
      qc.invalidateQueries({ queryKey: ["jobs", runId] });
      qc.invalidateQueries({ queryKey: ["runs"] });
    });
    es.onerror = () => setConnected(false); // EventSource reconnects on its own
    return () => {
      es.close();
      setConnected(false);
    };
  }, [runId, active, qc]);

  return connected;
}
