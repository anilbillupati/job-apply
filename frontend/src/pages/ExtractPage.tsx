import { useState } from "react";
import { Link } from "react-router-dom";
import { extractJob } from "../api/jobs";
import type { ExtractionResult } from "../types/job";

export function ExtractPage() {
  const [url, setUrl] = useState("");
  const [save, setSave] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExtractionResult | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await extractJob(url.trim(), save));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setLoading(false);
    }
  }

  const job = result?.job;

  return (
    <section>
      <div className="page-header">
        <h1>Extract a job</h1>
      </div>

      <form className="toolbar" onSubmit={handleSubmit}>
        <input
          type="url"
          required
          placeholder="https://company.com/careers/job-posting"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <label className="checkbox">
          <input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} />
          Save
        </label>
        <button className="button" type="submit" disabled={loading}>
          {loading ? "Extracting…" : "Extract"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {job && (
        <article className="panel">
          <div className="page-header">
            <h2>{job.title}</h2>
            <span className="muted">via {result.extractor}</span>
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
          </dl>
          {job.description && <pre className="description">{job.description}</pre>}
          {result.saved_job && (
            <p>
              Saved — <Link to={`/jobs/${result.saved_job.id}`}>view job</Link>
            </p>
          )}
        </article>
      )}
    </section>
  );
}
