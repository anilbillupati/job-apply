import { Check, Plus, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn, PLATFORM_LABEL } from "@/lib/utils";

/** Toggleable chip used for multi-select (roles, cities, platforms). */
export function ToggleChip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input bg-background text-foreground hover:bg-accent",
      )}
    >
      {selected && <Check className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

/** Editable list of strings shown as removable chips with an add box. */
export function ChipList({
  values,
  onChange,
  placeholder = "Add…",
  variant = "secondary",
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  variant?: "secondary" | "outline";
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const parts = draft
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean)
      .filter((s) => !values.some((v) => v.toLowerCase() === s.toLowerCase()));
    if (parts.length) onChange([...values, ...parts]);
    setDraft("");
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {values.length === 0 && <span className="text-sm text-muted-foreground">None</span>}
        {values.map((v) => (
          <Badge key={v} variant={variant} className="max-w-full py-1 pl-2.5 pr-1 text-[13px]">
            <span className="truncate">{v}</span>
            <button
              type="button"
              aria-label={`Remove ${v}`}
              className="rounded-full p-0.5 hover:bg-foreground/10"
              onClick={() => onChange(values.filter((x) => x !== v))}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="h-9"
        />
        <button
          type="button"
          onClick={add}
          className="inline-flex h-9 shrink-0 items-center gap-1 rounded-md border border-input px-3 text-sm hover:bg-accent"
        >
          <Plus className="h-4 w-4" /> Add
        </button>
      </div>
    </div>
  );
}

export function scoreTone(score: number | null | undefined) {
  if (score == null) return "bg-muted text-muted-foreground";
  if (score >= 85) return "bg-success/15 text-success ring-1 ring-success/30";
  if (score >= 75) return "bg-primary/10 text-primary ring-1 ring-primary/25";
  if (score >= 65) return "bg-warning/15 text-warning ring-1 ring-warning/30";
  return "bg-muted text-muted-foreground";
}

export function ScoreBadge({ score, className }: { score: number | null | undefined; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-[3rem] justify-center rounded-md px-2 py-1 text-sm font-semibold tabular",
        scoreTone(score),
        className,
      )}
      title={score == null ? "Not scored" : score >= 85 ? "85+" : score >= 75 ? "75–84" : score >= 65 ? "65–74" : "<65"}
    >
      {score ?? "—"}
    </span>
  );
}

const PLATFORM_DOT: Record<string, string> = {
  linkedin: "bg-[#0a66c2]",
  naukri: "bg-[#4a90e2]",
  indeed: "bg-[#2557a7]",
};

export function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={cn("h-2 w-2 rounded-full", PLATFORM_DOT[platform] ?? "bg-muted-foreground")} />
      {PLATFORM_LABEL[platform] ?? platform}
    </span>
  );
}

export function VerificationBadge({ status, easyApply }: { status: string | null; easyApply?: boolean | null }) {
  if (!status) return <Badge variant="outline">Not checked</Badge>;
  if (status === "verified_active" && easyApply) return <Badge variant="warning">Active · Easy Apply</Badge>;
  if (status === "verified_active") return <Badge variant="success">Verified active</Badge>;
  if (status === "inactive") return <Badge variant="destructive">Closed</Badge>;
  return <Badge variant="warning">Uncertain</Badge>;
}

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const variant = category === "safe" ? "success" : category === "strong" ? "secondary" : "warning";
  return (
    <Badge variant={variant} className="capitalize">
      {category}
    </Badge>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 text-xl font-semibold tabular">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}
