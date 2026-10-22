import json
from typing import Any, Iterator, Optional

from bs4 import BeautifulSoup

from app.schemas.job import JobCreate
from app.services.extraction.base import BaseExtractor, html_to_text, source_from_url


def _iter_nodes(data: Any) -> Iterator[dict]:
    if isinstance(data, list):
        for item in data:
            yield from _iter_nodes(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_nodes(data["@graph"])


def _is_job_posting(node: dict) -> bool:
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    return "JobPosting" in types


def _name(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        return value.get("name")
    if isinstance(value, str):
        return value
    return None


def _location(node: dict) -> Optional[str]:
    locations = node.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    parts = []
    for loc in locations:
        address = loc.get("address") if isinstance(loc, dict) else None
        if isinstance(address, str):
            parts.append(address)
        elif isinstance(address, dict):
            fields = [
                address.get("addressLocality"),
                address.get("addressRegion"),
                _name(address.get("addressCountry")),
            ]
            parts.append(", ".join(f for f in fields if f))
    if node.get("jobLocationType") == "TELECOMMUTE":
        parts.append("Remote")
    joined = " | ".join(p for p in parts if p)
    return joined or None


def _salary(node: dict) -> Optional[str]:
    base = node.get("baseSalary")
    if not isinstance(base, dict):
        return str(base) if base else None
    currency = base.get("currency", "")
    value = base.get("value")
    if isinstance(value, dict):
        unit = value.get("unitText", "")
        low, high, exact = value.get("minValue"), value.get("maxValue"), value.get("value")
        amount = f"{low} - {high}" if low and high else str(exact or low or high or "")
        return " ".join(p for p in [currency, amount, f"/ {unit}" if unit else ""] if p) or None
    return f"{currency} {value}".strip() if value else None


def _employment_type(node: dict) -> Optional[str]:
    value = node.get("employmentType")
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


class JsonLdExtractor(BaseExtractor):
    """Reads schema.org JobPosting JSON-LD, which most job boards embed for SEO."""

    name = "jsonld"

    def extract(self, url: str, soup: BeautifulSoup) -> Optional[JobCreate]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or script.get_text() or "")
            except (json.JSONDecodeError, TypeError):
                continue
            for node in _iter_nodes(data):
                if _is_job_posting(node) and node.get("title"):
                    return JobCreate(
                        title=node["title"].strip(),
                        company=_name(node.get("hiringOrganization")),
                        location=_location(node),
                        employment_type=_employment_type(node),
                        salary=_salary(node),
                        date_posted=node.get("datePosted"),
                        description=html_to_text(node.get("description")),
                        source_url=url,
                        source=source_from_url(url),
                    )
        return None
