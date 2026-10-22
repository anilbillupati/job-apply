from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.extraction import ExtractionRequest, ExtractionResult
from app.schemas.job import JobRead
from app.services import job_service
from app.services.extraction import ExtractionError, extract_job

router = APIRouter(prefix="/extract", tags=["extraction"])


@router.post("", response_model=ExtractionResult)
async def extract(request: ExtractionRequest, db: Session = Depends(get_db)) -> ExtractionResult:
    """Fetch a job posting URL, parse it, and optionally save it."""
    try:
        extractor, job = await extract_job(str(request.url))
    except ExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    saved = job_service.upsert_job(db, job) if request.save else None
    return ExtractionResult(
        extractor=extractor,
        job=job,
        saved_job=JobRead.model_validate(saved) if saved else None,
    )
