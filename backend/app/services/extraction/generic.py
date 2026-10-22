from typing import Optional

from bs4 import BeautifulSoup

from app.schemas.job import JobCreate
from app.services.extraction.base import BaseExtractor, source_from_url


def _meta(soup: BeautifulSoup, *keys: str) -> Optional[str]:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


class GenericHtmlExtractor(BaseExtractor):
    """Best-effort fallback using OpenGraph / meta tags and the page title."""

    name = "generic"

    def extract(self, url: str, soup: BeautifulSoup) -> Optional[JobCreate]:
        title = _meta(soup, "og:title", "twitter:title")
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else None
        if not title:
            return None

        return JobCreate(
            title=title[:300],
            company=_meta(soup, "og:site_name"),
            description=_meta(soup, "og:description", "description", "twitter:description"),
            source_url=url,
            source=source_from_url(url),
        )
