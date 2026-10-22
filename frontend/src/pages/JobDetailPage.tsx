import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getJob, updateJob } from "../api/jobs";
import { StatusSelect } from "../components/StatusSelect";
import type { Job, JobStatus } from "../types/job";

export function JobDetailPage() {
  const { id } = useParams();
  const [job, setJob] = useState<Job | null>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getJob(Number(id))
      .then((j) => {
        setJob(j);
        setNotes(j.notes ?? "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load job"));
  }, [id]);

  async function save(patch: { status?: JobStatus; notes?: string }) {
    if (!job) return;
    setSaving(true);
    try {
      setJob(await updateJob(job.id, patch));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!job) return <p className="muted">Loading…</p>;

  return (
    <section>
      <Link to="/" className="muted">
        ← Back to jobs
      </Link>
      <div className="page-header">
        <h1>{job.title}</h1>
        <StatusSelect value={job.status} disabled={saving} onChange={(status) => save({ status })} />
      </div>

      <dl className="fields">
        <dt>Company</dt>
        <dd>{job.company ?? "—"}</dd>
        <dt>Location</dt>
        <dd>{job.location ?? "—"}</dd>
        <dt>Type</dt>
        <dd>{job.employment_type ?? "—"}</dd>
        <dt>Salary</dt>
        <dd>{job.salary ?? "—"}</dd>
        <dt>Posted</dt>
        <dd>{job.date_posted ?? "—"}</dd>
        <dt>Source</dt>
        <dd>
          <a href={job.source_url} target="_blank" rel="noreferrer">
            {job.source ?? job.source_url}
          </a>
        </dd>
      </dl>

      <div className="panel">
        <h2>Notes</h2>
        <textarea rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <button className="button" disabled={saving} onClick={() => save({ notes })}>
          Save notes
        </button>
      </div>

      {job.description && (
        <div className="panel">
          <h2>Description</h2>
          <pre className="description">{job.description}</pre>
        </div>
      )}
    </section>
  );
}
