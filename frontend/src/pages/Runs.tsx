import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Download, FileSpreadsheet, Loader2, Plus, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/api/client";
import { ErrorNote } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/progress";
import { fmtDateTime, PLATFORM_LABEL, usd } from "@/lib/utils";
import { statusBadge } from "@/pages/RunProgress";

export function Runs() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs, refetchInterval: 10_000 });

  const upload = useMutation({
    mutationFn: (file: File) => api.uploadExcel(file),
    onSuccess: (data) => {
      toast.success(`Imported ${data.total_imported} opportunities from ${data.filename}`);
      qc.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${data.run_id}/results`);
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to upload Excel file");
    },
  });

  const deleteRun = useMutation({
    mutationFn: (runId: number) => api.deleteRun(runId),
    onSuccess: () => {
      toast.success("Run deleted");
      qc.invalidateQueries({ queryKey: ["runs"] });
    },
    onError: (err: any) => {
      toast.error(err.message || "Failed to delete run");
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      upload.mutate(file);
      e.target.value = "";
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      upload.mutate(file);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
          <p className="text-sm text-muted-foreground">
            Search history and uploaded job spreadsheets.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a href={api.templateUrl()} download="Job_Opportunities_Template.xlsx">
            <Button variant="outline" size="sm">
              <Download className="h-4 w-4 mr-1.5" /> Download Template
            </Button>
          </a>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".xlsx,.xls,.csv"
            className="hidden"
          />
          <Button
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={upload.isPending}
            className="bg-primary hover:bg-primary/90"
          >
            {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : <Upload className="h-4 w-4 mr-1.5" />}
            Upload Excel Sheet
          </Button>
          <Button asChild variant="secondary" size="sm">
            <Link to="/new">
              <Plus className="h-4 w-4 mr-1" /> New Search
            </Link>
          </Button>
        </div>
      </div>

      {/* Quick Upload Dropzone Card */}
      <Card
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`cursor-pointer border-2 border-dashed transition-all hover:border-primary/60 hover:bg-accent/40 ${
          isDragging ? "border-primary bg-primary/5" : "border-muted-foreground/20"
        }`}
      >
        <CardContent className="flex flex-col items-center justify-center py-8 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary mb-3">
            {upload.isPending ? (
              <Loader2 className="h-6 w-6 animate-spin" />
            ) : (
              <FileSpreadsheet className="h-6 w-6" />
            )}
          </div>
          <h3 className="text-base font-medium">
            {upload.isPending ? "Importing spreadsheet..." : "Drop your Excel sheet here or click to browse"}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Supports <span className="font-medium text-foreground">.xlsx</span>,{" "}
            <span className="font-medium text-foreground">.xls</span>, and{" "}
            <span className="font-medium text-foreground">.csv</span> files.
          </p>
        </CardContent>
      </Card>

      <ErrorNote error={runs.error || upload.error} />
      {runs.isLoading && <Skeleton className="h-40 w-full" />}

      {runs.data?.length === 0 && (
        <Card className="p-8 text-center text-sm text-muted-foreground">
          No runs yet. Upload an Excel sheet above or start a{" "}
          <Link to="/new" className="text-primary hover:underline font-medium">
            new search
          </Link>.
        </Card>
      )}

      <ul className="space-y-2.5">
        {runs.data?.map((r) => (
          <li key={r.id} className="group relative">
            <Link
              to={r.status === "completed" ? `/runs/${r.id}/results` : `/runs/${r.id}`}
              className="flex items-center gap-3 rounded-lg border bg-card p-4 transition-colors hover:bg-accent/50"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent/60">
                <FileSpreadsheet className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">
                    {(r.estimate as any)?.excel_import ? (r.estimate as any)?.filename || `Excel Import #${r.id}` : `Run #${r.id}`}
                  </span>
                  {statusBadge(r.status)}
                  {(r.estimate as any)?.excel_import && (
                    <Badge variant="outline" className="border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
                      Excel
                    </Badge>
                  )}
                  {r.estimate?.demo && <Badge variant="outline">Demo</Badge>}
                </div>
                <div className="truncate text-sm text-muted-foreground">
                  {r.roles.join(", ")} · {r.locations.join(", ") || "All Locations"}
                  {r.include_remote_india ? ", Remote" : ""} · {r.platforms.map((p) => PLATFORM_LABEL[p] || p).join("/")}
                </div>
                <div className="text-xs text-muted-foreground">{fmtDateTime(r.created_at)}</div>
              </div>
              <div className="hidden text-right text-sm sm:block mr-2">
                <div className="font-semibold tabular">{r.final_count ?? "—"} jobs</div>
                <div className="text-xs text-muted-foreground tabular">
                  {(r.estimate as any)?.excel_import ? "Imported" : usd(r.cost_usd, 3)}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-12 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
              title="Delete run"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                if (confirm(`Delete run #${r.id}?`)) {
                  deleteRun.mutate(r.id);
                }
              }}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
