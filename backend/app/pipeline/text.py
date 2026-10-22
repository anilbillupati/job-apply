"""Text helpers shared by the normalizers: HTML stripping, experience, city and date parsing."""

import html
import re
from datetime import UTC, date, datetime, timedelta

CITIES = ["Hyderabad", "Bengaluru", "Chennai", "Pune"]
REMOTE = "Remote-India"

_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr)\b[^>]*>", re.I)
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = _BLOCK.sub("\n", value)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = "\n".join(_WS.sub(" ", line).strip() for line in text.splitlines())
    return _NL.sub("\n\n", text).strip()


# The spec's experience regex: captures the minimum of "3-5 years", "3+ yrs", "3 to 5 years".
EXP_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*\d{0,2}\s*\+?\s*(?:years|yrs)", re.I)
EXP_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years|yrs)", re.I)


def parse_experience(text: str | None) -> tuple[float | None, float | None]:
    """Return (min, max) years. Uses the smallest plausible minimum below 16."""
    if not text:
        return None, None
    mins = [int(m.group(1)) for m in EXP_RE.finditer(text)]
    mins = [m for m in mins if m < 16]
    if not mins:
        return None, None
    lo = min(mins)
    hi = None
    for m in EXP_RANGE_RE.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if a == lo and b > a and b < 31:
            hi = b
            break
    return float(lo), (float(hi) if hi is not None else None)


_CITY_PATTERNS = [
    ("Hyderabad", re.compile(r"hyderabad|telangana|secunderabad|\bHYD\b", re.I)),
    ("Bengaluru", re.compile(r"bengaluru|bangalore|\bBLR\b", re.I)),
    ("Chennai", re.compile(r"chennai|\bMAA\b", re.I)),
    ("Pune", re.compile(r"\bpune\b", re.I)),
]


def map_cities(*texts: str | None) -> list[str]:
    """All in-scope cities mentioned (order of first appearance across CITIES)."""
    joined = " | ".join(t for t in texts if t)
    return [city for city, pat in _CITY_PATTERNS if pat.search(joined)]


def map_city(*texts: str | None) -> str | None:
    found = map_cities(*texts)
    return found[0] if found else None


_REL = re.compile(r"(\d+)\+?\s*(minute|min|hour|hr|day|week|month)s?\s*ago", re.I)


def parse_date(value, today: date | None = None) -> date | None:
    """Parse ISO strings, epoch millis/seconds, and relative strings like '3 days ago'."""
    today = today or datetime.now(UTC).date()
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts, UTC).date()
    s = str(value).strip()
    if s.isdigit():
        return parse_date(int(s), today)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    low = s.lower()
    if any(w in low for w in ("just now", "today", "few hours", "hour ago", "minutes ago")):
        return today
    if "yesterday" in low:
        return today - timedelta(days=1)
    m = _REL.search(low)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"minute": 0, "min": 0, "hour": 0, "hr": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
        return today - timedelta(days=days)
    for fmt in ("%d %b %Y", "%b %d, %Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def first(*values):
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def dig(obj, *path, default=None):
    """Safe nested get: dig(d, 'company', 'name')."""
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int) and -len(cur) <= key < len(cur):
            cur = cur[key]
        else:
            return default
        if cur is None:
            return default
    return cur
