import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, CheckCircle2, FileUp, KeyRound, ListChecks, Loader2, PlugZap, Plus, Power, Trash2, Wallet, XCircle } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import type { ApifyKey, KeyTest, KeyUsage, TestAllResult } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress, Skeleton } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/sheet";
import { cn, fmtDateTime, usd } from "@/lib/utils";

const EVENT_LABEL: Record<KeyUsage["event"], string> = {
  daily_pick: "Picked for the day",
  run: "Used by run",
  failover: "Failed, switched",
  test: "Connection test",
};

function statusBadge(k: ApifyKey) {
  if (!k.active) return <Badge variant="outline">Disabled</Badge>;
  if (k.exhausted_today) return <Badge variant="destructive">Failed today</Badge>;
  if (k.is_today) return <Badge variant="success">Today's key</Badge>;
  return <Badge variant="secondary">Active</Badge>;
}

function AddKey() {
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [label, setLabel] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const done = () => {
    qc.invalidateQueries({ queryKey: ["keys"] });
    qc.invalidateQueries({ queryKey: ["meta"] });
  };
  const add = useMutation({
    mutationFn: () => api.addKey(token.trim(), label.trim()),
    onSuccess: (k) => {
      toast.success(`Added ${k.label}`);
      setToken("");
      setLabel("");
      done();
    },
  });
  const imp = useMutation({
    mutationFn: (f: File) => api.importKeys(f),
    onSuccess: (r) => {
      toast.success(`Imported ${r.added} of ${r.found} keys${r.duplicates ? ` (${r.duplicates} already in the pool)` : ""}`);
      done();
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Add keys</CardTitle>
        <CardDescription>
          Keys are encrypted in the database and never shown again; only the last four characters are displayed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <form
          className="grid gap-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="key-label">Label</Label>
            <Input id="key-label" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Account 7" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-token">API token</Label>
            <Input
              id="key-token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="apify_api_…"
            />
          </div>
          <Button type="submit" disabled={!token.trim() || add.isPending}>
            {add.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Add key
          </Button>
        </form>
        <ErrorNote error={add.error} />

        <div className="flex flex-col gap-3 rounded-md border border-dashed p-4 sm:flex-row sm:items-center">
          <div className="flex-1 text-sm">
            <div className="font-medium">Import from Excel or CSV</div>
            <div className="text-muted-foreground">
              Every cell containing an <code className="text-xs">apify_api_…</code> token is imported. Another text cell in
              the same row (such as an account name) becomes the label. Duplicates are skipped.
            </div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xlsm,.csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) imp.mutate(f);
              e.target.value = "";
            }}
          />
          <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={imp.isPending}>
            {imp.isPending ? <Loader2 className="animate-spin" /> : <FileUp />} Choose file
          </Button>
        </div>
        <ErrorNote error={imp.error} />
        {imp.data && (
          <p className="text-sm text-muted-foreground">
            Found {imp.data.found}, added {imp.data.added}, skipped {imp.data.duplicates} duplicates.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function KeyUsageLine({ k }: { k: ApifyKey }) {
  if (!k.usage_checked_at) {
    return <div className="mt-1 text-xs text-muted-foreground">Usage not checked yet. Click Test.</div>;
  }
  if (k.monthly_limit_usd == null) {
    return <div className="mt-1 text-xs text-muted-foreground">Last test failed {fmtDateTime(k.usage_checked_at)}</div>;
  }
  const used = k.monthly_usage_usd ?? 0;
  const pct = k.monthly_limit_usd ? (used / k.monthly_limit_usd) * 100 : 0;
  return (
    <div className="mt-1.5 max-w-md space-y-1">
      <Progress
        value={pct}
        className="h-1.5"
        indicatorClassName={pct >= 90 ? "bg-destructive" : pct >= 70 ? "bg-warning" : "bg-success"}
      />
      <div className="text-xs text-muted-foreground tabular">
        {k.account && <span className="text-foreground">{k.account}</span>} · {usd(used)} used of{" "}
        {usd(k.monthly_limit_usd)} this month · <span className="text-foreground">{usd(k.remaining_usd)} left</span>
        {k.spent_by_jobradar_usd > 0 && <> · JobRadar spent {usd(k.spent_by_jobradar_usd, 3)}</>} · checked{" "}
        {fmtDateTime(k.usage_checked_at)}
      </div>
    </div>
  );
}

function TestAllPanel({ result, onClose }: { result: TestAllResult; onClose: () => void }) {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2 space-y-0 pb-3">
        <div className="min-w-0">
          <CardTitle className="text-base">Test results</CardTitle>
          <CardDescription>
            {result.ok} of {result.tested} keys working · {usd(result.remaining_usd)} credit left across working keys
          </CardDescription>
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Close
        </Button>
      </CardHeader>
      <CardContent>
        <ul className="space-y-1.5 text-sm">
          {result.results.map((r) => (
            <li key={r.key_id} className="flex items-start gap-2">
              {r.connected ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              ) : (
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
              )}
              <span className="min-w-0">
                <b>{r.label}</b> <span className="font-mono text-xs text-muted-foreground">{r.masked}</span>
                <span className={cn("block break-words text-xs", r.connected ? "text-muted-foreground" : "text-destructive")}>
                  {r.detail.replace(/^(OK|FAILED): /, "")}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function KeyRow({ k, onTest }: { k: ApifyKey; onTest: (r: KeyTest) => void }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["keys"] });
    qc.invalidateQueries({ queryKey: ["key-usage"] });
  };
  const toggle = useMutation({ mutationFn: () => api.updateKey(k.id, { active: !k.active }), onSuccess: refresh });
  const del = useMutation({
    mutationFn: () => api.deleteKey(k.id),
    onSuccess: () => {
      toast.success(`Deleted ${k.label}`);
      setConfirm(false);
      refresh();
    },
  });
  const test = useMutation({
    mutationFn: () => api.testKey(k.id),
    onSuccess: (r) => {
      onTest(r);
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <li className="flex flex-col gap-2 border-b px-4 py-3 last:border-0 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{k.label}</span>
          {statusBadge(k)}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          <span className="font-mono">{k.masked}</span> · last used {k.last_used_on ?? "never"} · {k.uses} run
          {k.uses === 1 ? "" : "s"}
        </div>
        <KeyUsageLine k={k} />
        {k.last_error && (k.exhausted_today || !k.monthly_limit_usd) && (
          <div className="mt-1 break-words text-xs text-destructive">{k.last_error}</div>
        )}
      </div>
      <div className="flex shrink-0 gap-1.5">
        <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
          {test.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />} Test
        </Button>
        <Button size="sm" variant="outline" onClick={() => toggle.mutate()} disabled={toggle.isPending}>
          <Power /> {k.active ? "Disable" : "Enable"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setConfirm(true)} aria-label={`Delete ${k.label}`}>
          <Trash2 />
        </Button>
      </div>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogTitle className="text-lg font-semibold">Delete {k.label}?</DialogTitle>
          <DialogDescription className="text-sm text-muted-foreground">
            The key is removed from the pool permanently. Its usage history is kept. Apify runs it started that are still
            unfinished can no longer be read, so delete keys only when no search is running.
          </DialogDescription>
          <ErrorNote error={del.error} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => del.mutate()} disabled={del.isPending}>
              {del.isPending && <Loader2 className="animate-spin" />} Delete key
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </li>
  );
}

function parseUsageDetail(detail?: string | null) {
  if (!detail) return { usageText: null, structuredUsage: null, detailsText: "—" };

  const segments = detail.split(/\s*·\s*/);
  const usageSegments: string[] = [];
  const otherSegments: string[] = [];

  for (const seg of segments) {
    if (/\$\d+(\.\d+)?\s*(used|left|remaining)/i.test(seg) || /used of \$/i.test(seg)) {
      usageSegments.push(seg.trim());
    } else {
      otherSegments.push(seg.trim());
    }
  }

  let structuredUsage: { used: string; limit: string; left?: string } | null = null;
  const match = detail.match(/\$(\d+(?:\.\d+)?)\s+used\s+of\s+\$(\d+(?:\.\d+)?)(?:.*?\$(\d+(?:\.\d+)?)\s+left)?/i);
  if (match) {
    structuredUsage = {
      used: match[1],
      limit: match[2],
      left: match[3],
    };
  }

  return {
    usageText: usageSegments.length > 0 ? usageSegments.join(" · ") : null,
    structuredUsage,
    detailsText: otherSegments.join(" · ") || (usageSegments.length ? "OK" : detail),
  };
}

export function ApiKeys() {
  const pool = useQuery({ queryKey: ["keys"], queryFn: api.keys });
  const usage = useQuery({ queryKey: ["key-usage"], queryFn: () => api.keyUsage(200) });
  const [tested, setTested] = useState<KeyTest | null>(null);
  const [allResult, setAllResult] = useState<TestAllResult | null>(null);
  const qc = useQueryClient();
  const testAll = useMutation({
    mutationFn: api.testAllKeys,
    onSuccess: (r) => {
      setAllResult(r);
      setTested(null);
      qc.invalidateQueries({ queryKey: ["keys"] });
      qc.invalidateQueries({ queryKey: ["key-usage"] });
      if (r.failed) toast.warning(`${r.ok} of ${r.tested} keys working, ${r.failed} failed`);
      else toast.success(`All ${r.tested} keys working`);
    },
    onError: (e) => toast.error(e.message),
  });

  if (pool.isLoading) return <Skeleton className="h-96 w-full" />;
  const p = pool.data;
  const todayKey = p?.keys.find((k) => k.id === p.today_key_id);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Apify API keys</h1>
          <p className="text-sm text-muted-foreground">
            One key is used per day ({p?.timezone}), rotating to the least recently used key. If a key is invalid or out of
            credit, the next one takes over automatically.
          </p>
        </div>
        <Button onClick={() => testAll.mutate()} disabled={!p?.keys.length || testAll.isPending}>
          {testAll.isPending ? <Loader2 className="animate-spin" /> : <ListChecks />}
          {testAll.isPending ? "Testing…" : "Test all keys"}
        </Button>
      </div>
      <ErrorNote error={pool.error} />

      {p && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="sm:col-span-2">
            <CardContent className="flex items-start gap-3 pt-4 sm:pt-6">
              <CalendarCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div className="min-w-0 text-sm">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Key for {p.today}</div>
                {todayKey ? (
                  <div className="font-medium">
                    {todayKey.label} <span className="font-mono text-muted-foreground">{todayKey.masked}</span>
                  </div>
                ) : p.keys.length ? (
                  <div className="text-muted-foreground">Picked when today's first search starts.</div>
                ) : p.env_fallback ? (
                  <div className="text-muted-foreground">Pool is empty: APIFY_TOKEN from .env is used.</div>
                ) : (
                  <div className="text-destructive">No keys yet. Add or import keys below.</div>
                )}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-start gap-3 pt-4 sm:pt-6">
              <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div className="text-sm">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Usable today</div>
                <div className="font-medium tabular">
                  {p.usable_today} of {p.keys.length}
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex items-start gap-3 pt-4 sm:pt-6">
              <Wallet className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
              <div className="text-sm">
                <div className="text-xs uppercase tracking-wide text-muted-foreground">Credit left</div>
                {p.totals.checked_keys ? (
                  <>
                    <div className="font-medium tabular">
                      {usd(p.totals.remaining_usd)} <span className="text-muted-foreground">of {usd(p.totals.monthly_limit_usd)}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {p.totals.checked_keys} checked · {fmtDateTime(p.totals.last_checked_at)}
                    </div>
                  </>
                ) : (
                  <div className="text-muted-foreground">Run "Test all keys"</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {allResult && <TestAllPanel result={allResult} onClose={() => setAllResult(null)} />}

      {tested && (
        <div
          className={`rounded-md border px-3 py-2 text-sm ${tested.connected ? "border-success/40 bg-success/10" : "border-destructive/40 bg-destructive/10 text-destructive"}`}
        >
          <b>{tested.label}</b>: {tested.detail.replace(/^(OK|FAILED): /, "")}
        </div>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Keys ({p?.keys.length ?? 0})</CardTitle>
        </CardHeader>
        <ul>
          {p?.keys.map((k) => <KeyRow key={k.id} k={k} onTest={setTested} />)}
          {!p?.keys.length && <li className="px-4 pb-4 text-sm text-muted-foreground">No keys in the pool.</li>}
        </ul>
      </Card>

      <AddKey />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Usage log</CardTitle>
          <CardDescription>Which key was picked or used, and when.</CardDescription>
        </CardHeader>
        <CardContent>
          <ErrorNote error={usage.error} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2.5 pr-3 font-medium">When</th>
                  <th className="py-2.5 pr-3 font-medium">Key</th>
                  <th className="py-2.5 pr-3 font-medium">Event</th>
                  <th className="py-2.5 pr-3 font-medium">Usage</th>
                  <th className="py-2.5 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {usage.data?.map((u) => {
                  const parsed = parseUsageDetail(u.detail);
                  return (
                    <tr key={u.id} className="border-b align-top last:border-0 hover:bg-muted/20 transition-colors">
                      <td className="whitespace-nowrap py-2.5 pr-3 tabular text-xs text-muted-foreground">{fmtDateTime(u.at)}</td>
                      <td className="whitespace-nowrap py-2.5 pr-3 font-medium text-foreground">{u.key_label}</td>
                      <td className="whitespace-nowrap py-2.5 pr-3">
                        <Badge variant={u.event === "failover" ? "destructive" : u.event === "run" ? "secondary" : "outline"}>
                          {EVENT_LABEL[u.event] ?? u.event}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap py-2.5 pr-3 text-xs">
                        {parsed.structuredUsage ? (
                          <div className="flex flex-col font-mono leading-tight">
                            <span>
                              <span className="font-semibold text-foreground">${parsed.structuredUsage.used}</span>
                              <span className="text-muted-foreground"> / ${parsed.structuredUsage.limit}</span>
                            </span>
                            {parsed.structuredUsage.left !== undefined && (
                              <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                                ${parsed.structuredUsage.left} left
                              </span>
                            )}
                          </div>
                        ) : parsed.usageText ? (
                          <span className="font-mono text-xs font-medium text-foreground">{parsed.usageText}</span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td
                        className={cn(
                          "min-w-[12rem] py-2.5 text-xs",
                          u.detail?.includes("FAILED") ? "text-destructive font-medium" : "text-muted-foreground",
                        )}
                      >
                        {u.run_id && (
                          <Link to={`/runs/${u.run_id}`} className="mr-1 text-primary hover:underline font-medium">
                            Run #{u.run_id}
                          </Link>
                        )}
                        <span className="break-words">{parsed.detailsText}</span>
                      </td>
                    </tr>
                  );
                })}
                {!usage.data?.length && (
                  <tr>
                    <td colSpan={5} className="py-4 text-center text-muted-foreground">
                      Nothing yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
