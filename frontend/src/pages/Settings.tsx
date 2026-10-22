import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, History, Loader2, PlugZap, Save, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { AppSettings } from "@/api/types";
import { ChipList, ErrorNote } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress, Skeleton } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/sheet";
import { fmtDateTime, usd } from "@/lib/utils";

const MODEL_LABEL: Record<string, string> = {
  "claude-sonnet-5-5": "Claude Sonnet 5.5 (default, faster and cheaper)",
  "claude-opus-5-5": "Claude Opus 5.5 (higher-quality scoring, about 2x cost)",
};

function ApifyCard() {
  const status = useMutation({ mutationFn: api.apifyStatus });
  useEffect(() => {
    status.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const s = status.data;
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="min-w-0">
          <CardTitle className="text-base">Apify connection</CardTitle>
          <CardDescription>
            Tests today's key from the pool (or APIFY_TOKEN). Manage keys on the{" "}
            <Link to="/keys" className="text-primary hover:underline">
              API keys
            </Link>{" "}
            page. Tokens are never shown.
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" onClick={() => status.mutate()} disabled={status.isPending}>
          {status.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Test
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ErrorNote error={status.error} />
        {s && !s.configured && (
          <p className="flex items-center gap-2">
            <XCircle className="h-4 w-4 text-destructive" /> No Apify key yet. Add keys on the API keys page, or set APIFY_TOKEN in <code>.env</code>.
          </p>
        )}
        {s?.configured && !s.connected && (
          <p className="flex items-start gap-2">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" /> Connection failed: {s.error}
          </p>
        )}
        {s?.connected && (
          <>
            <p className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-success" /> Connected as <b>{s.username}</b>
              {s.key_label && <span className="text-muted-foreground">using {s.key_label}</span>}
              {s.plan && <Badge variant="outline">{s.plan}</Badge>}
            </p>
            {s.monthly_limit_usd ? (
              <div className="space-y-1.5">
                <div className="flex justify-between tabular">
                  <span>Monthly usage {usd(s.monthly_usage_usd)}</span>
                  <span className="text-muted-foreground">limit {usd(s.monthly_limit_usd)}</span>
                </div>
                <Progress value={((s.monthly_usage_usd ?? 0) / s.monthly_limit_usd) * 100} />
                <p className="text-xs text-muted-foreground">
                  {usd(s.remaining_usd)} left{s.cycle_end ? `, cycle ends ${fmtDateTime(s.cycle_end)}` : ""}
                  {s.max_concurrent_runs ? ` · max ${s.max_concurrent_runs} concurrent runs` : ""}
                </p>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ExcludedCompaniesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["excluded-companies"], queryFn: api.excludedCompanies });
  const [list, setList] = useState<string[] | null>(null);
  useEffect(() => {
    if (q.data) setList(q.data.companies);
  }, [q.data]);
  const save = useMutation({
    mutationFn: (v: string[]) => api.setExcludedCompanies(v),
    onSuccess: (d) => {
      qc.setQueryData(["excluded-companies"], d);
      toast.success("Excluded companies saved");
    },
  });
  const dirty = list !== null && JSON.stringify(list) !== JSON.stringify(q.data?.companies);
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="min-w-0">
          <CardTitle className="text-base">Excluded companies</CardTitle>
          <CardDescription>
            Pre-filled into every new search (you can still edit it per search). Matches when the company name contains the
            text. You can also add a company from a job's detail panel.
          </CardDescription>
        </div>
        <Button size="sm" onClick={() => list && save.mutate(list)} disabled={!dirty || save.isPending}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save
        </Button>
      </CardHeader>
      <CardContent>
        <ErrorNote error={save.error ?? q.error} />
        {list && <ChipList values={list} onChange={setList} placeholder="Company name" />}
      </CardContent>
    </Card>
  );
}

function SeenJobsCard() {
  const qc = useQueryClient();
  const seen = useQuery({ queryKey: ["seen-jobs"], queryFn: api.seenJobs });
  const [confirm, setConfirm] = useState(false);
  const clear = useMutation({
    mutationFn: api.clearSeenJobs,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["seen-jobs"] });
      setConfirm(false);
      toast.success(`Cleared ${r.deleted} job IDs`);
    },
  });
  const d = seen.data;
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="h-4 w-4" /> Already-seen jobs
          </CardTitle>
          <CardDescription>
            Job IDs that were shown in a ranked list or that you shortlisted, applied to or rejected. Later searches skip
            them, so you never see or apply to the same job twice.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" onClick={() => setConfirm(true)} disabled={!d?.total}>
          <Trash2 /> Clear
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ErrorNote error={seen.error} />
        {d && (
          <>
            <p>
              <b className="tabular">{d.total}</b> job IDs remembered ({d.by_reason.shown ?? 0} shown,{" "}
              {d.by_reason.marked ?? 0} marked by you).
            </p>
            {d.recent.length > 0 && (
              <ul className="space-y-1 text-xs text-muted-foreground">
                {d.recent.slice(0, 8).map((r) => (
                  <li key={r.platform + r.platform_job_id} className="truncate">
                    <span className="text-foreground">{r.title}</span> · {r.company} · {r.platform} #{r.platform_job_id}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </CardContent>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle className="text-lg font-semibold">Clear the seen-jobs history?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            All {d?.total} remembered job IDs are forgotten, so jobs you have already seen or applied to can appear again in
            future searches. This can't be undone.
          </DialogDescription>
          <ErrorNote error={clear.error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => clear.mutate()} disabled={clear.isPending}>
              {clear.isPending && <Loader2 className="animate-spin" />} Clear history
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export function Settings() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [draft, setDraft] = useState<AppSettings | null>(null);
  useEffect(() => {
    if (settings.data) setDraft(settings.data);
  }, [settings.data]);

  const save = useMutation({
    mutationFn: (d: AppSettings) =>
      api.saveSettings({
        llm_model: d.llm_model,
        llm_top_n: d.llm_top_n,
        agency_blocklist: d.agency_blocklist,
        agency_allowlist: d.agency_allowlist,
        title_exclusions: d.title_exclusions,
        seniority_exclusions: d.seniority_exclusions,
        allow_senior_max_years: d.allow_senior_max_years,
      }),
    onSuccess: (d) => {
      qc.setQueryData(["settings"], d);
      toast.success("Settings saved. They apply to the next run (or expansion).");
    },
  });

  if (settings.isLoading || !draft) return <Skeleton className="h-96 w-full" />;
  const set = (patch: Partial<AppSettings>) => setDraft({ ...draft, ...patch });
  const dirty = JSON.stringify(draft) !== JSON.stringify(settings.data);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <Button onClick={() => save.mutate(draft)} disabled={!dirty || save.isPending}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save
        </Button>
      </div>
      <ErrorNote error={save.error ?? settings.error} />

      <ApifyCard />

      <ExcludedCompaniesCard />

      <SeenJobsCard />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Scoring model</CardTitle>
          <CardDescription>
            {draft.llm_configured
              ? "ANTHROPIC_API_KEY is configured."
              : "ANTHROPIC_API_KEY is not set: resume analysis and scoring fall back to a labelled heuristic."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-[2fr_1fr]">
          <div className="space-y-1.5">
            <Label htmlFor="model">Model</Label>
            <Select id="model" value={draft.llm_model} onChange={(e) => set({ llm_model: e.target.value })}>
              {draft.allowed_models.map((m) => (
                <option key={m} value={m}>
                  {MODEL_LABEL[m] ?? m}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="topn">Jobs sent to the LLM</Label>
            <Input
              id="topn"
              type="number"
              min={5}
              max={500}
              value={draft.llm_top_n}
              onChange={(e) => set({ llm_top_n: Number(e.target.value) })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Agency blocklist</CardTitle>
          <CardDescription>
            Company names (substring match) dropped as agencies or talent marketplaces, on top of the platform flags and the
            name check (recruit, staffing, talent, consultancy, placement, manpower).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ChipList values={draft.agency_blocklist} onChange={(v) => set({ agency_blocklist: v })} placeholder="Add company" />
          <div className="space-y-1.5">
            <Label>Never treat as agency</Label>
            <ChipList
              variant="outline"
              values={draft.agency_allowlist}
              onChange={(v) => set({ agency_allowlist: v })}
              placeholder="Add employer"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Title exclusions</CardTitle>
          <CardDescription>Titles containing these words or terms are filtered out as irrelevant.</CardDescription>
        </CardHeader>
        <CardContent>
          <ChipList values={draft.title_exclusions} onChange={(v) => set({ title_exclusions: v })} placeholder="Add term" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Seniority filter</CardTitle>
          <CardDescription>Titles with these words are filtered out.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ChipList values={draft.seniority_exclusions} onChange={(v) => set({ seniority_exclusions: v })} placeholder="Add word" />
          <div className="space-y-1.5">
            <Label htmlFor="senior">Allow "Senior" / "Sr" titles that ask for at most N years</Label>
            <p className="text-xs text-muted-foreground">
              Indian startups often title 2–4-year roles "Senior". Leave empty to always exclude them.
            </p>
            <Input
              id="senior"
              type="number"
              min={0}
              max={20}
              step="0.5"
              className="w-32"
              value={draft.allow_senior_max_years ?? ""}
              onChange={(e) => set({ allow_senior_max_years: e.target.value === "" ? null : Number(e.target.value) })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Limits and compliance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          <p>Run cost cap (MAX_RUN_COST_USD): {usd(draft.max_run_cost_usd)}</p>
          <p>robots.txt checks before verification: {draft.respect_robots_txt ? "on" : "off"} (RESPECT_ROBOTS_TXT)</p>
          <p>No logins, no captcha solving, and low request rates. You are responsible for each site's terms.</p>
        </CardContent>
      </Card>
    </div>
  );
}
