export interface Employer {
  name: string;
  title: string;
  start: string;
  end: string;
}

export interface Profile {
  total_years_experience: number;
  current_title: string;
  employers: Employer[];
  education: string[];
  certifications: string[];
  skills_professional: string[];
  skills_listed_only: string[];
  measurable_achievements: string[];
  best_fit_categories: string[];
  realistic_levels: string[];
  gaps: string[];
  inconsistencies: string[];
  source?: string;
  edited?: boolean;
}

export interface Resume {
  id: number;
  filename: string;
  chars: number;
  parsed_profile: Profile | null;
  created_at: string;
  llm_cost_usd?: number;
}

export interface Meta {
  roles: string[];
  cities: string[];
  platforms: string[];
  llm_configured: boolean;
  apify_configured: boolean;
  max_run_cost_usd: number;
}

export interface PlatformEstimate {
  runs: number;
  items: number;
  cost_usd: number;
}

export interface Estimate {
  platforms?: Record<string, PlatformEstimate>;
  apify_total_usd?: number;
  est_items?: number;
  llm_estimate_usd?: number;
  llm_model?: string;
  cap_usd?: number;
  spent_usd?: number;
  remaining_credit_usd?: number | null;
  credit_check?: string;
  ok?: boolean;
  reasons?: string[];
  demo?: boolean;
  note?: string;
  apify_key?: { label: string; masked: string };
}

export interface Counts {
  collected?: number;
  unique?: number;
  filtered?: Record<string, number>;
  passed_filters?: number;
  duplicates_merged?: number;
  after_dedupe?: number;
  prescore_ge_60?: number;
  verified?: Record<string, number>;
  scored?: number;
  below_min_score?: number;
  final?: number;
}

export interface PlatformProgress {
  stage?: string;
  tasks_total?: number;
  tasks_done?: number;
  items?: number;
  verify_total?: number;
  verify_done?: number;
}

export interface Progress {
  stage?: string;
  completed?: string[];
  platforms?: Record<string, PlatformProgress>;
  counts?: Counts;
  per_platform?: Record<string, Record<string, unknown>>;
  cost?: { apify?: Record<string, number>; apify_total?: number; llm?: number };
  scoring?: { total: number; done: number; failed: number };
  log?: { ts: string; msg: string }[];
  target_met?: boolean;
}

export interface Task {
  id: number;
  round: number;
  platform: string;
  status: string;
  item_count: number;
  cost_usd: number;
  est_items: number;
  max_charge_usd: number;
  error: string | null;
  keyword: string | null;
  location: string | null;
  urls: number;
}

export type RunStatus = "draft" | "queued" | "running" | "cancelling" | "cancelled" | "completed" | "failed";

export interface Run {
  id: number;
  resume_id: number;
  roles: string[];
  locations: string[];
  include_remote_india: boolean;
  work_arrangement: "any" | "remote_only" | "office_or_hybrid";
  posted_within_days: 7 | 14;
  platforms: string[];
  exclude_linkedin_easy_apply: boolean;
  target_count: number;
  min_score: number;
  keywords: Record<string, string[]>;
  exclude_companies: string[];
  round: number;
  expand_steps: string[];
  status: RunStatus;
  progress: Progress;
  cost_usd: number;
  estimate: Estimate | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  final_count: number | null;
  next_expand_step: { step: string; label: string } | null;
  tasks: Task[] | null;
}

export interface RunInput {
  resume_id: number;
  roles: string[];
  locations: string[];
  include_remote_india: boolean;
  work_arrangement: Run["work_arrangement"];
  posted_within_days: 7 | 14;
  platforms: string[];
  exclude_linkedin_easy_apply: boolean;
  target_count: number;
  min_score: number;
  keywords?: Record<string, string[]>;
  exclude_companies?: string[];
}

export interface JobRow {
  id: number;
  platform: string;
  title: string;
  company: string;
  city: string | null;
  location_text: string;
  is_remote: boolean;
  work_mode: string;
  posted_date: string | null;
  exp_min: number | null;
  exp_max: number | null;
  salary_text: string | null;
  listing_url: string | null;
  apply_url: string | null;
  employer_url: string | null;
  is_agency: boolean;
  duplicate_of: number | null;
  alt_sources: { platform: string; url: string | null; job_id?: number }[];
  filter_reason: string | null;
  prescore: number | null;
  user_state: "shortlisted" | "applied" | "rejected" | null;
  user_note: string | null;
  applicants_text: string | null;
  verification_status: string | null;
  easy_apply: boolean | null;
  score: number | null;
  company_tier: string | null;
  category: "stretch" | "strong" | "safe" | null;
}

export interface JobDetail extends JobRow {
  description: string;
  prescore_detail: Record<string, unknown> | null;
  verification: {
    status: string;
    method: string;
    easy_apply: boolean | null;
    evidence: Record<string, unknown>;
    checked_at: string;
  } | null;
  score_detail: {
    total: number;
    breakdown: Record<string, number>;
    company_tier: string;
    experience_summary: string;
    key_skills_match: string;
    why_fits: string;
    notes: string;
    category: string;
    model: string;
    created_at: string;
  } | null;
  duplicates: JobRow[];
}

export interface JobPage {
  total: number;
  page: number;
  page_size: number;
  items: JobRow[];
}

export interface AppSettings {
  agency_blocklist: string[];
  agency_allowlist: string[];
  title_exclusions: string[];
  seniority_exclusions: string[];
  allow_senior_max_years: number | null;
  llm_model: string;
  llm_top_n: number;
  allowed_models: string[];
  llm_configured: boolean;
  max_run_cost_usd: number;
  respect_robots_txt: boolean;
}

export interface ApifyStatus {
  configured: boolean;
  connected: boolean;
  key_label?: string;
  key_masked?: string;
  error?: string;
  username?: string;
  plan?: string;
  monthly_usage_usd?: number;
  monthly_limit_usd?: number;
  remaining_usd?: number | null;
  cycle_end?: string;
  max_concurrent_runs?: number;
  max_memory_mb?: number;
}

export interface ExpandPreview {
  step: string;
  label: string;
  changes: Record<string, unknown>;
  estimate: Estimate;
  min_score_unchanged: number;
  started?: boolean;
}

export interface ApifyKey {
  id: number;
  label: string;
  masked: string;
  active: boolean;
  exhausted_today: boolean;
  last_error: string | null;
  last_used_on: string | null;
  created_at: string;
  uses: number;
  is_today: boolean;
}

export interface KeyPool {
  today: string;
  timezone: string;
  today_key_id: number | null;
  env_fallback: boolean;
  keys: ApifyKey[];
  usable_today: number;
}

export interface KeyUsage {
  id: number;
  key_id: number | null;
  key_label: string;
  day: string;
  at: string;
  event: "daily_pick" | "run" | "failover" | "test";
  run_id: number | null;
  detail: string | null;
}

export interface KeyImportResult {
  found: number;
  added: number;
  duplicates: number;
  labels: string[];
}

export interface KeyTest extends ApifyStatus {
  key_id: number;
  label: string;
  masked: string;
}

export interface SeenJobs {
  total: number;
  by_reason: Record<string, number>;
  recent: { platform: string; platform_job_id: string; title: string; company: string; reason: string;
    first_run_id: number | null; seen_at: string }[];
}
