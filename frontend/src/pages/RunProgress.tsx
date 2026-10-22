import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, CircleDot, Loader2, OctagonX, Radio, RotateCcw, Table2, XCircle } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { Run } from "@/api/types";
import { ErrorNote, Stat } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress, Skeleton } from "@/components/ui/progress";
import { useRunEvents } from "@/hooks/useRunEvents";
import { cn, fmtDateTime, PLATFORM_LABEL, usd } from "@/lib/utils";

const RUN_STAGES = ["scraping", "normalizing", "filtering", "deduping", "pre-scoring", "verifying", "scoring", "finalizing"];
const PLATFORM_STEPS = ["Scraping", "Normalizing", "Deduping", "Verifying", "Scoring"];

export function statusBadge(status: Run["status"]) {
  const map: Record<string, "success" | "warning" | "destructive" | "secondary" | "outline"> = {
    completed: "success",
    running: "secondary",
    queued: "outline",
    cancelling: "warning",
    cancelled: "warning",
    failed: "destructive",
    draft: "outline",
  };
  return (
    <Badge variant={map[status] ?? "outline"} className="capitalize">
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin" />}
      {status}
    </Badge>
  );
}

function overallPercent(run: Run) {
  if (run.status === "completed") return 100;
  const p = run.progress ?? {};
  const stage = p.stage ?? "queued";
  const plats = Object.values(p.platforms ?? {});
  const tasksTotal = plats.reduce((a, x) => a + (x.tasks_total ?? 0), 0);
  const tasksDone = plats.reduce((a, x) => a + (x.tasks_done ?? 0), 0);
  if (stage === "queued") return 1;
  if (stage === "scraping") return 2 + 48 * (tasksTotal ? tasksDone / tasksTotal : 0);
  if (["normalizing", "filtering", "deduping", "pre-scoring"].includes(stage))
    return 50 + RUN_STAGES.indexOf(stage) * 1.5;
  if (stage === "verifying") {
    const tot = plats.reduce((a, x) => a + (x.verify_total ?? 0), 0);
    const done = plats.reduce((a, x) => a + (x.verify_done ?? 0), 0);
    return 56 + 24 * (tot ? done / tot : 0);
  }
  if (stage === "scoring") {
    const s = p.scoring;
    return 80 + 18 * (s && s.total ? (s.done + s.failed) / s.total : 0);
  }
  if (stage === "finalizing") return 99;
  return 0;
}

/** Index of the current step for one platform's mini-pipeline (5 = all done). */
function platformStep(runStage: string | undefined, platformStage: string | undefined, finished: boolean) {
  if (finished) return 5;
  if (runStage === "scraping") return platformStage === "scraped" ? 1 : 0;
  if (runStage === "normalizing" || runStage === "filtering") return 1;
  if (runStage === "deduping" || runStage === "pre-scoring") return 2;
  if (runStage === "verifying") return platformStage === "verified" ? 4 : 3;
  if (runStage === "scoring" || runStage === "finalizing") return 4;
  return 0;
}

export function RunProgress() {
  const id = Number(useParams().id);
  const qc = useQueryClient();
  const run = useQuery({ queryKey: ["run", id], queryFn: () => api.run(id) });
  const live = useRunEvents(id, run.data?.status);
  const cancel = useMutation({
    mutationFn: () => api.cancelRun(id),
    onSuccess: (r) => {
      qc.setQueryData(["run", id], r);
      toast.info("Cancelling: Apify runs are being aborted");
    },
  });
  const retry = useMutation({
    mutationFn: () => api.startRun(id),
    onSuccess: (r) => qc.setQueryData(["run", id], r),
    onError: (e) => toast.error(e.message),
  });

  if (run.isLoading) return <Skeleton className="h-64 w-full" />;
  if (run.error || !run.data) return <ErrorNote error={run.error ?? "Run not found"} />;
  const r = run.data;
  const p = r.progress ?? {};
  const c = p.counts ?? {};
  const active = ["queued", "running", "cancelling"].includes(r.status);
  const finished = r.status === "completed";
  const pct = overallPercent(r);
  const cap = r.estimate?.cap_usd ?? 3;
  const apifySpent = p.cost?.apify_total ?? 0;
  const platforms = r.platforms.filter((x) => p.platforms?.[x] || active || finished);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Run #{r.id}</h1>
            {statusBadge(r.status)}
            {r.round > 1 && <Badge variant="outline">Round {r.round}</Badge>}
            {r.estimate?.demo && <Badge variant="outline">Demo data</Badge>}
            {live && (
              <span className="inline-flex items-center gap-1 text-xs text-success">
                <Radio className="h-3.5 w-3.5" /> live
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {r.roles.join(", ")} · {[...r.locations, ...(r.include_remote_india ? ["Remote (India)"] : [])].join(", ")} ·
            last {r.posted_within_days} days
          </p>
        </div>
        <div className="flex gap-2">
          {r.status === "failed" && (
            <Button variant="outline" onClick={() => retry.mutate()} disabled={retry.isPending}>
              <RotateCcw /> Resume
            </Button>
          )}
          {active && (
            <Button variant="destructive" onClick={() => cancel.mutate()} disabled={cancel.isPending || r.status === "cancelling"}>
              <OctagonX /> Cancel
            </Button>
          )}
          {(finished || (r.final_count ?? 0) > 0) && (
            <Button asChild>
              <Link to={`/runs/${r.id}/results`}>
                <Table2 /> View results
              </Link>
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="space-y-3 pt-4 sm:pt-6">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium capitalize">{finished ? "Completed" : (p.stage ?? r.status)}</span>
            <span className="tabular text-muted-foreground">{Math.round(pct)}%</span>
          </div>
          <Progress
            value={pct}
            indicatorClassName={cn(r.status === "failed" && "bg-destructive", r.status === "cancelled" && "bg-warning")}
          />
          {r.error && <ErrorNote error={r.error} />}
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-3">
        {platforms.map((pl) => {
          const pp = p.platforms?.[pl] ?? {};
          const step = platformStep(p.stage, pp.stage, finished);
          return (
            <Card key={pl}>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">{PLATFORM_LABEL[pl]}</CardTitle>
                <CardDescription className="tabular">
                  {pp.tasks_done ?? 0}/{pp.tasks_total ?? 0} Apify runs · {pp.items ?? 0} items
                  {pp.verify_total ? ` · verified ${pp.verify_done ?? 0}/${pp.verify_total}` : ""}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="space-y-1.5">
                  {PLATFORM_STEPS.map((label, i) => (
                    <li key={label} className="flex items-center gap-2 text-sm">
                      {i < step ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : i === step && active ? (
                        <CircleDot className="h-4 w-4 animate-pulse text-primary" />
                      ) : (
                        <Circle className="h-4 w-4 text-muted-foreground/50" />
                      )}
                      <span className={cn(i > step && "text-muted-foreground")}>{label}</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        <Stat label="Collected" value={c.collected ?? "—"} />
        <Stat label="Unique" value={c.unique ?? "—"} />
        <Stat label="Passed filters" value={c.passed_filters ?? "—"} />
        <Stat label="After dedupe" value={c.after_dedupe ?? "—"} />
        <Stat label="Verified active" value={c.verified?.verified_active ?? "—"} />
        <Stat label="Scored" value={c.scored ?? "—"} hint={p.scoring ? `${p.scoring.done}/${p.scoring.total}` : undefined} />
        <Stat label="Final" value={c.final ?? "—"} hint={`target ${r.target_count}`} />
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Spend</CardTitle>
            <CardDescription>Apify spend against the run cap (MAX_RUN_COST_USD)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between text-sm tabular">
              <span>Apify {usd(apifySpent, 3)}</span>
              <span className="text-muted-foreground">cap {usd(cap)}</span>
            </div>
            <Progress value={(apifySpent / cap) * 100} indicatorClassName={apifySpent > cap * 0.8 ? "bg-warning" : undefined} />
            <div className="flex flex-wrap gap-2 text-xs">
              {Object.entries(p.cost?.apify ?? {}).map(([k, v]) => (
                <Badge key={k} variant="outline">
                  {PLATFORM_LABEL[k]} {usd(v, 3)}
                </Badge>
              ))}
              <Badge variant="outline">LLM {usd(p.cost?.llm ?? 0, 3)}</Badge>
              <Badge variant="secondary">Total {usd(r.cost_usd, 3)}</Badge>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="max-h-56 space-y-1 overflow-y-auto text-xs">
              {[...(p.log ?? [])].reverse().map((l, i) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0 tabular text-muted-foreground">
                    {new Date(l.ts).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </span>
                  <span className="min-w-0 break-words">{l.msg}</span>
                </li>
              ))}
              {!p.log?.length && <li className="text-muted-foreground">Waiting for the worker…</li>}
            </ul>
          </CardContent>
        </Card>
      </div>

      {r.status === "failed" && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <XCircle className="h-4 w-4 text-destructive" /> Failed at {fmtDateTime(r.finished_at)}. Completed stages are
          kept; starting again resumes from the last completed stage without re-paying Apify.
        </p>
      )}
    </div>
  );
}
