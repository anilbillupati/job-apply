import httpx

from app.core.config import get_settings
from app.services.extraction.base import ExtractionError


async def fetch_html(url: str) -> str:
    settings = get_settings()
    headers = {"User-Agent": settings.user_agent, "Accept": "text/html,application/xhtml+xml"}
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
    except httpx.HTTPStatusError as exc:
        raise ExtractionError(f"Page returned HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ExtractionError(f"Could not fetch page: {exc}") from exc
