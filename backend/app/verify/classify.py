"""Pure page classifiers for verification. Each returns {status, easy_apply?, matched[], ...}."""

import re

from app.pipeline.text import strip_html

ACTIVE, UNCERTAIN, INACTIVE = "verified_active", "uncertain", "inactive"

# ------------------------------------------------------------------ LinkedIn

_LI_POSTED = re.compile(r'posted-time-ago__text[^"]*"[^>]*>\s*([^<]+?)\s*<', re.I)
_LI_APPLICANTS = re.compile(r'num-applicants__(?:caption|figure)[^"]*"[^>]*>\s*([^<]+?)\s*<', re.I)


def classify_linkedin(html: str) -> dict:
    out: dict = {"matched": []}
    m = _LI_POSTED.search(html)
    out["posted_time_ago"] = m.group(1).strip() if m else None
    m = _LI_APPLICANTS.search(html)
    out["applicants"] = m.group(1).strip() if m else None

    if "No longer accepting applications" in html:
        out.update(status=INACTIVE, easy_apply=None)
        out["matched"].append("No longer accepting applications")
    elif "apply-link-offsite" in html:
        out.update(status=ACTIVE, easy_apply=False)
        out["matched"].append("apply-link-offsite")
    elif "apply-link-onsite" in html:
        out.update(status=ACTIVE, easy_apply=True)
        out["matched"].append("apply-link-onsite")
    else:
        out.update(status=UNCERTAIN, easy_apply=None)
    return out


# ------------------------------------------------------------------ Naukri

_BLOCKED = re.compile(
    r"captcha|are you a robot|access denied|unusual traffic|verify you are (a )?human|request blocked|"
    r"pardon our interruption",
    re.I,
)
_NAUKRI_CLOSED = re.compile(r"\bexpired\b|no longer (available|accepting)|job (has been )?removed", re.I)
_NAUKRI_APPLY = re.compile(r"\b(apply|apply on company site|i am interested)\b", re.I)


def classify_naukri_text(text: str) -> dict:
    out: dict = {"matched": []}
    m = _BLOCKED.search(text)
    if m:
        out.update(status=UNCERTAIN, reason="captcha_or_block")
        out["matched"].append(m.group(0))
        return out
    m = _NAUKRI_CLOSED.search(text)
    if m:
        out.update(status=INACTIVE)
        out["matched"].append(m.group(0))
        return out
    posted = re.search(r"Posted:\s*([^\n|]{1,40})", text)
    apply = _NAUKRI_APPLY.search(text)
    if posted and apply:
        out.update(status=ACTIVE, posted=posted.group(1).strip())
        out["matched"] += [posted.group(0).strip(), apply.group(0)]
    else:
        out.update(status=UNCERTAIN, reason="markers_missing")
    return out


# ------------------------------------------------------------------ Indeed employer page

_CLOSED = re.compile(
    r"no longer available|position (has been )?filled|job (is |has been )?closed|no longer accepting|"
    r"(this )?job (posting )?has expired|posting (has )?closed|job not found|this position is closed",
    re.I,
)
_OUT_OF_SCOPE = re.compile(
    r"(remote|work from home)\s*[-–—(:]?\s*(us|usa|u\.s\.|united states|uk|europe|eu|canada|emea|latam)\s*only|"
    r"\b(us|usa|united states|uk|canada|europe)[- ]only\b|must (be located|reside) in the (us|united states|uk)",
    re.I,
)
_APPLY = re.compile(r"\bapply( now| for this job| online| today)?\b", re.I)
_JS_ONLY = re.compile(r"enable javascript|requires javascript|javascript is (disabled|required)", re.I)


def page_text(html: str) -> str:
    cleaned = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", html, flags=re.I | re.S)
    return strip_html(cleaned)


def classify_employer_page(html: str, http_status: int | None = 200) -> dict:
    out: dict = {"matched": []}
    if http_status is None or http_status >= 400:
        out.update(status=UNCERTAIN, reason=f"unreachable (HTTP {http_status})")
        return out
    text = page_text(html)
    m = _CLOSED.search(text)
    if m:
        out.update(status=INACTIVE)
        out["matched"].append(m.group(0))
        return out
    m = _OUT_OF_SCOPE.search(text)
    if m:
        out.update(status=UNCERTAIN, reason="location_out_of_scope")
        out["matched"].append(m.group(0))
        return out
    if len(text) < 300 or _JS_ONLY.search(text):
        out.update(status=UNCERTAIN, reason="js_only_page")
        return out
    m = _APPLY.search(text)
    if m:
        out.update(status=ACTIVE)
        out["matched"].append(m.group(0))
    else:
        out.update(status=UNCERTAIN, reason="no_apply_text")
    return out
