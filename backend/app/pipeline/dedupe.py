"""Cross-platform duplicate detection."""

import re
from collections import defaultdict

from rapidfuzz import fuzz

COMPANY_STOPWORDS = re.compile(
    r"\b(pvt|private|ltd|limited|inc|llc|llp|india|technologies|technology|solutions|corp|corporation|co)\b",
    re.I,
)
_PARENS = re.compile(r"[\(\[\{].*?[\)\]\}]")
_SUFFIX_SPLIT = re.compile(r"\s+[-–—|/:]\s+|\s*[|:]\s*|,\s*")
_NON_ALNUM = re.compile(r"[^a-z0-9]")

FUZZ_THRESHOLD = 85


def normalize_company(name: str) -> str:
    return _NON_ALNUM.sub("", COMPANY_STOPWORDS.sub(" ", (name or "").lower()))


def normalize_title(title: str) -> str:
    t = _PARENS.sub(" ", (title or "").lower())
    t = _SUFFIX_SPLIT.split(t, maxsplit=1)[0]
    return _NON_ALNUM.sub("", t)


def dedupe_key(company: str, title: str) -> str:
    return f"{normalize_company(company)}|{normalize_title(title)}"


def is_same_job(a, b) -> bool:
    """Confirm a key match with description similarity and the same city (two remote listings also match)."""
    if (a.city or "") != (b.city or "") and not (a.is_remote and b.is_remote):
        return False
    if not a.description or not b.description:
        return False
    return fuzz.token_set_ratio(a.description[:6000], b.description[:6000]) >= FUZZ_THRESHOLD


def verifiability(job, verified: dict[int, str]) -> tuple:
    """Higher is better: prefer verified jobs, then the most checkable apply route."""
    status_rank = {"verified_active": 2, "uncertain": 1}.get(verified.get(job.id, ""), 0)
    route = {"linkedin": 3, "indeed": 2 if job.employer_url else 0, "naukri": 1}.get(job.platform, 0)
    return (status_rank, route, len(job.description or ""), -(job.id or 0))


def find_duplicates(jobs: list, verified: dict[int, str] | None = None) -> dict[int, list]:
    """Group jobs into clusters. Returns {primary_id: [duplicate jobs]}."""
    verified = verified or {}
    by_key: dict[str, list] = defaultdict(list)
    for j in jobs:
        if j.dedupe_key and not j.dedupe_key.startswith("|") and not j.dedupe_key.endswith("|"):
            by_key[j.dedupe_key].append(j)

    clusters: dict[int, list] = {}
    for group in by_key.values():
        if len(group) < 2:
            continue
        parent = {j.id: j.id for j in group}

        def root(x, parent=parent):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a.platform == b.platform and a.platform_job_id == b.platform_job_id:
                    continue
                if is_same_job(a, b):
                    parent[root(a.id)] = root(b.id)

        comps: dict[int, list] = defaultdict(list)
        for j in group:
            comps[root(j.id)].append(j)
        for members in comps.values():
            if len(members) < 2:
                continue
            members.sort(key=lambda j: verifiability(j, verified), reverse=True)
            clusters[members[0].id] = members[1:]
    return clusters
