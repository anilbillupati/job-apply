from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.job import Job
from app.schemas.job import JobCreate, JobList, JobRead, JobStatus, JobUpdate
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_or_404(db: Session, job_id: int) -> Job:
    job = job_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("", response_model=JobList)
def list_jobs(
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    q: Optional[str] = Query(None, description="Search title, company or location"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> JobList:
    items, total = job_service.list_jobs(db, status=status_filter, q=q, skip=skip, limit=limit)
    return JobList(items=[JobRead.model_validate(j) for j in items], total=total)


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(data: JobCreate, db: Session = Depends(get_db)) -> Job:
    return job_service.upsert_job(db, data)


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, db: Session = Depends(get_db)) -> Job:
    return _get_or_404(db, job_id)


@router.patch("/{job_id}", response_model=JobRead)
def update_job(job_id: int, data: JobUpdate, db: Session = Depends(get_db)) -> Job:
    return job_service.update_job(db, _get_or_404(db, job_id), data)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, db: Session = Depends(get_db)) -> Response:
    job_service.delete_job(db, _get_or_404(db, job_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
