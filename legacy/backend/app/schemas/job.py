from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(str, Enum):
    new = "new"
    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"


class JobBase(BaseModel):
    title: str = Field(..., max_length=300)
    company: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary: Optional[str] = None
    date_posted: Optional[str] = None
    description: Optional[str] = None
    source_url: str = Field(..., max_length=2000)
    source: Optional[str] = None


class JobCreate(JobBase):
    status: JobStatus = JobStatus.new
    notes: Optional[str] = None


class JobUpdate(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary: Optional[str] = None
    description: Optional[str] = None
    status: Optional[JobStatus] = None
    notes: Optional[str] = None


class JobRead(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: JobStatus
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobList(BaseModel):
    items: List[JobRead]
    total: int
