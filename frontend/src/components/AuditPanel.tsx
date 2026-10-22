import type { Run } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PLATFORM_LABEL, usd } from "@/lib/utils";

const REASON_LABEL: Record<string, string> = {
  location: "Location not in scope",
  work_arrangement: "Work arrangement mismatch",
  agency: "Agency / staffing / marketplace",
  seniority: "Title seniority",
  irrelevant_title: "Irrelevant title",
  exp_too_high: "Minimum experience too high",
  exp_too_low: "Maximum experience below 2 years",
};

function FunnelRow({ label, value, max, children }: { label: string; value: number; max: number; children?: React.ReactNode }) {
  const pct = max ? Math.max(2, (value / max) * 100) : 0;
  return (
    <li className="space-y-1">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular">{value.toLocaleString()}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </div>
      {children && <div className="flex flex-wrap gap-1.5 pt-1 text-xs">{children}</div>}
    </li>
  );
}

export function AuditPanel({ run }: { run: Run }) {
  const p = run.progress ?? {};
  const c = p.counts ?? {};
  const v = c.verified ?? {};
  const max = c.collected ?? 0;
  const filteredTotal = Object.values(c.filtered ?? {}).reduce((a, b) => a + b, 0);
  const verifiedTotal = Object.values(v).reduce((a, b) => a + b, 0);
  const costs = p.cost?.apify ?? {};
  const tasks = run.tasks ?? [];

  return (
    <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Search funnel</CardTitle>
          <CardDescription>How many listings survived each stage</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="space-y-4">
            <FunnelRow label="Collected (raw items)" value={c.collected ?? 0} max={max} />
            <FunnelRow label="Unique listings" value={c.unique ?? 0} max={max} />
            <FunnelRow label={`Passed filters (${filteredTotal} removed)`} value={c.passed_filters ?? 0} max={max}>
              {Object.entries(c.filtered ?? {}).map(([k, n]) => (
                <Badge key={k} variant="outline" className="font-normal">
                  {REASON_LABEL[k] ?? k}: {n}
                </Badge>
              ))}
            </FunnelRow>
            <FunnelRow label={`After dedupe (${c.duplicates_merged ?? 0} cross-listings merged)`} value={c.after_dedupe ?? 0} max={max} />
            <FunnelRow label="Pre-score ≥ 60 (sent to verification)" value={c.prescore_ge_60 ?? 0} max={max} />
            <FunnelRow label="Verified" value={verifiedTotal} max={max}>
              <Badge variant="success" className="font-normal">Active: {v.verified_active ?? 0}</Badge>
              <Badge variant="warning" className="font-normal">Uncertain: {v.uncertain ?? 0}</Badge>
              <Badge variant="destructive" className="font-normal">Inactive: {v.inactive ?? 0}</Badge>
              <Badge variant="outline" className="font-normal">Easy Apply excluded: {v.easy_apply_excluded ?? 0}</Badge>
            </FunnelRow>
            <FunnelRow label={`Scored (${c.below_min_score ?? 0} below ${run.min_score})`} value={c.scored ?? 0} max={max} />
            <FunnelRow label="Final ranked list" value={c.final ?? 0} max={max} />
          </ol>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Cost per platform</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-1.5 font-medium">Platform</th>
                  <th className="py-1.5 text-right font-medium">Items</th>
                  <th className="py-1.5 text-right font-medium">Final</th>
                  <th className="py-1.5 text-right font-medium">Cost</th>
                </tr>
              </thead>
              <tbody className="tabular">
                {run.platforms.map((pl) => {
                  const pp = (p.per_platform?.[pl] ?? {}) as Record<string, number>;
                  return (
                    <tr key={pl} className="border-b">
                      <td className="py-1.5">{PLATFORM_LABEL[pl]}</td>
                      <td className="py-1.5 text-right">{pp.collected ?? 0}</td>
                      <td className="py-1.5 text-right">{pp.final ?? 0}</td>
                      <td className="py-1.5 text-right">{usd(costs[pl] ?? 0, 3)}</td>
                    </tr>
                  );
                })}
                <tr>
                  <td className="py-1.5">LLM scoring</td>
                  <td />
                  <td />
                  <td className="py-1.5 text-right">{usd(p.cost?.llm ?? 0, 3)}</td>
                </tr>
                <tr className="font-semibold">
                  <td className="py-1.5">Total</td>
                  <td />
                  <td />
                  <td className="py-1.5 text-right">{usd(run.cost_usd, 3)}</td>
                </tr>
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Apify runs ({tasks.length})</CardTitle>
            <CardDescription>Dataset IDs are stored, so a resumed run never pays twice</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="max-h-72 space-y-1 overflow-y-auto text-xs">
              {tasks.map((t) => (
                <li key={t.id} className="flex items-center gap-2 border-b py-1 last:border-0">
                  <span className="w-14 shrink-0">{PLATFORM_LABEL[t.platform]}</span>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground" title={t.error ?? undefined}>
                    {t.urls ? `${t.urls} search URLs` : `${t.keyword ?? ""} · ${t.location ?? ""}`}
                    {t.round > 1 ? ` · round ${t.round}` : ""}
                  </span>
                  <span className="shrink-0 tabular">{t.item_count}</span>
                  <Badge
                    variant={t.status === "fetched" ? "success" : t.status === "failed" ? "destructive" : "outline"}
                    className="shrink-0 font-normal"
                  >
                    {t.status}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
