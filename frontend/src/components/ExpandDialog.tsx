import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Expand, Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { ExpandPreview, Run } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/sheet";
import { EstimateTable } from "@/pages/NewSearch";

function describeChanges(p: ExpandPreview) {
  const ch = p.changes as Record<string, unknown>;
  if (ch.keywords_added) {
    const kws = Object.values(ch.keywords_added as Record<string, string[]>).flat();
    return `Adds ${kws.length} keywords: ${kws.join(", ")}.`;
  }
  if (ch.posted_within_days) return "Re-runs every search with a 14-day window.";
  if (ch.depth) return "Re-runs every search fetching twice as many results per search.";
  return "";
}

export function ExpandCard({ run }: { run: Run }) {
  const [preview, setPreview] = useState<ExpandPreview | null>(null);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const load = useMutation({ mutationFn: () => api.expandRun(run.id, false), onSuccess: setPreview });
  const confirm = useMutation({
    mutationFn: () => api.expandRun(run.id, true),
    onSuccess: () => {
      toast.success("Expanded search started");
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["run", run.id] });
      navigate(`/runs/${run.id}`);
    },
  });

  const final = run.final_count ?? 0;
  if (run.status !== "completed" || final >= run.target_count || !run.next_expand_step) return null;

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning/10 p-4 sm:flex-row sm:items-center">
      <div className="flex-1 text-sm">
        <b>
          {final} of {run.target_count} target jobs found.
        </b>{" "}
        Next step: {run.next_expand_step.label.toLowerCase()}. The minimum score stays at {run.min_score}.
      </div>
      <Button variant="outline" onClick={() => load.mutate()} disabled={load.isPending}>
        {load.isPending ? <Loader2 className="animate-spin" /> : <Expand />} Expand search
      </Button>
      <ErrorNote error={load.error} />

      <Dialog open={!!preview} onOpenChange={(o) => !o && setPreview(null)}>
        <DialogContent>
          {preview && (
            <>
              <DialogTitle className="text-lg font-semibold">{preview.label}</DialogTitle>
              <DialogDescription className="text-sm text-muted-foreground">
                {describeChanges(preview)} Results merge into this run and duplicates are skipped. Your minimum score of{" "}
                {preview.min_score_unchanged} is not changed.
              </DialogDescription>
              <EstimateTable est={preview.estimate} />
              <ErrorNote error={confirm.error} />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setPreview(null)}>
                  Cancel
                </Button>
                <Button onClick={() => confirm.mutate()} disabled={confirm.isPending || !preview.estimate.ok}>
                  {confirm.isPending && <Loader2 className="animate-spin" />} Confirm and spend
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
