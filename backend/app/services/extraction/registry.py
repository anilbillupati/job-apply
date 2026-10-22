from typing import List, Tuple

from bs4 import BeautifulSoup

from app.schemas.job import JobCreate
from app.services.extraction.base import BaseExtractor, ExtractionError
from app.services.extraction.generic import GenericHtmlExtractor
from app.services.extraction.jsonld import JsonLdExtractor

# Ordered most-specific first. Site-specific extractors go before these.
EXTRACTORS: List[BaseExtractor] = [
    JsonLdExtractor(),
    GenericHtmlExtractor(),
]


def extract_from_html(url: str, html: str) -> Tuple[str, JobCreate]:
    soup = BeautifulSoup(html, "html.parser")
    for extractor in EXTRACTORS:
        if not extractor.can_handle(url):
            continue
        job = extractor.extract(url, soup)
        if job is not None:
            return extractor.name, job
    raise ExtractionError("No job posting data found on the page")
