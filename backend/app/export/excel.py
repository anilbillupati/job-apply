"""Excel export: one 'Ranked Opportunities' sheet, plus an optional full report."""

import io
from collections import Counter

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.llm.scoring import RUBRIC_LABELS
from app.scrapers.platforms import PLATFORM_LABEL

FILENAME = "LinkedIn_Naukri_Indeed_Ranked_Opportunities.xlsx"
SHEET = "Ranked Opportunities"

COLUMNS: list[tuple[str, int]] = [
    ("Match Score (%)", 12),
    ("Job Title", 34),
    ("Company", 26),
    ("Source Platform", 14),
    ("Company Tier", 30),
    ("Location", 22),
    ("Posted Date", 13),
    ("Experience Match Summary", 40),
    ("Key Skills Match", 48),
    ("Why This Fits Me", 56),
    ("Application Link", 42),
    ("Notes / Concerns", 48),
]

FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name=FONT, size=10)
LINK_FONT = Font(name=FONT, size=10, color="0563C1", underline="single")
ALT_FILL = PatternFill("solid", fgColor="EEF3FA")
WHITE_FILL = PatternFill("solid", fgColor="FFFFFF")
THIN = Side(style="thin", color="D0D7E2")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")


def application_link(job) -> str | None:
    """Indeed links to the employer's jobUrl; LinkedIn and Naukri link to the listing."""
    if job.platform == "indeed":
        return job.employer_url or job.listing_url
    return job.listing_url


def location_label(job) -> str:
    if job.city == "Remote-India":
        return "Remote (India)"
    label = job.city or job.location_text or "Not stated"
    if job.is_remote and job.city:
        label += " (Remote)"
    elif job.work_mode == "hybrid":
        label += " (Hybrid)"
    return label


def notes_text(job) -> str:
    parts = []
    note = (job.score.notes or "").strip() if job.score else ""
    if note and note.lower() not in ("none", "none."):
        parts.append(note)
    if job.alt_sources:
        alts = "; ".join(
            f"{PLATFORM_LABEL.get(a['platform'], a['platform'])}: {a.get('url') or 'n/a'}" for a in job.alt_sources
        )
        parts.append(f"Also listed on {alts}")
    if job.applicants_text:
        parts.append(job.applicants_text)
    return "\n".join(parts) or "None"


def row_values(job) -> list:
    s = job.score
    return [
        s.total / 100,
        job.title,
        job.company or "Not stated",
        PLATFORM_LABEL.get(job.platform, job.platform),
        s.company_tier,
        location_label(job),
        job.posted_date.isoformat() if job.posted_date else "Not stated",
        s.experience_summary,
        s.key_skills_match,
        s.why_fits,
        application_link(job) or "",
        notes_text(job),
    ]


def _header(ws: Worksheet, columns: list[tuple[str, int]]) -> None:
    for idx, (name, width) in enumerate(columns, start=1):
        c = ws.cell(row=1, column=idx, value=name)
        c.font, c.fill, c.border = HEADER_FONT, HEADER_FILL, BORDER
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def _body_style(ws: Worksheet, n_rows: int, n_cols: int, link_col: int | None = None, pct_col: int | None = None):
    for r in range(2, n_rows + 2):
        fill = ALT_FILL if r % 2 == 0 else WHITE_FILL
        for col in range(1, n_cols + 1):
            c = ws.cell(row=r, column=col)
            c.font, c.fill, c.border, c.alignment = BODY_FONT, fill, BORDER, WRAP
            if col == pct_col:
                c.number_format = "0%"
                c.alignment = Alignment(horizontal="center", vertical="top")
            if col == link_col and c.value:
                c.hyperlink = str(c.value)
                c.font = LINK_FONT


def write_ranked_sheet(ws: Worksheet, jobs: list) -> None:
    ws.title = SHEET
    _header(ws, COLUMNS)
    jobs = sorted(jobs, key=lambda j: -j.score.total)
    for job in jobs:
        ws.append(row_values(job))
    _body_style(ws, len(jobs), len(COLUMNS), link_col=11, pct_col=1)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(len(jobs) + 1, 1)}"


def _simple_sheet(
    wb: Workbook, title: str, columns: list[tuple[str, int]], rows: list[list], pct_col=None, link_col=None
) -> None:
    ws = wb.create_sheet(title)
    _header(ws, columns)
    for r in rows:
        ws.append(r)
    _body_style(ws, len(rows), len(columns), link_col=link_col, pct_col=pct_col)
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(len(rows) + 1, 1)}"


def _top_rows(jobs: list) -> list[list]:
    return [
        [
            j.score.total / 100,
            j.title,
            j.company,
            PLATFORM_LABEL.get(j.platform, j.platform),
            j.score.category.title(),
            j.score.why_fits,
            application_link(j) or "",
        ]
        for j in jobs
    ]


TOP_COLS = [
    ("Match Score (%)", 12),
    ("Job Title", 34),
    ("Company", 26),
    ("Source Platform", 14),
    ("Category", 11),
    ("Why This Fits Me", 60),
    ("Application Link", 42),
]


def build_workbook(jobs: list, full: bool = False, run=None, profile: dict | None = None) -> bytes:
    wb = Workbook()
    write_ranked_sheet(wb.active, jobs)

    if full:
        ranked = sorted(jobs, key=lambda j: -j.score.total)
        strongest = ranked[:5]
        stretch = [j for j in ranked if j.score.category == "stretch"][:5]

        def probability(j):
            # Highest-probability: safe/strong fits, fewer applicants, recent postings.
            cat = {"safe": 2, "strong": 1}.get(j.score.category, 0)
            applicants = 0
            if j.applicants_text:
                digits = "".join(ch for ch in j.applicants_text if ch.isdigit())
                applicants = int(digits) if digits else 0
            return (cat, j.score.total - min(applicants, 500) / 25)

        likely = sorted(jobs, key=probability, reverse=True)[:5]
        _simple_sheet(wb, "Top 5 Strongest", TOP_COLS, _top_rows(strongest), pct_col=1, link_col=7)
        _simple_sheet(wb, "Top 5 Stretch", TOP_COLS, _top_rows(stretch), pct_col=1, link_col=7)
        _simple_sheet(wb, "Top 5 Highest-Probability", TOP_COLS, _top_rows(likely), pct_col=1, link_col=7)

        rows: list[list] = []
        for label, counter in (
            ("Platform", Counter(PLATFORM_LABEL.get(j.platform, j.platform) for j in jobs)),
            ("City", Counter(location_label(j) for j in jobs)),
            ("Company tier", Counter(j.score.company_tier for j in jobs)),
            ("Category", Counter(j.score.category for j in jobs)),
        ):
            for key, n in counter.most_common():
                rows.append([label, key, n])
        gaps: Counter = Counter()
        for j in jobs:
            for part in (j.score.key_skills_match or "").split(";"):
                part = part.strip()
                if part.lower().startswith("gap:"):
                    gaps[part[4:].strip()] += 1
        for skill, n in gaps.most_common(15):
            rows.append(["Most common skill gap", skill, n])
        if jobs:
            avg = {k: round(sum(j.score.breakdown.get(k, 0) for j in jobs) / len(jobs), 1) for k in RUBRIC_LABELS}
            for k, v in avg.items():
                rows.append(["Average score: " + RUBRIC_LABELS[k], "", v])
        _simple_sheet(wb, "Market Analysis", [("Dimension", 30), ("Value", 46), ("Count / Avg", 14)], rows)

        audit: list[list] = []
        if run is not None:
            p = run.progress or {}
            c = p.get("counts", {})
            audit += [["Collected (raw items)", c.get("collected", 0)], ["Unique listings", c.get("unique", 0)]]
            for reason, n in (c.get("filtered") or {}).items():
                audit.append([f"Filtered out: {reason}", n])
            audit += [
                ["Passed filters", c.get("passed_filters", 0)],
                ["Duplicates merged", c.get("duplicates_merged", 0)],
                ["After dedupe", c.get("after_dedupe", 0)],
                ["Pre-score ≥ 60 (verified)", c.get("prescore_ge_60", 0)],
            ]
            for k, n in (c.get("verified") or {}).items():
                audit.append([f"Verification: {k}", n])
            audit += [
                ["Scored", c.get("scored", 0)],
                ["Below min score", c.get("below_min_score", 0)],
                ["Final ranked", c.get("final", len(jobs))],
            ]
            cost = p.get("cost", {})
            for platform, usd in (cost.get("apify") or {}).items():
                audit.append([f"Apify cost: {PLATFORM_LABEL.get(platform, platform)} (USD)", usd])
            audit.append(["LLM cost (USD)", cost.get("llm", 0)])
            audit.append(["Keywords", ", ".join(k for v in (run.keywords or {}).values() for k in v)])
            remote = " + Remote (India)" if run.include_remote_india else ""
            audit.append(["Locations", ", ".join(run.locations or []) + remote])
            audit.append(["Posted within (days)", run.posted_within_days])
            audit.append(["Min score", run.min_score])
        _simple_sheet(wb, "Search Audit", [("Stage", 40), ("Value", 60)], audit)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
