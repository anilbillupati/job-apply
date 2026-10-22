import { useState } from "react";
import { deleteJob, updateJob } from "../api/jobs";
import { JobCard } from "../components/JobCard";
import { useJobs } from "../hooks/useJobs";
import { JOB_STATUSES, type Job, type JobStatus } from "../types/job";

export function JobsPage() {
  const [status, setStatus] = useState<JobStatus | "">("");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const { jobs, total, loading, error, reload } = useJobs({ status: status || undefined, q: query });

  async function handleStatusChange(job: Job, next: JobStatus) {
    await updateJob(job.id, { status: next });
    await reload();
  }

  async function handleDelete(job: Job) {
    if (!window.confirm(`Delete "${job.title}"?`)) return;
    await deleteJob(job.id);
    await reload();
  }

  return (
    <section>
      <div className="page-header">
        <h1>Jobs</h1>
        <span className="muted">{total} total</span>
      </div>

      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(search.trim());
        }}
      >
        <input
          type="search"
          placeholder="Search title, company, location"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value as JobStatus | "")}>
          <option value="">All statuses</option>
          {JOB_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button className="button" type="submit">
          Search
        </button>
      </form>

      {error && <p className="error">{error}</p>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">No jobs yet. Use Extract to add one from a posting URL.</p>
      ) : (
        <div className="job-list">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} onStatusChange={handleStatusChange} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </section>
  );
}
