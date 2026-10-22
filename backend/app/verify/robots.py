"""robots.txt cache. A disallowed URL is never fetched; the job is marked uncertain instead."""

import logging
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import get_settings

log = logging.getLogger("robots")

ROBOTS_AGENT = "*"


class RobotsCache:
    def __init__(self, http: httpx.AsyncClient):
        self._http = http
        self._parsers: dict[str, RobotFileParser | None] = {}

    async def allowed(self, url: str) -> bool:
        if not get_settings().respect_robots_txt:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers:
            self._parsers[origin] = await self._load(origin)
        parser = self._parsers[origin]
        return True if parser is None else parser.can_fetch(ROBOTS_AGENT, url)

    async def _load(self, origin: str) -> RobotFileParser | None:
        try:
            resp = await self._http.get(f"{origin}/robots.txt", timeout=10, follow_redirects=True)
        except httpx.HTTPError as exc:
            log.info(f"robots.txt unavailable for {origin}: {exc}")
            return None
        parser = RobotFileParser()
        if resp.status_code in (401, 403):
            parser.disallow_all = True  # same convention as urllib.robotparser
            return parser
        if resp.status_code >= 400:
            return None  # no robots.txt means no restrictions
        parser.parse(resp.text.splitlines())
        return parser
