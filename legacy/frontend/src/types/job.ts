export const JOB_STATUSES = ["new", "saved", "applied", "interviewing", "offer", "rejected"] as const;

export type JobStatus = (typeof JOB_STATUSES)[number];

export interface JobFields {
  title: string;
  company: string | null;
  location: string | null;
  employment_type: string | null;
  salary: string | null;
  date_posted: string | null;
  description: string | null;
  source_url: string;
  source: string | null;
}

export interface Job extends JobFields {
  id: number;
  status: JobStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobList {
  items: Job[];
  total: number;
}

export type JobUpdate = Partial<Pick<Job, "title" | "company" | "location" | "salary" | "description" | "status" | "notes">>;

export interface ExtractionResult {
  extractor: string;
  job: JobFields & { status: JobStatus };
  saved_job: Job | null;
}
