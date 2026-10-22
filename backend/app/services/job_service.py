from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.job import Job
from app.schemas.job import JobCreate, JobStatus, JobUpdate


def list_jobs(
    db: Session,
    status: Optional[JobStatus] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[Job], int]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status.value)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company.ilike(like), Job.location.ilike(like)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(stmt.order_by(Job.created_at.desc(), Job.id.desc()).offset(skip).limit(limit)).all()
    return list(items), total


def get_job(db: Session, job_id: int) -> Optional[Job]:
    return db.get(Job, job_id)


def get_job_by_url(db: Session, url: str) -> Optional[Job]:
    return db.scalar(select(Job).where(Job.source_url == url))


def upsert_job(db: Session, data: JobCreate) -> Job:
    """Create a job, or refresh the scraped fields if the URL was already saved.

    Status and notes are user-owned, so they are kept on re-extraction.
    """
    job = get_job_by_url(db, data.source_url)
    if job is None:
        job = Job(**data.model_dump(mode="json"))
        db.add(job)
    else:
        for field, value in data.model_dump(mode="json", exclude={"status", "notes"}).items():
            setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job: Job, data: JobUpdate) -> Job:
    for field, value in data.model_dump(mode="json", exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job


def delete_job(db: Session, job: Job) -> None:
    db.delete(job)
    db.commit()
