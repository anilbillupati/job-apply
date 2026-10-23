import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, History, Info, KeyRound, Loader2, PlugZap, Save, Trash2, XCircle } from "lucide-react";
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
  const qc = useQueryClient();
  const status = useQuery({
    queryKey: ["apify-status"],
    queryFn: () => api.apifyStatus(false),
    staleTime: 60_000,
  });

  const test = useMutation({
    mutationFn: () => api.apifyStatus(true),
    onSuccess: (data) => {
      qc.setQueryData(["apify-status"], data);
      if (data.connected) {
        toast.success(`Connected as ${data.username}`);
      } else if (data.error) {
        toast.error(`Connection failed: ${data.error}`);
      }
    },
    onError: (err: any) => toast.error(err.message || "Failed to test connection"),
  });

  const s = test.data ?? status.data;
  const isTesting = test.isPending;

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
        <Button variant="outline" size="sm" onClick={() => test.mutate()} disabled={isTesting}>
          {isTesting ? <Loader2 className="animate-spin" /> : <PlugZap />} Test
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <ErrorNote error={test.error ?? status.error} />
        {status.isLoading && !s && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-2 w-full" />
          </div>
        )}
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

function AnthropicKeyCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["anthropic-key"], queryFn: api.anthropicKey, staleTime: 60_000 });
  const [key, setKey] = useState("");
  const [confirm, setConfirm] = useState(false);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["anthropic-key"] });
    qc.invalidateQueries({ queryKey: ["settings"] });
    qc.invalidateQueries({ queryKey: ["meta"] });
  };
  const save = useMutation({
    mutationFn: () => api.saveAnthropicKey(key.trim()),
    onSuccess: (r) => {
      setKey("");
      refresh();
      if (r.warning) toast.warning(r.warning);
      else toast.success("Anthropic key verified and saved");
    },
  });
  const remove = useMutation({
    mutationFn: api.removeAnthropicKey,
    onSuccess: () => {
      setConfirm(false);
      refresh();
      toast.success("Anthropic key removed");
    },
  });
  const test = useMutation({
    mutationFn: api.testAnthropicKey,
    onSuccess: (r) => (r.ok ? toast.success(r.detail) : toast.error(r.detail)),
    onError: (e) => toast.error(e.message),
  });
  const s = status.data;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4" /> Anthropic API key <Badge variant="secondary" className="text-xs font-normal">Optional</Badge>
          </CardTitle>
          <CardDescription>
            For Claude-powered resume scoring. Uses Claude Sonnet / Opus models from console.anthropic.com.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={!s?.configured || test.isPending}>
          {test.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Test
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <ErrorNote error={status.error} />
        {s && (
          <p className="flex flex-wrap items-center gap-2">
            {s.configured ? (
              <>
                <CheckCircle2 className="h-4 w-4 text-success" />
                <span>
                  Active key <span className="font-mono">{s.masked}</span>
                </span>
                <Badge variant="outline">{s.source === "ui" ? "saved here" : "from .env"}</Badge>
                {s.saved_at && <span className="text-xs text-muted-foreground">saved {fmtDateTime(s.saved_at)}</span>}
              </>
            ) : (
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Info className="h-4 w-4 text-primary shrink-0" />
                <span>No Anthropic key configured.</span>
              </span>
            )}
          </p>
        )}
        {s?.unreadable && (
          <p className="text-xs text-destructive">
            A saved key exists but can't be decrypted (the secret key file changed). Save the key again.
          </p>
        )}
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Input
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={s?.source === "ui" ? "Paste a new key to replace it (sk-ant-api03-…)" : "sk-ant-api03-… (or 'test' for mock)"}
            aria-label="Anthropic API key"
          />
          <Button type="submit" disabled={!key.trim() || save.isPending} className="shrink-0">
            {save.isPending ? <Loader2 className="animate-spin" /> : <Save />}
            {s?.source === "ui" ? "Replace key" : "Save key"}
          </Button>
          {s?.source === "ui" && (
            <Button type="button" variant="outline" onClick={() => setConfirm(true)} className="shrink-0">
              <Trash2 /> Remove
            </Button>
          )}
        </form>
        <p className="text-xs text-muted-foreground">
          Format: <code className="font-mono text-foreground">sk-ant-api03-...</code> from console.anthropic.com, or type <code className="font-mono text-foreground">test</code> for demo mode.
        </p>
        <ErrorNote error={save.error} />
      </CardContent>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle className="text-lg font-semibold">Remove the saved Anthropic key?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            {s?.env_available
              ? "JobRadar will fall back to ANTHROPIC_API_KEY from .env."
              : "Without a key, scoring falls back to the keyword heuristic."}
          </DialogDescription>
          <ErrorNote error={remove.error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>
              {remove.isPending && <Loader2 className="animate-spin" />} Remove key
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function GoogleKeyCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["google-key"], queryFn: api.googleKey, staleTime: 60_000 });
  const [key, setKey] = useState("");
  const [confirm, setConfirm] = useState(false);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["google-key"] });
    qc.invalidateQueries({ queryKey: ["settings"] });
    qc.invalidateQueries({ queryKey: ["meta"] });
  };
  const save = useMutation({
    mutationFn: () => api.saveGoogleKey(key.trim()),
    onSuccess: (r) => {
      setKey("");
      refresh();
      if (r.warning) toast.warning(r.warning);
      else toast.success("Google AI Studio key saved and verified");
    },
    onError: (e: any) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: api.removeGoogleKey,
    onSuccess: () => {
      setConfirm(false);
      refresh();
      toast.success("Google AI key removed");
    },
  });
  const test = useMutation({
    mutationFn: api.testGoogleKey,
    onSuccess: (r) => (r.ok ? toast.success(r.detail) : toast.error(r.detail)),
    onError: (e: any) => toast.error(e.message),
  });
  const s = status.data;

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-blue-500" /> Google AI Studio key{" "}
            <Badge variant="secondary" className="text-xs font-normal">Optional</Badge>
          </CardTitle>
          <CardDescription>
            For Gemini-powered resume scoring. Uses Gemini Flash / Pro models from{" "}
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="text-primary hover:underline">
              aistudio.google.com
            </a>
            . Takes effect only when no Anthropic key is configured.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={!s?.configured || test.isPending}>
          {test.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Test
        </Button>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <ErrorNote error={status.error} />
        {s && (
          <p className="flex flex-wrap items-center gap-2">
            {s.configured ? (
              <>
                <CheckCircle2 className="h-4 w-4 text-success" />
                <span>
                  Active key <span className="font-mono">{s.masked}</span>
                </span>
                <Badge variant="outline">{s.source === "ui" ? "saved here" : "from .env"}</Badge>
                {s.saved_at && <span className="text-xs text-muted-foreground">saved {fmtDateTime(s.saved_at)}</span>}
              </>
            ) : (
              <span className="flex items-center gap-1.5 text-muted-foreground">
                <Info className="h-4 w-4 text-primary shrink-0" />
                <span>No Google AI key configured.</span>
              </span>
            )}
          </p>
        )}
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Input
            type="password"
            autoComplete="off"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={s?.source === "ui" ? "Paste a new key to replace it (AIza… or AQ.…)" : "AIzaSy… or AQ.Ab8… from aistudio.google.com"}
            aria-label="Google AI Studio API key"
          />
          <Button type="submit" disabled={!key.trim() || save.isPending} className="shrink-0">
            {save.isPending ? <Loader2 className="animate-spin" /> : <Save />}
            {s?.source === "ui" ? "Replace key" : "Save key"}
          </Button>
          {s?.source === "ui" && (
            <Button type="button" variant="outline" onClick={() => setConfirm(true)} className="shrink-0">
              <Trash2 /> Remove
            </Button>
          )}
        </form>
        <p className="text-xs text-muted-foreground">
          Format: <code className="font-mono text-foreground">AIzaSy...</code> or <code className="font-mono text-foreground">AQ.Ab8...</code> — get one free at{" "}
          <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer" className="text-primary hover:underline">
            aistudio.google.com/apikey
          </a>
        </p>
        <ErrorNote error={save.error} />
      </CardContent>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle className="text-lg font-semibold">Remove the saved Google AI key?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            Scoring will fall back to the keyword heuristic unless an Anthropic key is configured.
          </DialogDescription>
          <ErrorNote error={remove.error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>
              {remove.isPending && <Loader2 className="animate-spin" />} Remove key
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Card>
  );
}


function ExcludedCompaniesCard() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["excluded-companies"], queryFn: api.excludedCompanies, staleTime: 60_000 });
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
  const seen = useQuery({ queryKey: ["seen-jobs"], queryFn: api.seenJobs, staleTime: 60_000 });
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
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 60_000 });
  const [draft, setDraft] = useState<AppSettings | null>(null);

  useEffect(() => {
    if (settings.data && !draft) setDraft(settings.data);
  }, [settings.data, draft]);

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
        naukri_limit: d.naukri_limit,
        max_run_cost_usd: d.max_run_cost_usd,
      }),
    onSuccess: (d) => {
      qc.setQueryData(["settings"], d);
      setDraft(d);
      toast.success("Settings saved. They apply to the next run (or expansion).");
    },
  });

  const activeDraft = draft ?? settings.data;
  const set = (patch: Partial<AppSettings>) => {
    if (activeDraft) setDraft({ ...activeDraft, ...patch });
  };
  const dirty = Boolean(draft && settings.data && JSON.stringify(draft) !== JSON.stringify(settings.data));

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <Button onClick={() => activeDraft && save.mutate(activeDraft)} disabled={!dirty || save.isPending}>
          {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save
        </Button>
      </div>
      <ErrorNote error={save.error ?? settings.error} />

      <ApifyCard />

      <AnthropicKeyCard />

      <GoogleKeyCard />

      <ExcludedCompaniesCard />

      <SeenJobsCard />

      {!activeDraft ? (
        <Card className="p-8">
          <Skeleton className="h-48 w-full" />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Scoring model</CardTitle>
              <CardDescription>
                {activeDraft.llm_configured
                  ? "An Anthropic key is configured."
                  : "No Anthropic key yet (add one above): resume analysis and scoring fall back to a heuristic."}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-[2fr_1fr]">
              <div className="space-y-1.5">
                <Label htmlFor="model">Model</Label>
                <Select id="model" value={activeDraft.llm_model} onChange={(e) => set({ llm_model: e.target.value })}>
                  {activeDraft.allowed_models.map((m) => (
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
                  value={activeDraft.llm_top_n}
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
              <ChipList values={activeDraft.agency_blocklist} onChange={(v) => set({ agency_blocklist: v })} placeholder="Add company" />
              <div className="space-y-1.5">
                <Label>Never treat as agency</Label>
                <ChipList
                  variant="outline"
                  values={activeDraft.agency_allowlist}
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
              <ChipList values={activeDraft.title_exclusions} onChange={(v) => set({ title_exclusions: v })} placeholder="Add term" />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Seniority filter</CardTitle>
              <CardDescription>Titles with these words are filtered out.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ChipList values={activeDraft.seniority_exclusions} onChange={(v) => set({ seniority_exclusions: v })} placeholder="Add word" />
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
                  value={activeDraft.allow_senior_max_years ?? ""}
                  onChange={(e) => set({ allow_senior_max_years: e.target.value === "" ? null : Number(e.target.value) })}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Search limits & cost budget</CardTitle>
              <CardDescription>
                Configure scraping limits and hard spend caps per search run.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="max_cost">Run cost cap (USD)</Label>
                  <Input
                    id="max_cost"
                    type="number"
                    min={0.5}
                    max={50}
                    step={0.5}
                    value={activeDraft.max_run_cost_usd}
                    onChange={(e) => set({ max_run_cost_usd: Number(e.target.value) })}
                  />
                  <p className="text-xs text-muted-foreground">Hard cap per search run (e.g. $5.00 for free tier credit).</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="naukri_lim">Naukri items per search</Label>
                  <Input
                    id="naukri_lim"
                    type="number"
                    min={5}
                    max={100}
                    value={activeDraft.naukri_limit ?? 30}
                    onChange={(e) => set({ naukri_limit: Number(e.target.value) })}
                  />
                  <p className="text-xs text-muted-foreground">30 items per search (with LinkedIn 20 and Indeed 10) keeps a typical run under $5.00.</p>
                </div>
              </div>
              <div className="space-y-1 text-sm text-muted-foreground pt-2 border-t">
                <p>robots.txt checks before verification: {activeDraft.respect_robots_txt ? "on" : "off"} (RESPECT_ROBOTS_TXT)</p>
                <p>No logins, no captcha solving, and low request rates. You are responsible for each site's terms.</p>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
