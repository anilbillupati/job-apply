from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, attributes, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    raw_text: Mapped[str] = mapped_column(Text)
    parsed_profile: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunStatus:
    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"))
    roles: Mapped[list] = mapped_column(JSON, default=list)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    include_remote_india: Mapped[bool] = mapped_column(Boolean, default=True)
    # any | remote_only | office_or_hybrid
    work_arrangement: Mapped[str] = mapped_column(String(20), default="any")
    posted_within_days: Mapped[int] = mapped_column(Integer, default=7)
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    exclude_linkedin_easy_apply: Mapped[bool] = mapped_column(Boolean, default=True)
    target_count: Mapped[int] = mapped_column(Integer, default=60)
    min_score: Mapped[int] = mapped_column(Integer, default=65)
    keywords: Mapped[dict] = mapped_column(JSON, default=dict)  # {category: [kw, ...]}
    # Company names (case-insensitive substring) to drop for this run.
    exclude_companies: Mapped[list] = mapped_column(JSON, default=list)
    # Scrape depth multiplier and expansion bookkeeping (round 1 = initial search).
    round: Mapped[int] = mapped_column(Integer, default=1)
    expand_steps: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.DRAFT)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimate: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)

    resume: Mapped[Resume] = relationship()
    tasks: Mapped[list["ScrapeTask"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ScrapeTask(Base):
    __tablename__ = "scrape_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer, default=1)
    platform: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str] = mapped_column(String(100))
    input: Mapped[dict] = mapped_column(JSON)
    # Maps a LinkedIn search URL (or "*") to {"keyword", "location"} so raw items keep their query.
    query_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    # The pooled Apify key that started this run. Apify run/dataset IDs belong to that account.
    apify_key_id: Mapped[int | None] = mapped_column(ForeignKey("apify_keys.id", ondelete="SET NULL"))
    memory_mb: Mapped[int] = mapped_column(Integer, default=256)
    max_charge_usd: Mapped[float] = mapped_column(Float, default=0.0)
    est_items: Mapped[int] = mapped_column(Integer, default=0)
    apify_run_id: Mapped[str | None] = mapped_column(String(50))
    dataset_id: Mapped[str | None] = mapped_column(String(50))
    # pending | running | succeeded | partial | failed | aborted | fetched
    status: Mapped[str] = mapped_column(String(20), default="pending")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)

    run: Mapped[SearchRun] = relationship(back_populates="tasks")


class RawJob(Base):
    __tablename__ = "raw_jobs"
    __table_args__ = (UniqueConstraint("platform", "platform_job_id", "run_id", name="uq_raw_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20))
    platform_job_id: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    keyword: Mapped[str | None] = mapped_column(String(200))
    location_query: Mapped[str | None] = mapped_column(String(200))
    is_remote_query: Mapped[bool] = mapped_column(Boolean, default=False)
    normalized: Mapped[bool] = mapped_column(Boolean, default=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("search_runs.id", ondelete="CASCADE"), index=True)
    raw_job_id: Mapped[int | None] = mapped_column(ForeignKey("raw_jobs.id", ondelete="SET NULL"))
    platform: Mapped[str] = mapped_column(String(20))
    platform_job_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(500))
    company: Mapped[str] = mapped_column(String(300), default="")
    location_text: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str | None] = mapped_column(String(30))
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    work_mode: Mapped[str] = mapped_column(String(10), default="unknown")  # office | hybrid | remote | unknown
    posted_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="")
    exp_min: Mapped[float | None] = mapped_column(Float)
    exp_max: Mapped[float | None] = mapped_column(Float)
    salary_text: Mapped[str | None] = mapped_column(String(200))
    listing_url: Mapped[str | None] = mapped_column(String(1000))
    apply_url: Mapped[str | None] = mapped_column(String(1000))
    employer_url: Mapped[str | None] = mapped_column(String(1000))
    applicants_text: Mapped[str | None] = mapped_column(String(100))
    is_agency: Mapped[bool] = mapped_column(Boolean, default=False)
    dedupe_key: Mapped[str] = mapped_column(String(400), default="", index=True)
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    alt_sources: Mapped[list] = mapped_column(JSON, default=list)
    # Pipeline bookkeeping
    filter_reason: Mapped[str | None] = mapped_column(String(40))
    prescore: Mapped[float | None] = mapped_column(Float)
    prescore_detail: Mapped[dict | None] = mapped_column(JSON)
    # User state
    user_state: Mapped[str | None] = mapped_column(String(20))  # shortlisted | applied | rejected
    user_note: Mapped[str | None] = mapped_column(Text)

    verification: Mapped["Verification | None"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )
    score: Mapped["Score | None"] = relationship(
        back_populates="job", uselist=False, cascade="all, delete-orphan"
    )


class Verification(Base):
    __tablename__ = "verifications"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))  # verified_active | uncertain | inactive
    method: Mapped[str] = mapped_column(String(60))
    easy_apply: Mapped[bool | None] = mapped_column(Boolean)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job] = relationship(back_populates="verification")


class Score(Base):
    __tablename__ = "scores"

    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    total: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict] = mapped_column(JSON)
    company_tier: Mapped[str] = mapped_column(String(80))
    experience_summary: Mapped[str] = mapped_column(Text)
    key_skills_match: Mapped[str] = mapped_column(Text)
    why_fits: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(10), default="strong")  # stretch | strong | safe
    model: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[Job] = relationship(back_populates="score")


class AppSetting(Base):
    """User-editable settings (blocklists, model choice). Secrets never live here."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict | list | str | float | int | bool | None] = mapped_column(JSON)


class ApifyKey(Base):
    """A pooled Apify API token. The token is encrypted at rest and never returned by the API."""

    __tablename__ = "apify_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(200))
    token_enc: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256, for duplicate detection
    last4: Mapped[str] = mapped_column(String(8))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    exhausted_on: Mapped[date | None] = mapped_column(Date)  # skipped for the rest of this day
    last_error: Mapped[str | None] = mapped_column(Text)
    last_used_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApifyKeyDay(Base):
    """Which key was picked for each calendar day."""

    __tablename__ = "apify_key_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    key_id: Mapped[int | None] = mapped_column(ForeignKey("apify_keys.id", ondelete="SET NULL"))
    picked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApifyKeyUsage(Base):
    """Log of when each key was picked or used (daily pick, run, failover, test)."""

    __tablename__ = "apify_key_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_id: Mapped[int | None] = mapped_column(ForeignKey("apify_keys.id", ondelete="SET NULL"), index=True)
    key_label: Mapped[str] = mapped_column(String(200))  # snapshot, kept after the key is deleted
    day: Mapped[date] = mapped_column(Date, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event: Mapped[str] = mapped_column(String(20))  # daily_pick | run | failover | test
    run_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)


class SeenJob(Base):
    """Jobs already shown in a ranked list or marked by the user. Later runs skip them.

    No foreign keys on purpose: the history survives deleting runs."""

    __tablename__ = "seen_jobs"

    platform: Mapped[str] = mapped_column(String(20), primary_key=True)
    platform_job_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    company: Mapped[str] = mapped_column(String(300), default="")
    first_run_id: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(20))  # shown | marked
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(Session, "before_flush")
def _remember_marked_jobs(session: Session, flush_context, instances) -> None:
    """When a job gets a user state (shortlisted/applied/rejected...), add it to the seen history."""
    with session.no_autoflush:
        for obj in list(session.dirty) + list(session.new):
            if not isinstance(obj, Job) or not obj.user_state or not obj.platform_job_id:
                continue
            if not attributes.get_history(obj, "user_state").has_changes():
                continue
            key = (obj.platform, obj.platform_job_id)
            if session.get(SeenJob, key) is None and not any(
                isinstance(o, SeenJob) and (o.platform, o.platform_job_id) == key for o in session.new
            ):
                session.add(SeenJob(platform=obj.platform, platform_job_id=obj.platform_job_id,
                                    title=(obj.title or "")[:500], company=(obj.company or "")[:300],
                                    first_run_id=obj.run_id, reason="marked"))
