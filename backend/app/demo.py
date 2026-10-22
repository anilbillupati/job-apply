"""Fixture-backed stand-ins for Apify and the live verifier, so the full pipeline can be demoed offline.

The recorded datasets in fixtures/apify_*.json have the actors' output shape. Dates are stored as
`_days_ago` and materialised relative to today. Verification runs the real classifiers on recorded pages.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.config import BACKEND_DIR
from app.scrapers.platforms import ACTORS, LINKEDIN, NAUKRI, PRICE_PER_ITEM
from app.verify.classify import classify_employer_page, classify_linkedin, classify_naukri_text
from app.verify.verifier import result

FIXTURES = BACKEND_DIR / "fixtures"
PAGES = FIXTURES / "pages"
PLATFORM_BY_ACTOR = {v: k for k, v in ACTORS.items()}


def load_dataset(platform: str) -> list[dict]:
    return json.loads((FIXTURES / f"apify_{platform}.json").read_text(encoding="utf-8"))


def _materialize(platform: str, item: dict) -> dict:
    out = copy.deepcopy(item)
    days = int(out.get("_days_ago", 0))
    now = datetime.now(UTC)
    if platform == LINKEDIN:
        out["postedAt"] = (now - timedelta(days=days)).date().isoformat()
    elif platform == NAUKRI:
        out["createdDateText"] = "Today" if days == 0 else f"{days} Day{'s' if days > 1 else ''} Ago"
    else:
        out["datePublished"] = int((now - timedelta(days=days)).timestamp() * 1000)
    return out


def _city_matches(item: dict, city: str | None, remote: bool) -> bool:
    if remote:
        return bool(item.get("_remote")) or item.get("_city") == "Remote"
    return (item.get("_city") or "").lower() == (city or "").lower()


class FixtureApify:
    """Implements the ApifyClient surface used by the runner."""

    _runs: dict[str, tuple[str, list[dict]]] = {}

    def __init__(self, token: str | None = None):
        self.token = token  # ignored: fixtures never touch Apify

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def start(self, actor: str, input: dict, memory_mb: int, max_total_charge_usd: float) -> dict:
        platform = PLATFORM_BY_ACTOR[actor]
        run_id = "fx_" + hashlib.sha1(json.dumps([actor, input], sort_keys=True).encode()).hexdigest()[:12]
        FixtureApify._runs[run_id] = (platform, self._select(platform, input))
        return {"id": run_id, "defaultDatasetId": run_id, "status": "RUNNING"}

    def _select(self, platform: str, input: dict) -> list[dict]:
        data = load_dataset(platform)
        if platform == LINKEDIN:
            urls = input["urls"]
            parsed = []
            for u in urls:
                q = parse_qs(urlsplit(u).query)
                loc = (q.get("location") or [""])[0].split(",")[0]
                parsed.append((u, loc, "f_WT" in q))
            out = []
            for item in data:
                matches = [u for u, loc, remote in parsed if _city_matches(item, loc, remote)]
                pick = matches[int(item["id"]) % len(matches)] if matches else urls[0]
                out.append(_materialize(platform, item) | {"inputUrl": pick})
            return out
        if platform == NAUKRI:
            remote = bool(input.get("wfhType"))
            return [_materialize(platform, i) for i in data if _city_matches(i, input.get("location"), remote)]
        remote = input.get("location") == "remote"
        return [_materialize(platform, i) for i in data if _city_matches(i, input.get("location"), remote)]

    async def wait(self, run_id: str, should_stop=None) -> dict:
        platform, items = FixtureApify._runs[run_id]
        return {"id": run_id, "status": "SUCCEEDED", "defaultDatasetId": run_id,
                "usageTotalUsd": round(len(items) * PRICE_PER_ITEM[platform], 5)}

    async def items(self, dataset_id: str) -> list[dict]:
        return FixtureApify._runs[dataset_id][1]

    async def abort(self, run_id: str) -> None:
        return None

    async def limits(self) -> dict:
        return {"current": {"monthlyUsageUsd": 0.42}, "limits": {"maxMonthlyUsageUsd": 5.0}}


def _page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


class FixtureVerifier:
    """Runs the real page classifiers against recorded pages chosen by each fixture's `_demo_status`."""

    LINKEDIN_PAGES = {"offsite": "linkedin_offsite.html", "easy": "linkedin_easy_apply.html",
                      "closed": "linkedin_closed.html", "uncertain": "linkedin_unknown.html"}
    NAUKRI_PAGES = {"active": "naukri_active.txt", "expired": "naukri_expired.txt", "captcha": "naukri_captcha.txt"}
    EMPLOYER_PAGES = {"active": "employer_active.html", "closed": "employer_closed.html",
                      "remote_us": "employer_remote_us.html"}

    def __init__(self):
        self.li = {str(i["id"]): i["_demo_status"] for i in load_dataset("linkedin")}
        self.nk = {i["url"]: i["_demo_status"] for i in load_dataset("naukri")}
        self.ind = {i["jobUrl"]: i["_demo_status"] for i in load_dataset("indeed")}

    async def aclose(self) -> None:
        return None

    async def linkedin(self, job_id: str) -> dict:
        page = self.LINKEDIN_PAGES.get(self.li.get(job_id, "uncertain"), "linkedin_unknown.html")
        c = classify_linkedin(_page(page))
        return result(c["status"], "linkedin_guest_api (fixture)", c.get("easy_apply"), fixture=page,
                      http_status=200, matched=c["matched"], posted_time_ago=c.get("posted_time_ago"),
                      applicants=c.get("applicants"))

    async def naukri(self, listing_url: str | None) -> dict:
        page = self.NAUKRI_PAGES.get(self.nk.get(listing_url or "", ""), "naukri_captcha.txt")
        c = classify_naukri_text(_page(page))
        return result(c["status"], "naukri_playwright (fixture)", fixture=page, url=listing_url,
                      matched=c["matched"], reason=c.get("reason"), posted=c.get("posted"))

    async def indeed(self, expired: bool, employer_url: str | None) -> dict:
        if expired:
            return result("inactive", "indeed_scraped_flag", matched=["expired == true"])
        if not employer_url:
            return result("uncertain", "indeed_employer_page (fixture)",
                          reason="no employer jobUrl (Indeed-hosted apply)")
        page = self.EMPLOYER_PAGES.get(self.ind.get(employer_url, ""), "employer_active.html")
        c = classify_employer_page(_page(page), 200)
        return result(c["status"], "indeed_employer_page (fixture)", fixture=page, url=employer_url,
                      matched=c["matched"], reason=c.get("reason"))


def demo_profile() -> dict:
    return json.loads((FIXTURES / "demo_profile.json").read_text(encoding="utf-8"))


def demo_resume_text() -> str:
    return (FIXTURES / "demo_resume.txt").read_text(encoding="utf-8")


def fixture_path(name: str) -> Path:
    return FIXTURES / name
