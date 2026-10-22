import { Link } from "react-router-dom";
import type { Job, JobStatus } from "../types/job";
import { StatusSelect } from "./StatusSelect";

interface Props {
  job: Job;
  onStatusChange: (job: Job, status: JobStatus) => void;
  onDelete: (job: Job) => void;
}

export function JobCard({ job, onStatusChange, onDelete }: Props) {
  const meta = [job.company, job.location, job.employment_type].filter(Boolean).join(" · ");

  return (
    <article className="job-card">
      <div className="job-card-main">
        <Link to={`/jobs/${job.id}`} className="job-title">
          {job.title}
        </Link>
        {meta && <div className="job-meta">{meta}</div>}
        {job.salary && <div className="job-meta">{job.salary}</div>}
        {job.source && <div className="job-source">{job.source}</div>}
      </div>
      <div className="job-card-actions">
        <StatusSelect value={job.status} onChange={(s) => onStatusChange(job, s)} />
        <a href={job.source_url} target="_blank" rel="noreferrer" className="button secondary">
          Open
        </a>
        <button className="button danger" onClick={() => onDelete(job)}>
          Delete
        </button>
      </div>
    </article>
  );
}
