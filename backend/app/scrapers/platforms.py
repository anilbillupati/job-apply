"""Apify actor definitions per platform: input builders, cost estimates and output mappers."""

from dataclasses import dataclass, field
from urllib.parse import quote, quote_plus

from app.pipeline.text import (
    REMOTE,
    dig,
    first,
    map_cities,
    parse_date,
    parse_experience,
    strip_html,
)

LINKEDIN, NAUKRI, INDEED = "linkedin", "naukri", "indeed"
PLATFORMS = [LINKEDIN, NAUKRI, INDEED]

ACTORS = {
    LINKEDIN: "curious_coder~linkedin-jobs-scraper",
    NAUKRI: "valig~naukri-jobs-scraper",
    INDEED: "valig~indeed-jobs-scraper",
}
PRICE_PER_ITEM = {LINKEDIN: 0.002, NAUKRI: 0.0004, INDEED: 0.0001}
MEMORY_MB = {LINKEDIN: 512, NAUKRI: 256, INDEED: 256}
PLATFORM_LABEL = {LINKEDIN: "LinkedIn", NAUKRI: "Naukri", INDEED: "Indeed"}

LINKEDIN_LOCATIONS = {
    "Hyderabad": "Hyderabad, Telangana, India",
    "Bengaluru": "Bengaluru, Karnataka, India",
    "Chennai": "Chennai, Tamil Nadu, India",
    "Pune": "Pune, Maharashtra, India",
}

LINKEDIN_PER_SOURCE = 25
NAUKRI_LIMIT = 40
INDEED_LIMIT = 40


@dataclass
class TaskSpec:
    platform: str
    actor_id: str
    input: dict
    memory_mb: int
    est_items: int
    query_meta: dict = field(default_factory=dict)

    @property
    def est_cost(self) -> float:
        return self.est_items * PRICE_PER_ITEM[self.platform]


def linkedin_url(keyword: str, location: str | None, window_days: int, remote: bool = False) -> str:
    tpr = "r1209600" if window_days >= 14 else "r604800"
    loc = "India" if remote else location
    url = (
        f"https://www.linkedin.com/jobs/search/?keywords={quote_plus(keyword)}"
        f"&location={quote(loc or 'India')}&f_TPR={tpr}&f_E=2%2C3%2C4"
    )
    if remote:
        url += "&f_WT=2"
    return url


def build_tasks(
    platform: str,
    keywords: list[str],
    cities: list[str],
    include_remote: bool,
    window_days: int,
    candidate_years: float,
    depth: int = 1,
) -> list[TaskSpec]:
    """Build the Apify runs for one platform. `depth` > 1 pages further (Expand search step 3)."""
    targets: list[tuple[str | None, bool]] = [(c, False) for c in cities]
    if include_remote:
        targets.append((None, True))

    if platform == LINKEDIN:
        urls, meta = [], {}
        for kw in keywords:
            for city, remote in targets:
                url = linkedin_url(kw, LINKEDIN_LOCATIONS.get(city or "", city), window_days, remote)
                urls.append(url)
                meta[url] = {"keyword": kw, "location": REMOTE if remote else city, "remote": remote}
        if not urls:
            return []
        per_source = LINKEDIN_PER_SOURCE * depth
        return [TaskSpec(
            LINKEDIN, ACTORS[LINKEDIN],
            {"urls": urls, "limitPerSource": per_source, "scrapeCompany": True},
            MEMORY_MB[LINKEDIN], per_source * len(urls), meta,
        )]

    tasks: list[TaskSpec] = []
    for kw in keywords:
        for city, remote in targets:
            meta = {"*": {"keyword": kw, "location": REMOTE if remote else city, "remote": remote}}
            if platform == NAUKRI:
                limit = NAUKRI_LIMIT * depth
                inp = {
                    "keywords": kw,
                    "jobAge": "15" if window_days >= 14 else "7",
                    "experience": int(round(candidate_years)),
                    "limit": limit,
                }
                if remote:
                    inp["wfhType"] = ["2"]
                else:
                    inp["location"] = city.lower()
            elif platform == INDEED:
                limit = INDEED_LIMIT * depth
                inp = {
                    "country": "in",
                    "title": kw,
                    "location": "remote" if remote else city,
                    "datePosted": "14" if window_days >= 14 else "7",
                    "limit": limit,
                }
            else:
                raise ValueError(platform)
            tasks.append(TaskSpec(platform, ACTORS[platform], inp, MEMORY_MB[platform], limit, meta))
    return tasks


# ---------------------------------------------------------------- output mapping

def item_id(platform: str, item: dict) -> str | None:
    key = {LINKEDIN: "id", NAUKRI: "id", INDEED: "key"}[platform]
    value = item.get(key) or item.get("jobId") or item.get("id")
    return str(value) if value not in (None, "") else None


def item_query(item: dict, query_meta: dict) -> dict:
    """Find which keyword/location produced this item (LinkedIn batches many URLs into one run)."""
    if "*" in query_meta:
        return query_meta["*"]
    url = item.get("inputUrl")
    if url and url in query_meta:
        return query_meta[url]
    return {"keyword": None, "location": None, "remote": False}


def _salary_text(value) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        lo, hi = first(value.get("min"), value.get("minValue")), first(value.get("max"), value.get("maxValue"))
        unit = first(value.get("unitOfWork"), value.get("unit"), "")
        cur = first(value.get("currencyCode"), value.get("currency"), "")
        if lo or hi:
            fmt = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)  # noqa: E731
            rng = " – ".join(fmt(v) for v in (lo, hi) if v)
            return f"{cur} {rng} {str(unit).lower()}".strip()
        return first(value.get("label"), value.get("text"))
    return str(value)


def _work_mode_from_text(text: str) -> str:
    low = text.lower()
    if "remote" in low or "work from home" in low:
        return "remote"
    if "hybrid" in low:
        return "hybrid"
    return "unknown"


def map_item(platform: str, item: dict, is_remote_query: bool) -> dict:
    """Map an actor output item to normalized Job fields (plus agency signal)."""
    if platform == LINKEDIN:
        jid = item_id(platform, item)
        desc = item.get("descriptionText") or strip_html(item.get("descriptionHtml"))
        location = item.get("location") or ""
        industries = item.get("industries") or ""
        if isinstance(industries, list):
            industries = ", ".join(map(str, industries))
        is_remote = bool(is_remote_query)
        exp_min, exp_max = parse_experience(desc)
        listing = item.get("link") or (f"https://www.linkedin.com/jobs/view/{jid}" if jid else None)
        listing = listing.split("?")[0] if listing else None
        return dict(
            title=item.get("title") or "",
            company=item.get("companyName") or "",
            location_text=location,
            cities=map_cities(location),
            is_remote=is_remote,
            work_mode="remote" if is_remote else _work_mode_from_text(location),
            posted_date=parse_date(first(item.get("postedAt"), item.get("postedDate"))),
            description=desc or "",
            exp_min=exp_min,
            exp_max=exp_max,
            salary_text=_salary_text(item.get("salary") or item.get("salaryInfo")),
            listing_url=listing,
            apply_url=item.get("applyUrl") or None,
            employer_url=item.get("companyWebsite") or None,
            applicants_text=str(item["applicantsCount"]) + " applicants" if item.get("applicantsCount") else None,
            agency_signal="staffing and recruiting" in industries.lower(),
            extra={
                "seniorityLevel": item.get("seniorityLevel"),
                "employmentType": item.get("employmentType"),
                "industries": industries,
                "companyEmployeesCount": item.get("companyEmployeesCount"),
            },
        )

    if platform == NAUKRI:
        desc = strip_html(first(dig(item, "description", "full"), dig(item, "description", "text"),
                                item.get("description") if isinstance(item.get("description"), str) else None))
        loc_labels = [loc.get("label") if isinstance(loc, dict) else str(loc) for loc in item.get("locations") or []]
        location = ", ".join(x for x in loc_labels if x)
        wfh = str(item.get("wfhType", "")).strip()
        exp_min = dig(item, "experience", "minimum")
        exp_max = dig(item, "experience", "maximum")
        if exp_min is None:
            exp_min, exp_max = parse_experience(desc)
        company_apply = item.get("companyApplyJob")
        if isinstance(company_apply, str):
            apply_url = company_apply
        elif isinstance(company_apply, dict):
            apply_url = company_apply.get("url")
        else:
            apply_url = None
        apply_count = item.get("applyCount")
        return dict(
            title=item.get("title") or "",
            company=dig(item, "company", "name") or "",
            location_text=location,
            cities=map_cities(location),
            is_remote=wfh == "2",
            work_mode={"0": "office", "2": "remote", "3": "hybrid"}.get(wfh, "unknown"),
            posted_date=parse_date(first(item.get("createdDate"), item.get("createdDateText"))),
            description=desc,
            exp_min=float(exp_min) if exp_min is not None else None,
            exp_max=float(exp_max) if exp_max is not None else None,
            salary_text=_salary_text(dig(item, "salary", "label") or item.get("salary")),
            listing_url=item.get("url") or item.get("jdURL"),
            apply_url=apply_url,
            employer_url=apply_url,
            applicants_text=f"{apply_count} applicants" if apply_count else None,
            agency_signal=bool(item.get("consultant")),
            extra={"wfhType": wfh, "createdDateText": item.get("createdDateText")},
        )

    if platform == INDEED:
        desc = first(dig(item, "description", "text"), strip_html(dig(item, "description", "html")))
        if desc is None and isinstance(item.get("description"), str):
            desc = strip_html(item["description"])
        loc = item.get("location") or {}
        if isinstance(loc, str):
            loc = {"formatted": loc}
        parts = [loc.get("city"), loc.get("admin1Code"), loc.get("admin3Code"), loc.get("formatted"),
                 dig(loc, "formatted", "long") if isinstance(loc.get("formatted"), dict) else None]
        location_text = ", ".join(str(p) for p in parts if p and not isinstance(p, dict))
        attrs = item.get("employerAttributes") or item.get("attributes") or []
        attr_text = " ".join(a.get("label", "") if isinstance(a, dict) else str(a) for a in attrs)
        is_remote = "remote" in attr_text.lower()
        exp_min, exp_max = parse_experience(desc)
        employer_url = item.get("jobUrl") or None
        if employer_url and "indeed." in employer_url:
            employer_url = None
        return dict(
            title=item.get("title") or "",
            company=dig(item, "employer", "name") or item.get("companyName") or "",
            location_text=location_text,
            cities=map_cities(location_text),
            is_remote=is_remote,
            work_mode="remote" if is_remote else ("hybrid" if "hybrid" in attr_text.lower() else "unknown"),
            posted_date=parse_date(first(item.get("datePublished"), item.get("dateOnIndeed"))),
            description=desc or "",
            exp_min=exp_min,
            exp_max=exp_max,
            salary_text=_salary_text(item.get("baseSalary")),
            listing_url=item.get("url") or (
                f"https://in.indeed.com/viewjob?jk={item['key']}" if item.get("key") else None
            ),
            apply_url=employer_url,
            employer_url=employer_url,
            applicants_text=None,
            agency_signal=bool(item.get("isPlacement")),
            extra={"expired": bool(item.get("expired")), "isRepost": bool(item.get("isRepost")),
                   "attributes": attr_text},
        )
    raise ValueError(platform)
