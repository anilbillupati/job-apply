from typing import Tuple

from app.schemas.job import JobCreate
from app.services.extraction.base import BaseExtractor, ExtractionError
from app.services.extraction.fetcher import fetch_html
from app.services.extraction.registry import EXTRACTORS, extract_from_html


async def extract_job(url: str) -> Tuple[str, JobCreate]:
    """Fetch a job posting URL and return (extractor_name, job)."""
    html = await fetch_html(url)
    return extract_from_html(url, html)


__all__ = ["BaseExtractor", "EXTRACTORS", "ExtractionError", "extract_from_html", "extract_job"]
