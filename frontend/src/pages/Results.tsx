import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Ban,
  BookmarkCheck,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Search,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import type { JobRow } from "@/api/types";
import { AuditPanel } from "@/components/AuditPanel";
import { CategoryBadge, ErrorNote, PlatformBadge, ScoreBadge, VerificationBadge } from "@/components/common";
import { ExpandCard } from "@/components/ExpandDialog";
import { JobDrawer } from "@/components/JobDrawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, fmtDate, PLATFORM_LABEL } from "@/lib/utils";
import { statusBadge } from "@/pages/RunProgress";

const STATUS_OPTIONS = [
  ["final", "Ranked (final)"],
  ["verified_active", "Verified active"],
  ["uncertain", "Uncertain"],
  ["inactive", "Closed / inactive"],
  ["unverified", "Not verified"],
  ["filtered", "Filtered out"],
  ["duplicates", "Duplicates"],
  ["shortlisted", "Shortlisted"],
  ["applied", "Applied"],
  ["rejected", "Rejected"],
  ["all", "All listings"],
] as const;

const TIERS = [
  "Tier 1 – Global tech product",
  "Tier 1 – Global enterprise / bank (India GCC)",
  "Tier 2 – Established product / SaaS company",
  "Tier 2 – Funded startup / scale-up",
  "Tier 3 – Small or early-stage company",
  "IT services / consulting",
];

const SORT_PARAM: Record<string, [string, string]> = {
  score: ["score", "-score"],
  posted_date: ["posted", "-posted"],
  title: ["title", "title"],
  company: ["company", "company"],
};

const col = createColumnHelper<JobRow>();

function StateIcon({ state }: { state: JobRow["user_state"] }) {
  if (state === "shortlisted") return <BookmarkCheck className="h-4 w-4 text-primary" aria-label="Shortlisted" />;
  if (state === "applied") return <CheckCheck className="h-4 w-4 text-success" aria-label="Applied" />;
  if (state === "rejected") return <Ban className="h-4 w-4 text-muted-foreground" aria-label="Rejected" />;
  return null;
}

function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function Results() {
  const runId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "jobs";
  const [status, setStatus] = useState("final");
  const [platform, setPlatform] = useState("");
  const [tier, setTier] = useState("");
  const [city, setCity] = useState("");
  const [category, setCategory] = useState("");
  const [minScore, setMinScore] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  const [openJob, setOpenJob] = useState<number | null>(null);
  const pageSize = 25;
  const dq = useDebounced(q);

  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const sort = sorting[0] ? SORT_PARAM[sorting[0].id]?.[sorting[0].desc ? 0 : 1] : "score";
  const filters = { status, platform, tier, city, category, min_score: minScore, q: dq, sort };

  useEffect(() => setPage(1), [status, platform, tier, city, category, minScore, dq, sort]);

  const jobs = useQuery({
    queryKey: ["jobs", runId, filters, page],
    queryFn: () => api.jobs(runId, { ...filters, page, page_size: pageSize }),
    placeholderData: keepPreviousData,
  });

  const columns = useMemo(
    () => [
      col.accessor("score", {
        header: "Score",
        cell: (c) => <ScoreBadge score={c.getValue()} />,
      }),
      col.accessor("title", {
        header: "Job",
        cell: ({ row: { original: j } }) => (
          <div className="min-w-0 max-w-[22rem]">
            <div className="flex items-center gap-1.5">
              <span className="truncate font-medium">{j.title}</span>
              <StateIcon state={j.user_state} />
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {j.company}
              <span className="sm:hidden"> · {PLATFORM_LABEL[j.platform]}</span>
              <span className="md:hidden"> · {j.city === "Remote-India" ? "Remote" : j.city}</span>
            </div>
            {status !== "final" && (
              <div className="mt-1 flex flex-wrap gap-1">
                {j.filter_reason && (
                  <Badge variant="outline" className="font-normal">
                    {j.filter_reason.replace(/_/g, " ")}
                  </Badge>
                )}
                {j.verification_status && <VerificationBadge status={j.verification_status} easyApply={j.easy_apply} />}
              </div>
            )}
          </div>
        ),
      }),
      col.accessor("platform", {
        header: "Platform",
        enableSorting: false,
        cell: (c) => (
          <div className="flex flex-col gap-0.5">
            <PlatformBadge platform={c.getValue()} />
            {c.row.original.alt_sources.length > 0 && (
              <span className="text-xs text-muted-foreground">+{c.row.original.alt_sources.length} more</span>
            )}
          </div>
        ),
      }),
      col.accessor("company_tier", {
        header: "Tier",
        enableSorting: false,
        cell: (c) => <span className="line-clamp-2 text-xs">{c.getValue() ?? "—"}</span>,
      }),
      col.accessor("city", {
        header: "City",
        enableSorting: false,
        cell: (c) => (c.getValue() === "Remote-India" ? "Remote" : c.getValue() ?? "—"),
      }),
      col.accessor("posted_date", { header: "Posted", cell: (c) => <span className="tabular">{fmtDate(c.getValue())}</span> }),
      col.accessor("category", { header: "Category", enableSorting: false, cell: (c) => <CategoryBadge category={c.getValue()} /> }),
    ],
    [status],
  );

  const responsive: Record<string, string> = {
    platform: "hidden sm:table-cell",
    company_tier: "hidden lg:table-cell",
    city: "hidden md:table-cell",
    posted_date: "hidden sm:table-cell",
    category: "hidden md:table-cell",
  };

  const table = useReactTable({
    data: jobs.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    state: { sorting },
    onSortingChange: setSorting,
    enableSortingRemoval: false,
  });

  if (run.isLoading) return <Skeleton className="h-96 w-full" />;
  if (run.error || !run.data) return <ErrorNote error={run.error ?? "Run not found"} />;
  const r = run.data;
  const total = jobs.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Results · Run #{r.id}</h1>
            {statusBadge(r.status)}
            {r.estimate?.demo && <Badge variant="outline">Demo data</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {r.final_count ?? 0} ranked jobs (target {r.target_count}, min score {r.min_score}) ·{" "}
            <Link to={`/runs/${r.id}`} className="text-primary hover:underline">
              run details
            </Link>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <a href={api.exportUrl(r.id, false)} download>
              <Download /> Excel
            </a>
          </Button>
          <Button asChild variant="outline">
            <a href={api.exportUrl(r.id, true)} download>
              <FileSpreadsheet /> Full report
            </a>
          </Button>
        </div>
      </div>

      <ExpandCard run={r} />

      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <TabsList>
          <TabsTrigger value="jobs">Jobs</TabsTrigger>
          <TabsTrigger value="audit">Audit</TabsTrigger>
        </TabsList>

        <TabsContent value="jobs" className="space-y-3">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
            <div className="relative col-span-2 xl:col-span-2">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search title, company, skills…"
                className="pl-9"
                aria-label="Search jobs"
              />
            </div>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
              {STATUS_OPTIONS.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
            <Select value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="Platform">
              <option value="">All platforms</option>
              {r.platforms.map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABEL[p]}
                </option>
              ))}
            </Select>
            <Select value={tier} onChange={(e) => setTier(e.target.value)} aria-label="Company tier">
              <option value="">All tiers</option>
              {TIERS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
            <Select value={city} onChange={(e) => setCity(e.target.value)} aria-label="City">
              <option value="">All cities</option>
              {[...r.locations, ...(r.include_remote_india ? ["Remote-India"] : [])].map((c) => (
                <option key={c} value={c}>
                  {c === "Remote-India" ? "Remote (India)" : c}
                </option>
              ))}
            </Select>
            <div className="col-span-2 flex gap-2 md:col-span-1">
              <Select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
                <option value="">Any category</option>
                <option value="safe">Safe</option>
                <option value="strong">Strong</option>
                <option value="stretch">Stretch</option>
              </Select>
              <Input
                type="number"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(e.target.value)}
                placeholder="Min"
                aria-label="Minimum score"
                className="w-20 shrink-0"
              />
            </div>
          </div>

          <ErrorNote error={jobs.error} />
          <div className="overflow-hidden rounded-lg border">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/60">
                  {table.getHeaderGroups().map((hg) => (
                    <tr key={hg.id}>
                      {hg.headers.map((h) => {
                        const sorted = h.column.getIsSorted();
                        const SortIcon = sorted === "desc" ? ArrowDown : sorted === "asc" ? ArrowUp : ArrowUpDown;
                        return (
                          <th
                            key={h.id}
                            className={cn("px-3 py-2.5 text-left text-xs font-medium text-muted-foreground", responsive[h.id])}
                          >
                            {h.column.getCanSort() ? (
                              <button
                                type="button"
                                onClick={h.column.getToggleSortingHandler()}
                                className="inline-flex items-center gap-1 hover:text-foreground"
                              >
                                {flexRender(h.column.columnDef.header, h.getContext())}
                                <SortIcon className={cn("h-3.5 w-3.5", !sorted && "opacity-40")} />
                              </button>
                            ) : (
                              flexRender(h.column.columnDef.header, h.getContext())
                            )}
                          </th>
                        );
                      })}
                    </tr>
                  ))}
                </thead>
                <tbody className={cn(jobs.isFetching && "opacity-70")}>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      tabIndex={0}
                      onClick={() => setOpenJob(row.original.id)}
                      onKeyDown={(e) => e.key === "Enter" && setOpenJob(row.original.id)}
                      className={cn(
                        "cursor-pointer border-t transition-colors hover:bg-accent/60 focus-visible:bg-accent focus-visible:outline-none",
                        row.original.user_state === "rejected" && "opacity-60",
                      )}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className={cn("px-3 py-2.5 align-top", responsive[cell.column.id])}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {!jobs.isLoading && total === 0 && (
                    <tr>
                      <td colSpan={7} className="px-3 py-10 text-center text-muted-foreground">
                        No jobs match these filters.
                      </td>
                    </tr>
                  )}
                  {jobs.isLoading && (
                    <tr>
                      <td colSpan={7} className="p-3">
                        <Skeleton className="h-40 w-full" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex items-center justify-between gap-2 text-sm">
            <span className="text-muted-foreground tabular">
              {total ? `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}` : "0 jobs"}
            </span>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="icon" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">
                <ChevronLeft />
              </Button>
              <span className="px-2 tabular">
                {page}/{pages}
              </span>
              <Button variant="outline" size="icon" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page">
                <ChevronRight />
              </Button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Score colours: <span className="font-medium text-success">85+</span> ·{" "}
            <span className="font-medium text-primary">75–84</span> · <span className="font-medium text-warning">65–74</span>
          </p>
        </TabsContent>

        <TabsContent value="audit">
          <AuditPanel run={r} />
        </TabsContent>
      </Tabs>

      <JobDrawer jobId={openJob} runId={runId} onClose={() => setOpenJob(null)} />
    </div>
  );
}
