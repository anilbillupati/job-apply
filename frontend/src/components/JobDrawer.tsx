import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Bookmark, BookmarkCheck, Building2, CheckCheck, ExternalLink, Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { JobDetail, JobRow } from "@/api/types";
import { CategoryBadge, ErrorNote, PlatformBadge, ScoreBadge, VerificationBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { cn, expRange, fmtDate, fmtDateTime, PLATFORM_LABEL } from "@/lib/utils";

const RUBRIC: { key: string; label: string; max: number }[] = [
  { key: "technical_skills", label: "Technical skills", max: 30 },
  { key: "experience_seniority", label: "Experience / seniority", max: 20 },
  { key: "role_domain", label: "Role / domain", max: 15 },
  { key: "projects_achievements", label: "Projects / achievements", max: 15 },
  { key: "location", label: "Location", max: 10 },
  { key: "education_mandatory", label: "Education / mandatory", max: 5 },
  { key: "career_growth", label: "Career growth", max: 5 },
];

export function applyLink(j: JobRow) {
  return j.platform === "indeed" ? j.employer_url || j.listing_url : j.listing_url;
}

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("space-y-2", className)}>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
      {children}
    </section>
  );
}

function Breakdown({ breakdown }: { breakdown: Record<string, number> }) {
  return (
    <div className="space-y-2" role="list" aria-label="Score breakdown">
      {RUBRIC.map(({ key, label, max }) => {
        const v = breakdown[key] ?? 0;
        const pct = (v / max) * 100;
        return (
          <div key={key} role="listitem" className="grid grid-cols-[minmax(0,9.5rem)_1fr_3rem] items-center gap-2 text-sm">
            <span className="truncate text-muted-foreground" title={label}>
              {label}
            </span>
            <div className="h-2.5 overflow-hidden rounded-full bg-secondary">
              <div
                className={cn("h-full rounded-full", pct >= 80 ? "bg-success" : pct >= 55 ? "bg-primary" : "bg-warning")}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-right tabular">
              {v}
              <span className="text-muted-foreground">/{max}</span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

function SkillsMatch({ text }: { text: string }) {
  const parts = text
    .split(/;|\n/)
    .map((s) => s.trim())
    .filter(Boolean);
  return (
    <div className="flex flex-wrap gap-1.5">
      {parts.map((p) => {
        const gap = /^gap:/i.test(p);
        return (
          <Badge key={p} variant={gap ? "warning" : "success"} className="font-normal">
            {p}
          </Badge>
        );
      })}
    </div>
  );
}

function Evidence({ v }: { v: NonNullable<JobDetail["verification"]> }) {
  const ev = v.evidence as Record<string, unknown>;
  const matched = (ev.matched as string[] | undefined) ?? [];
  const rows: [string, unknown][] = [
    ["Method", v.method],
    ["Checked", fmtDateTime(v.checked_at)],
    ["HTTP status", ev.http_status],
    ["Matched text", matched.length ? matched.map((m) => `"${m}"`).join(", ") : undefined],
    ["Reason", ev.reason],
    ["Posted", ev.posted_time_ago ?? ev.posted],
    ["Applicants", ev.applicants],
    ["Fixture", ev.fixture],
  ];
  const url = (ev.final_url ?? ev.url) as string | undefined;
  return (
    <div className="space-y-2 rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <VerificationBadge status={v.status} easyApply={v.easy_apply} />
        {v.easy_apply === false && <Badge variant="outline">Applies on company site</Badge>}
      </div>
      <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1">
        {rows
          .filter(([, val]) => val != null && val !== "")
          .map(([k, val]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="min-w-0 break-words">{String(val)}</dd>
            </div>
          ))}
        {url && (
          <div className="contents">
            <dt className="text-muted-foreground">URL</dt>
            <dd className="min-w-0 break-all">
              <a href={url} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                {url}
              </a>
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

export function JobDrawer({ jobId, runId, onClose }: { jobId: number | null; runId: number; onClose: () => void }) {
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ["job", jobId], queryFn: () => api.job(jobId!), enabled: jobId != null });
  const [note, setNote] = useState("");
  const [showFull, setShowFull] = useState(false);

  useEffect(() => {
    setNote(job.data?.user_note ?? "");
    setShowFull(false);
  }, [job.data?.id, job.data?.user_note]);

  const patch = useMutation({
    mutationFn: (body: { user_state?: JobRow["user_state"]; user_note?: string | null }) => api.patchJob(jobId!, body),
    onSuccess: (row, body) => {
      qc.setQueryData<JobDetail>(["job", jobId], (old) => (old ? { ...old, ...row } : old));
      qc.invalidateQueries({ queryKey: ["jobs", runId] });
      toast.success(body.user_note !== undefined ? "Note saved" : `Marked ${row.user_state ?? "unset"}`);
    },
  });

  const exclude = useMutation({
    mutationFn: (company: string) => api.excludeCompany(company),
    onSuccess: (_r, company) => {
      qc.invalidateQueries({ queryKey: ["excluded-companies"] });
      toast.success(`${company} will be excluded from future searches`);
    },
    onError: (e) => toast.error(e.message),
  });

  const setState = (s: NonNullable<JobRow["user_state"]>) =>
    patch.mutate({ user_state: job.data?.user_state === s ? null : s });

  const j = job.data;
  const sd = j?.score_detail;
  const link = j ? applyLink(j) : null;
  const desc = j?.description ?? "";

  return (
    <Sheet open={jobId != null} onOpenChange={(o) => !o && onClose()}>
      <SheetContent aria-describedby={undefined}>
        {!j ? (
          <div className="space-y-3 p-6">
            <SheetTitle className="sr-only">Loading job</SheetTitle>
            {job.error ? <ErrorNote error={job.error} /> : <Skeleton className="h-40 w-full" />}
          </div>
        ) : (
          <>
            <div className="border-b p-4 pr-12 sm:p-6 sm:pr-14">
              <div className="flex items-start gap-3">
                <ScoreBadge score={j.score} className="mt-0.5 text-base" />
                <div className="min-w-0">
                  <SheetTitle className="text-lg font-semibold leading-snug">{j.title}</SheetTitle>
                  <SheetDescription className="text-sm text-muted-foreground">
                    {j.company} · {j.city === "Remote-India" ? "Remote (India)" : j.city ?? j.location_text}
                    {j.work_mode !== "unknown" && j.city !== "Remote-India" ? ` · ${j.work_mode}` : ""}
                  </SheetDescription>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <PlatformBadge platform={j.platform} />
                    <CategoryBadge category={j.category} />
                    {j.company_tier && <Badge variant="outline">{j.company_tier}</Badge>}
                  </div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {link && (
                  <Button asChild size="sm">
                    <a href={link} target="_blank" rel="noreferrer">
                      <ExternalLink /> Apply
                    </a>
                  </Button>
                )}
                <Button size="sm" variant={j.user_state === "shortlisted" ? "secondary" : "outline"} onClick={() => setState("shortlisted")}>
                  {j.user_state === "shortlisted" ? <BookmarkCheck /> : <Bookmark />} Shortlist
                </Button>
                <Button size="sm" variant={j.user_state === "applied" ? "secondary" : "outline"} onClick={() => setState("applied")}>
                  <CheckCheck /> {j.user_state === "applied" ? "Applied" : "Mark applied"}
                </Button>
                <Button size="sm" variant={j.user_state === "rejected" ? "secondary" : "outline"} onClick={() => setState("rejected")}>
                  <Ban /> {j.user_state === "rejected" ? "Rejected" : "Reject"}
                </Button>
                {j.company && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => exclude.mutate(j.company)}
                    disabled={exclude.isPending}
                    title="Skip this company in future searches"
                  >
                    <Building2 /> Exclude company
                  </Button>
                )}
              </div>
            </div>

            <div className="flex-1 space-y-6 overflow-y-auto p-4 sm:p-6">
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                {[
                  ["Posted", fmtDate(j.posted_date)],
                  ["Experience", expRange(j.exp_min, j.exp_max)],
                  ["Salary", j.salary_text || "Not stated"],
                  ["Applicants", j.applicants_text || "Not stated"],
                ].map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-xs text-muted-foreground">{k}</dt>
                    <dd className="font-medium">{v}</dd>
                  </div>
                ))}
              </dl>

              {sd ? (
                <>
                  <Section title={`Score breakdown · ${sd.total}/100 · ${sd.model}`}>
                    <Breakdown breakdown={sd.breakdown} />
                  </Section>
                  <Section title="Why this fits">
                    <p className="text-sm">{sd.why_fits}</p>
                  </Section>
                  <Section title="Experience match">
                    <p className="text-sm">{sd.experience_summary}</p>
                  </Section>
                  <Section title="Key skills">
                    <SkillsMatch text={sd.key_skills_match} />
                  </Section>
                  {sd.notes && sd.notes.toLowerCase() !== "none" && (
                    <Section title="Notes and concerns">
                      <p className="whitespace-pre-line text-sm">{sd.notes}</p>
                    </Section>
                  )}
                </>
              ) : (
                <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
                  Not scored{j.filter_reason ? ` (filtered: ${j.filter_reason.replace(/_/g, " ")})` : ""}
                  {j.duplicate_of ? " (duplicate of another listing)" : ""}. Pre-score: {j.prescore ?? "—"}
                </p>
              )}

              <Section title="Verification">
                {j.verification ? (
                  <Evidence v={j.verification} />
                ) : (
                  <p className="text-sm text-muted-foreground">Not verified (only jobs that pass the filters with a pre-score of 60+ are checked).</p>
                )}
              </Section>

              {(j.alt_sources.length > 0 || j.duplicates.length > 0) && (
                <Section title="Also listed on">
                  <ul className="space-y-1.5 text-sm">
                    {j.alt_sources.map((a, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <PlatformBadge platform={a.platform} />
                        {a.url && (
                          <a href={a.url} target="_blank" rel="noreferrer" className="min-w-0 truncate text-primary hover:underline">
                            {a.url}
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              <Section title="Your note">
                <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Recruiter name, referral, follow-up date…" />
                <Button
                  size="sm"
                  variant="outline"
                  disabled={patch.isPending || note === (j.user_note ?? "")}
                  onClick={() => patch.mutate({ user_note: note || null })}
                >
                  {patch.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save note
                </Button>
              </Section>

              <Section title={`Description · ${PLATFORM_LABEL[j.platform]}`}>
                <div className={cn("whitespace-pre-line text-sm leading-relaxed", !showFull && "line-clamp-[18]")}>{desc}</div>
                {desc.length > 1200 && (
                  <Button variant="link" size="sm" className="h-auto px-0" onClick={() => setShowFull(!showFull)}>
                    {showFull ? "Show less" : "Show full description"}
                  </Button>
                )}
              </Section>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
