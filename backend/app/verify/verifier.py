"""Fetchers for active-job verification. Low request rates, no logins, no captcha solving."""

import asyncio
import logging
import random
from datetime import UTC, datetime

import httpx

from app.apify.client import request_with_retry
from app.logging_setup import redact, timed_call
from app.verify.classify import (
    UNCERTAIN,
    classify_employer_page,
    classify_linkedin,
    classify_naukri_text,
)
from app.verify.robots import RobotsCache

log = logging.getLogger("verify")

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
LINKEDIN_GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def result(status: str, method: str, easy_apply=None, **evidence) -> dict:
    evidence.setdefault("checked_at", _now())
    return {"status": status, "method": method, "easy_apply": easy_apply, "evidence": evidence}


class Verifier:
    """One instance per verification stage. Call the platform method for each job."""

    def __init__(self):
        self.http = httpx.AsyncClient(
            headers={"User-Agent": DESKTOP_UA, "Accept-Language": "en-IN,en;q=0.9"},
            timeout=25,
            follow_redirects=True,
        )
        self.robots = RobotsCache(self.http)
        self._linkedin_lock = asyncio.Lock()
        self._naukri_lock = asyncio.Lock()
        self._browser = None
        self._pw = None

    async def aclose(self) -> None:
        await self.http.aclose()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    # -------------------------------------------------------------- LinkedIn

    async def linkedin(self, job_id: str) -> dict:
        url = LINKEDIN_GUEST.format(id=job_id)
        if not await self.robots.allowed(url):
            return result(UNCERTAIN, "linkedin_guest_api", url=url, reason="disallowed by robots.txt")
        async with self._linkedin_lock:  # strictly sequential
            await asyncio.sleep(random.uniform(1.2, 1.5))
            try:
                with timed_call(log, "linkedin", "jobPosting", job=job_id) as info:
                    resp = await request_with_retry(self.http, "GET", url, attempts=3)
                    info["status"] = resp.status_code
            except httpx.HTTPError as exc:
                return result(UNCERTAIN, "linkedin_guest_api", url=url, reason=redact(exc))
        if resp.status_code != 200:
            return result(
                UNCERTAIN, "linkedin_guest_api", url=url, http_status=resp.status_code, reason="non-200 response"
            )
        c = classify_linkedin(resp.text)
        return result(
            c["status"],
            "linkedin_guest_api",
            c.get("easy_apply"),
            url=url,
            final_url=str(resp.url),
            http_status=resp.status_code,
            matched=c["matched"],
            posted_time_ago=c.get("posted_time_ago"),
            applicants=c.get("applicants"),
        )

    # -------------------------------------------------------------- Naukri

    async def _page(self):
        if self._browser is None:
            from playwright.async_api import async_playwright  # optional dependency at runtime

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=True)
        ctx = await self._browser.new_context(user_agent=DESKTOP_UA, locale="en-IN")
        return ctx, await ctx.new_page()

    async def naukri(self, listing_url: str | None) -> dict:
        if not listing_url:
            return result(UNCERTAIN, "naukri_playwright", reason="no listing URL")
        if not await self.robots.allowed(listing_url):
            return result(UNCERTAIN, "naukri_playwright", url=listing_url, reason="disallowed by robots.txt")
        async with self._naukri_lock:
            await asyncio.sleep(random.uniform(1.5, 2.5))
            ctx = None
            try:
                with timed_call(log, "naukri", "render", url=listing_url) as info:
                    ctx, page = await self._page()
                    resp = await page.goto(listing_url, wait_until="networkidle", timeout=30_000)
                    text = await page.evaluate("document.body.innerText")
                    final_url = page.url
                    info["status"] = resp.status if resp else None
            except ImportError:
                return result(UNCERTAIN, "naukri_playwright", url=listing_url, reason="playwright not installed")
            except Exception as exc:  # noqa: BLE001 - browser errors are many and varied
                return result(UNCERTAIN, "naukri_playwright", url=listing_url, reason=redact(exc)[:300])
            finally:
                if ctx:
                    await ctx.close()
        c = classify_naukri_text(text or "")
        return result(
            c["status"],
            "naukri_playwright",
            url=listing_url,
            final_url=final_url,
            http_status=info.get("status"),
            matched=c["matched"],
            reason=c.get("reason"),
            posted=c.get("posted"),
        )

    # -------------------------------------------------------------- Indeed

    async def indeed(self, expired: bool, employer_url: str | None) -> dict:
        if expired:
            return result("inactive", "indeed_scraped_flag", matched=["expired == true"])
        if not employer_url:
            return result(UNCERTAIN, "indeed_employer_page", reason="no employer jobUrl (Indeed-hosted apply)")
        if not await self.robots.allowed(employer_url):
            return result(UNCERTAIN, "indeed_employer_page", url=employer_url, reason="disallowed by robots.txt")
        await asyncio.sleep(random.uniform(0.5, 1.0))
        try:
            with timed_call(log, "employer", "fetch", url=employer_url) as info:
                resp = await request_with_retry(self.http, "GET", employer_url, attempts=2)
                info["status"] = resp.status_code
        except httpx.HTTPError as exc:
            return result(UNCERTAIN, "indeed_employer_page", url=employer_url, reason=redact(exc)[:300])
        c = classify_employer_page(resp.text, resp.status_code)
        return result(
            c["status"],
            "indeed_employer_page",
            url=employer_url,
            final_url=str(resp.url),
            http_status=resp.status_code,
            matched=c["matched"],
            reason=c.get("reason"),
        )
