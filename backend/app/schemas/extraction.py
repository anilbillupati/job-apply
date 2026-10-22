from typing import Optional

from pydantic import BaseModel, HttpUrl

from app.schemas.job import JobCreate, JobRead


class ExtractionRequest(BaseModel):
    url: HttpUrl
    save: bool = True


class ExtractionResult(BaseModel):
    extractor: str
    job: JobCreate
    saved_job: Optional[JobRead] = None
