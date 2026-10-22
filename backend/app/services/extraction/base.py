from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.schemas.job import JobCreate


class ExtractionError(Exception):
    """Raised when a job posting cannot be fetched or parsed."""


class BaseExtractor(ABC):
    """A strategy for turning a job posting page into a JobCreate.

    Add site-specific extractors (LinkedIn, Greenhouse, Lever, ...) by subclassing
    this and registering them in `registry.py` ahead of the generic ones.
    """

    name: str = "base"

    def can_handle(self, url: str) -> bool:
        return True

    @abstractmethod
    def extract(self, url: str, soup: BeautifulSoup) -> Optional[JobCreate]:
        """Return a JobCreate, or None if this extractor found nothing usable."""


def source_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def html_to_text(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text("\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line) or None
