import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { ErrorNote } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";
import { fmtDateTime, PLATFORM_LABEL, usd } from "@/lib/utils";
import { statusBadge } from "@/pages/RunProgress";

export function Runs() {
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <Button asChild>
          <Link to="/new">
            <Plus /> New search
          </Link>
        </Button>
      </div>
      <ErrorNote error={runs.error} />
      {runs.isLoading && <Skeleton className="h-40 w-full" />}
      {runs.data?.length === 0 && (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          No runs yet. Start a <Link to="/new" className="text-primary hover:underline">new search</Link>, or load the
          demo with <code>make seed</code>.
        </Card>
      )}
      <ul className="space-y-2">
        {runs.data?.map((r) => (
          <li key={r.id}>
            <Link
              to={r.status === "completed" ? `/runs/${r.id}/results` : `/runs/${r.id}`}
              className="flex items-center gap-3 rounded-lg border bg-card p-4 transition-colors hover:bg-accent/50"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Run #{r.id}</span>
                  {statusBadge(r.status)}
                  {r.estimate?.demo && <Badge variant="outline">Demo</Badge>}
                </div>
                <div className="truncate text-sm text-muted-foreground">
                  {r.roles.join(", ")} · {r.locations.join(", ")}
                  {r.include_remote_india ? ", Remote" : ""} · {r.platforms.map((p) => PLATFORM_LABEL[p]).join("/")}
                </div>
                <div className="text-xs text-muted-foreground">{fmtDateTime(r.created_at)}</div>
              </div>
              <div className="hidden text-right text-sm sm:block">
                <div className="font-semibold tabular">{r.final_count ?? "—"} jobs</div>
                <div className="text-xs text-muted-foreground tabular">{usd(r.cost_usd, 3)}</div>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
