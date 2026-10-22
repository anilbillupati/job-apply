import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ArrowRight, FileText, Loader2, Play, RefreshCw, Upload } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { Estimate, Profile, Run, RunInput } from "@/api/types";
import { ChipList, ErrorNote, ToggleChip } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn, fmtDateTime, PLATFORM_LABEL, usd } from "@/lib/utils";

const STEPS = ["Resume", "Profile", "Roles", "Locations", "Search options", "Keywords & start"];
const STORAGE_KEY = "jobradar.wizard";

interface WizardState {
  step: number;
  resumeId?: number;
  profile?: Profile;
  roles: string[];
  locations: string[];
  include_remote_india: boolean;
  work_arrangement: RunInput["work_arrangement"];
  platforms: string[];
  posted_within_days: 7 | 14;
  target_count: number;
  min_score: number;
  exclude_linkedin_easy_apply: boolean;
  keywords?: Record<string, string[]>;
  keywordRoles?: string[];
  exclude_companies?: string[];
  runId?: number;
}

const INITIAL: WizardState = {
  step: 0,
  roles: [],
  locations: ["Hyderabad", "Bengaluru", "Chennai", "Pune"],
  include_remote_india: true,
  work_arrangement: "any",
  platforms: ["linkedin", "naukri", "indeed"],
  posted_within_days: 7,
  target_count: 60,
  min_score: 65,
  exclude_linkedin_easy_apply: true,
};

function loadState(): WizardState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? { ...INITIAL, ...JSON.parse(raw) } : INITIAL;
  } catch {
    return INITIAL;
  }
}

function toggle<T>(list: T[], v: T) {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export function NewSearch() {
  const [s, setS] = useState<WizardState>(loadState);
  const update = (patch: Partial<WizardState>) => setS((prev) => ({ ...prev, ...patch }));
  const meta = useQuery({ queryKey: ["meta"], queryFn: api.meta });

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    } catch {
      /* storage unavailable */
    }
  }, [s]);

  const canNext = [
    !!s.resumeId && !!s.profile,
    !!s.profile,
    s.roles.length > 0,
    s.locations.length > 0 || s.include_remote_india,
    s.platforms.length > 0,
    true,
  ][s.step];

  const reset = () => {
    setS(INITIAL);
  };

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">New search</h1>
          <p className="text-sm text-muted-foreground">
            Step {s.step + 1} of {STEPS.length} · {STEPS[s.step]}
          </p>
        </div>
        {s.step > 0 && (
          <Button variant="ghost" size="sm" onClick={reset}>
            Start over
          </Button>
        )}
      </div>

      <ol className="grid grid-cols-6 gap-1.5" aria-label="Progress">
        {STEPS.map((label, i) => (
          <li key={label}>
            <button
              type="button"
              disabled={i > s.step}
              onClick={() => update({ step: i })}
              className="group w-full text-left disabled:cursor-default"
              aria-current={i === s.step ? "step" : undefined}
            >
              <div className={cn("h-1.5 rounded-full", i <= s.step ? "bg-primary" : "bg-secondary")} />
              <span
                className={cn(
                  "mt-1.5 hidden truncate text-xs md:block",
                  i === s.step ? "font-medium text-foreground" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </button>
          </li>
        ))}
      </ol>

      {meta.data && !meta.data.apify_configured && (
        <div className="flex gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <span>
            No Apify key is configured, so searches can't start yet. Add your keys on the{" "}
            <Link to="/keys" className="font-medium text-primary hover:underline">
              API keys
            </Link>{" "}
            page.
          </span>
        </div>
      )}

      {s.step === 0 && <StepResume state={s} update={update} />}
      {s.step === 1 && s.profile && <StepProfile state={s} update={update} />}
      {s.step === 2 && <StepRoles state={s} update={update} roles={meta.data?.roles ?? []} />}
      {s.step === 3 && <StepLocations state={s} update={update} cities={meta.data?.cities ?? []} />}
      {s.step === 4 && <StepOptions state={s} update={update} />}
      {s.step === 5 && <StepKeywords state={s} update={update} onDone={reset} />}

      {s.step < 5 && s.step !== 1 && (
        <div className="flex justify-between gap-2">
          <Button variant="outline" disabled={s.step === 0} onClick={() => update({ step: s.step - 1 })}>
            <ArrowLeft /> Back
          </Button>
          <Button disabled={!canNext} onClick={() => update({ step: s.step + 1 })}>
            Next <ArrowRight />
          </Button>
        </div>
      )}
      {s.step === 5 && (
        <Button variant="outline" onClick={() => update({ step: 4 })}>
          <ArrowLeft /> Back
        </Button>
      )}
    </div>
  );
}

type StepProps = { state: WizardState; update: (p: Partial<WizardState>) => void };

// ------------------------------------------------------------------ 1. resume

function StepResume({ state, update }: StepProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const resumes = useQuery({ queryKey: ["resumes"], queryFn: api.resumes });
  const qc = useQueryClient();

  const upload = useMutation({
    mutationFn: () => api.uploadResumes(files),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["resumes"] });
      update({ resumeId: r.id, profile: r.parsed_profile ?? undefined, step: 1, keywords: undefined, runId: undefined });
      toast.success(`Analysed ${r.filename}`);
    },
  });

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const ok = Array.from(list).filter((f) => /\.(pdf|docx)$/i.test(f.name));
    if (ok.length < list.length) toast.error("Only PDF and DOCX files are supported");
    setFiles((prev) => [...prev, ...ok.filter((f) => !prev.some((p) => p.name === f.name))]);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Upload your resume</CardTitle>
          <CardDescription>
            PDF or DOCX. Upload several (for example a Java and a GenAI version) and they are analysed together.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            role="button"
            tabIndex={0}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              addFiles(e.dataTransfer.files);
            }}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-10 text-center transition-colors",
              dragging ? "border-primary bg-primary/5" : "border-input hover:bg-accent/50",
            )}
          >
            <Upload className="h-6 w-6 text-muted-foreground" />
            <div className="text-sm font-medium">Drop files here or click to choose</div>
            <div className="text-xs text-muted-foreground">Max 10 MB each</div>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".pdf,.docx"
              className="hidden"
              onChange={(e) => addFiles(e.target.files)}
            />
          </div>
          {files.length > 0 && (
            <ul className="space-y-1.5">
              {files.map((f) => (
                <li key={f.name} className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm">
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  <button
                    type="button"
                    className="text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setFiles(files.filter((x) => x !== f))}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
          <ErrorNote error={upload.error} />
          <Button disabled={!files.length || upload.isPending} onClick={() => upload.mutate()} className="w-full sm:w-auto">
            {upload.isPending ? <Loader2 className="animate-spin" /> : <Upload />}
            {upload.isPending ? "Analysing…" : `Upload and analyse${files.length > 1 ? ` ${files.length} resumes` : ""}`}
          </Button>
        </CardContent>
      </Card>

      {!!resumes.data?.length && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Or reuse a previous upload</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {resumes.data.slice(0, 6).map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() =>
                  update({
                    resumeId: r.id,
                    profile: r.parsed_profile ?? undefined,
                    step: 1,
                    keywords: undefined,
                    runId: undefined,
                  })
                }
                className={cn(
                  "flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm hover:bg-accent",
                  state.resumeId === r.id && "border-primary",
                )}
              >
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">{r.filename}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{fmtDateTime(r.created_at)}</span>
              </button>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ 2. profile

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </div>
  );
}

function StepProfile({ state, update }: StepProps) {
  const [p, setP] = useState<Profile>(state.profile!);
  const set = (patch: Partial<Profile>) => setP((prev) => ({ ...prev, ...patch }));
  const save = useMutation({
    mutationFn: () => api.updateProfile(state.resumeId!, p),
    onSuccess: (r) => update({ profile: r.parsed_profile ?? p, step: 2 }),
  });
  const lines = (v: string[]) => v.join("\n");
  const fromLines = (v: string) =>
    v
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review your profile</CardTitle>
        <CardDescription>
          Scoring uses this profile, so correct anything that's wrong.{" "}
          {p.source === "heuristic" && (
            <span className="text-warning">
              This is a keyword-based profile because no ANTHROPIC_API_KEY is configured. Please check it carefully.
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Total years of experience">
            <Input
              type="number"
              step="0.5"
              min={0}
              max={50}
              value={p.total_years_experience}
              onChange={(e) => set({ total_years_experience: Number(e.target.value) })}
            />
          </Field>
          <Field label="Current title">
            <Input value={p.current_title} onChange={(e) => set({ current_title: e.target.value })} />
          </Field>
        </div>
        {p.employers.length > 0 && (
          <Field label="Employers">
            <ul className="space-y-1 text-sm">
              {p.employers.map((e, i) => (
                <li key={i} className="rounded-md bg-muted px-3 py-1.5">
                  <b>{e.title}</b>, {e.name} <span className="text-muted-foreground">({e.start} – {e.end})</span>
                </li>
              ))}
            </ul>
          </Field>
        )}
        <Field label="Skills used professionally" hint="Backed by experience bullets. Weighted fully when matching.">
          <ChipList values={p.skills_professional} onChange={(v) => set({ skills_professional: v })} placeholder="Add skill" />
        </Field>
        <Field label="Skills listed only" hint="Appear only in a skills section. Weighted at 40%.">
          <ChipList
            variant="outline"
            values={p.skills_listed_only}
            onChange={(v) => set({ skills_listed_only: v })}
            placeholder="Add skill"
          />
        </Field>
        <Field label="Measurable achievements" hint="One per line. Used to explain why a job fits.">
          <Textarea
            rows={5}
            value={lines(p.measurable_achievements)}
            onChange={(e) => set({ measurable_achievements: fromLines(e.target.value) })}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Best-fit categories">
            <ChipList values={p.best_fit_categories} onChange={(v) => set({ best_fit_categories: v })} />
          </Field>
          <Field label="Realistic levels">
            <ChipList values={p.realistic_levels} onChange={(v) => set({ realistic_levels: v })} />
          </Field>
          <Field label="Education">
            <Textarea rows={2} value={lines(p.education)} onChange={(e) => set({ education: fromLines(e.target.value) })} />
          </Field>
          <Field label="Certifications">
            <Textarea
              rows={2}
              value={lines(p.certifications)}
              onChange={(e) => set({ certifications: fromLines(e.target.value) })}
            />
          </Field>
        </div>
        <Field label="Gaps">
          <Textarea rows={3} value={lines(p.gaps)} onChange={(e) => set({ gaps: fromLines(e.target.value) })} />
        </Field>
        {p.inconsistencies.length > 0 && (
          <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-sm">
            <div className="mb-1 flex items-center gap-1.5 font-medium">
              <AlertTriangle className="h-4 w-4 text-warning" /> Inconsistencies found
            </div>
            <ul className="list-disc space-y-0.5 pl-5">
              {p.inconsistencies.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}
        <ErrorNote error={save.error} />
        <div className="flex justify-between gap-2">
          <Button variant="outline" onClick={() => update({ step: 0 })}>
            <ArrowLeft /> Back
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending && <Loader2 className="animate-spin" />} Save and continue <ArrowRight />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ 3. roles

function StepRoles({ state, update, roles }: StepProps & { roles: string[] }) {
  useEffect(() => {
    if (state.roles.length === 0 && state.profile) {
      const fit = state.profile.best_fit_categories.filter((c) => roles.includes(c));
      if (fit.length) update({ roles: fit });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles.length]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Target roles</CardTitle>
        <CardDescription>Pick the role categories to search. Keywords are generated from these and your resume.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {roles.map((r) => (
          <ToggleChip key={r} selected={state.roles.includes(r)} onClick={() => update({ roles: toggle(state.roles, r) })}>
            {r}
          </ToggleChip>
        ))}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ 4. locations

const ARRANGEMENTS: { value: RunInput["work_arrangement"]; label: string; hint: string }[] = [
  { value: "any", label: "Any", hint: "Office, hybrid or remote" },
  { value: "office_or_hybrid", label: "Office or hybrid", hint: "Skip remote-only jobs outside your cities" },
  { value: "remote_only", label: "Remote only", hint: "Only jobs marked remote" },
];

function StepLocations({ state, update, cities }: StepProps & { cities: string[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Locations</CardTitle>
        <CardDescription>Jobs outside these cities are filtered out (multi-city listings count if any city matches).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap gap-2">
          {cities.map((c) => (
            <ToggleChip
              key={c}
              selected={state.locations.includes(c)}
              onClick={() => update({ locations: toggle(state.locations, c) })}
            >
              {c}
            </ToggleChip>
          ))}
        </div>
        <label className="flex items-center justify-between gap-4 rounded-md border p-3">
          <span>
            <span className="block text-sm font-medium">Remote (India-eligible)</span>
            <span className="block text-xs text-muted-foreground">Also search remote roles open to candidates in India</span>
          </span>
          <Switch
            checked={state.include_remote_india}
            onCheckedChange={(v) => update({ include_remote_india: v })}
          />
        </label>
        <fieldset className="space-y-2">
          <legend className="mb-2 text-sm font-medium">Work arrangement</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {ARRANGEMENTS.map((a) => (
              <label
                key={a.value}
                className={cn(
                  "cursor-pointer rounded-md border p-3 text-sm",
                  state.work_arrangement === a.value && "border-primary bg-primary/5",
                )}
              >
                <input
                  type="radio"
                  name="arrangement"
                  className="sr-only"
                  checked={state.work_arrangement === a.value}
                  onChange={() => update({ work_arrangement: a.value })}
                />
                <span className="block font-medium">{a.label}</span>
                <span className="block text-xs text-muted-foreground">{a.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ 5. options

function StepOptions({ state, update }: StepProps) {
  const global = useQuery({ queryKey: ["excluded-companies"], queryFn: api.excludedCompanies });
  useEffect(() => {
    if (state.exclude_companies === undefined && global.data) update({ exclude_companies: global.data.companies });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [global.data]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Search options</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label>Platforms</Label>
          <div className="flex flex-wrap gap-2">
            {["linkedin", "naukri", "indeed"].map((p) => (
              <ToggleChip
                key={p}
                selected={state.platforms.includes(p)}
                onClick={() => update({ platforms: toggle(state.platforms, p) })}
              >
                {PLATFORM_LABEL[p]}
              </ToggleChip>
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <Label>Posted within</Label>
          <div className="flex gap-2">
            {([7, 14] as const).map((d) => (
              <ToggleChip key={d} selected={state.posted_within_days === d} onClick={() => update({ posted_within_days: d })}>
                {d} days
              </ToggleChip>
            ))}
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="target">Target number of jobs</Label>
            <Input
              id="target"
              type="number"
              min={1}
              max={1000}
              value={state.target_count}
              onChange={(e) => update({ target_count: Number(e.target.value) || 1 })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="minscore">Minimum match score</Label>
            <Input
              id="minscore"
              type="number"
              min={0}
              max={100}
              value={state.min_score}
              onChange={(e) => update({ min_score: Math.min(100, Math.max(0, Number(e.target.value) || 0)) })}
            />
            <p className="text-xs text-muted-foreground">Jobs below this are dropped. It is never lowered automatically.</p>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Exclude companies</Label>
          <p className="text-xs text-muted-foreground">
            Jobs from these companies are dropped (name contains the text, case-insensitive). Pre-filled from Settings.
          </p>
          <ChipList
            values={state.exclude_companies ?? []}
            onChange={(v) => update({ exclude_companies: v })}
            placeholder="Company name, e.g. Infosys"
          />
        </div>
        <label className="flex items-center justify-between gap-4 rounded-md border p-3">
          <span>
            <span className="block text-sm font-medium">Exclude LinkedIn Easy Apply</span>
            <span className="block text-xs text-muted-foreground">Keep only jobs that apply on the company's own site</span>
          </span>
          <Switch
            checked={state.exclude_linkedin_easy_apply}
            onCheckedChange={(v) => update({ exclude_linkedin_easy_apply: v })}
          />
        </label>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ 6. keywords + estimate

function runInput(s: WizardState): RunInput {
  return {
    resume_id: s.resumeId!,
    roles: s.roles,
    locations: s.locations,
    include_remote_india: s.include_remote_india,
    work_arrangement: s.work_arrangement,
    posted_within_days: s.posted_within_days,
    platforms: s.platforms,
    exclude_linkedin_easy_apply: s.exclude_linkedin_easy_apply,
    target_count: s.target_count,
    min_score: s.min_score,
    keywords: s.keywords,
    exclude_companies: s.exclude_companies ?? [],
  };
}

function StepKeywords({ state, update, onDone }: StepProps & { onDone: () => void }) {
  const navigate = useNavigate();
  const [run, setRun] = useState<Run | null>(null);
  const rolesKey = state.roles.join("|");

  const suggest = useMutation({
    mutationFn: () => api.suggestKeywords(state.resumeId!, state.roles),
    onSuccess: (r) => update({ keywords: r.keywords, keywordRoles: state.roles }),
  });

  useEffect(() => {
    if (!state.keywords || (state.keywordRoles ?? []).join("|") !== rolesKey) suggest.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rolesKey]);

  const estimate = useMutation({
    mutationFn: async () => {
      const body = runInput(state);
      if (state.runId) {
        try {
          return await api.updateRun(state.runId, body);
        } catch {
          /* the draft was started or removed; create a fresh one */
        }
      }
      return api.createRun(body);
    },
    onSuccess: (r) => {
      setRun(r);
      update({ runId: r.id });
    },
  });

  const kwKey = JSON.stringify([state.keywords ?? {}, state.exclude_companies ?? []]);
  useEffect(() => {
    if (!state.keywords) return;
    const t = setTimeout(() => estimate.mutate(), 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kwKey]);

  const start = useMutation({
    mutationFn: () => api.startRun(run!.id),
    onSuccess: (r) => {
      toast.success("Search started");
      onDone();
      navigate(`/runs/${r.id}`);
    },
  });

  const est = run?.estimate;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-2 space-y-0">
          <div>
            <CardTitle>Search keywords</CardTitle>
            <CardDescription>Edit freely. Each keyword runs once per location and platform.</CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => suggest.mutate()} disabled={suggest.isPending}>
            <RefreshCw className={cn(suggest.isPending && "animate-spin")} /> Regenerate
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <ErrorNote error={suggest.error} />
          {Object.entries(state.keywords ?? {}).map(([cat, kws]) => (
            <div key={cat} className="space-y-1.5">
              <Label>{cat}</Label>
              <ChipList
                values={kws}
                onChange={(v) => update({ keywords: { ...state.keywords, [cat]: v } })}
                placeholder="Add keyword"
              />
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Cost estimate {estimate.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </CardTitle>
          <CardDescription>Apify charges per result; the estimate assumes every search returns its full limit.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <ErrorNote error={estimate.error} />
          {est && <EstimateTable est={est} />}
          <ErrorNote error={start.error} />
          <Button
            size="lg"
            className="w-full"
            disabled={!run || !est?.ok || start.isPending || estimate.isPending}
            onClick={() => start.mutate()}
          >
            {start.isPending ? <Loader2 className="animate-spin" /> : <Play />} Start search
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export function EstimateTable({ est }: { est: Estimate }) {
  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 font-medium">Platform</th>
              <th className="py-2 text-right font-medium">Apify runs</th>
              <th className="py-2 text-right font-medium">Max items</th>
              <th className="py-2 text-right font-medium">Est. cost</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {Object.entries(est.platforms ?? {}).map(([p, v]) => (
              <tr key={p} className="border-b">
                <td className="py-2">{PLATFORM_LABEL[p] ?? p}</td>
                <td className="py-2 text-right">{v.runs}</td>
                <td className="py-2 text-right">{v.items.toLocaleString()}</td>
                <td className="py-2 text-right">{usd(v.cost_usd, 3)}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td className="py-2">Apify total</td>
              <td />
              <td className="py-2 text-right">{est.est_items?.toLocaleString()}</td>
              <td className="py-2 text-right">{usd(est.apify_total_usd)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        <Badge variant="outline">Run cap {usd(est.cap_usd)}</Badge>
        {est.spent_usd ? <Badge variant="outline">Already spent {usd(est.spent_usd)}</Badge> : null}
        <Badge variant="outline">
          Apify credit left {est.remaining_credit_usd == null ? "unknown" : usd(est.remaining_credit_usd)}
        </Badge>
        <Badge variant="outline">
          LLM scoring ≈ {usd(est.llm_estimate_usd)} ({est.llm_model})
        </Badge>
      </div>
      {est.credit_check && <p className="text-xs text-muted-foreground">{est.credit_check}</p>}
      {est.note && <p className="text-xs text-muted-foreground">{est.note}</p>}
      {est.reasons?.map((r) => (
        <div key={r} className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {r}
        </div>
      ))}
    </div>
  );
}
