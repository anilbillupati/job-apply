"""Hard filters. Each returns a reason code, or None when the job passes."""

import re
from dataclasses import dataclass, field

from app.pipeline.text import REMOTE

AGENCY_NAME_RE = re.compile(r"recruit|staffing|talent|consultancy|placement|manpower|\bhr solutions?\b", re.I)

NON_SENIOR_PHRASES = re.compile(r"member of (the )?technical staff|\bmts\b", re.I)

REASONS = {
    "location": "Location not in scope",
    "work_arrangement": "Work arrangement mismatch",
    "agency": "Agency / staffing / marketplace",
    "seniority": "Title seniority",
    "irrelevant_title": "Irrelevant title",
    "exp_too_high": "Minimum experience too high",
    "exp_too_low": "Maximum experience below 2 years",
}


@dataclass
class FilterConfig:
    cities: list[str]
    include_remote: bool
    work_arrangement: str  # any | remote_only | office_or_hybrid
    candidate_years: float
    agency_blocklist: list[str] = field(default_factory=list)
    title_exclusions: list[str] = field(default_factory=list)
    seniority_exclusions: list[str] = field(default_factory=list)
    allow_senior_max_years: float | None = None


def _term_re(term: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(term.lower().strip()) + r"(?![a-z0-9+#])", re.I)


def title_has_any(title: str, terms: list[str]) -> str | None:
    low = title.lower()
    for term in terms:
        if term.strip() and _term_re(term).search(low):
            return term
    return None


def is_agency(company: str, agency_signal: bool, blocklist: list[str], allowlist: list[str] | None = None) -> bool:
    low = (company or "").lower()
    if any(a.strip() and a.lower().strip() in low for a in allowlist or []):
        return False  # e.g. "Tata Consultancy Services" matches the name regex but is an employer
    if agency_signal:
        return True
    if company and AGENCY_NAME_RE.search(company):
        return True
    return any(b.strip() and b.lower().strip() in low for b in blocklist)


def resolve_city(cities_found: list[str], is_remote: bool, selected: list[str], include_remote: bool) -> str | None:
    """Pick the job's city: the first matching selected city, else Remote-India for remote jobs."""
    for c in cities_found:
        if c in selected:
            return c
    if is_remote and include_remote:
        return REMOTE
    return cities_found[0] if cities_found else (REMOTE if is_remote else None)


def check(job, cfg: FilterConfig) -> str | None:
    """Return the first failing reason code for a normalized Job, or None."""
    in_city = job.city in cfg.cities
    remote_ok = job.is_remote and cfg.include_remote
    if not (in_city or remote_ok):
        return "location"
    if cfg.work_arrangement == "remote_only" and not job.is_remote:
        return "work_arrangement"
    if cfg.work_arrangement == "office_or_hybrid" and job.work_mode == "remote" and not in_city:
        return "work_arrangement"

    if job.is_agency:
        return "agency"

    # "Member of Technical Staff" is a mid-level title, not a Staff-level one.
    hit = title_has_any(NON_SENIOR_PHRASES.sub(" ", job.title), cfg.seniority_exclusions)
    if hit:
        senior_word = hit.lower() in ("senior", "sr")
        upper = job.exp_max if job.exp_max is not None else job.exp_min
        allowed = (
            senior_word
            and cfg.allow_senior_max_years is not None
            and upper is not None
            and upper <= cfg.allow_senior_max_years
            and not title_has_any(job.title, [t for t in cfg.seniority_exclusions if t.lower() not in ("senior", "sr")])
        )
        if not allowed:
            return "seniority"

    if title_has_any(job.title, cfg.title_exclusions):
        return "irrelevant_title"

    if job.exp_min is not None and job.exp_min >= cfg.candidate_years + 2.5:
        return "exp_too_high"
    if job.exp_max is not None and job.exp_max < 2:
        return "exp_too_low"
    return None
