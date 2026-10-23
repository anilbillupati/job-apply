"""Excel parser and importer for job listings.

Supports .xlsx, .xls, and .csv files with flexible column headers.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.export.excel import (
    ALT_FILL,
    BODY_FONT,
    BORDER,
    COLUMNS,
    HEADER_FILL,
    HEADER_FONT,
    LINK_FONT,
    WHITE_FILL,
    WRAP,
)
from app.models import Job, Resume, RunStatus, Score, SearchRun, Verification
from app.pipeline.text import CITIES

# Header synonyms mapped to canonical keys
HEADER_SYNONYMS: dict[str, list[str]] = {
    "score": [
        "match score (%)",
        "match score",
        "match_score",
        "score",
        "match %",
        "match percent",
        "fit score",
        "fit %",
        "match",
        "percentage",
    ],
    "title": ["job title", "title", "role", "position", "designation", "job name", "job"],
    "company": ["company", "company name", "organization", "organisation", "employer", "firm"],
    "platform": ["source platform", "platform", "source", "portal", "website", "job board", "source_platform"],
    "company_tier": ["company tier", "tier", "company category", "company rating"],
    "location": ["location", "city", "job location", "work location", "place", "location_text"],
    "posted_date": ["posted date", "date posted", "date", "posted", "posting date", "posted_on"],
    "experience_summary": [
        "experience match summary",
        "experience summary",
        "experience",
        "exp",
        "required experience",
        "years of experience",
        "exp summary",
    ],
    "key_skills_match": [
        "key skills match",
        "key skills",
        "skills",
        "tech stack",
        "skills match",
        "technologies",
        "matched skills",
    ],
    "why_fits": ["why this fits me", "why fits", "fit summary", "reason", "why fit", "fit notes", "match reason"],
    "listing_url": [
        "application link",
        "job url",
        "link",
        "url",
        "apply url",
        "listing url",
        "apply link",
        "job link",
        "career link",
    ],
    "notes": ["notes / concerns", "notes", "concerns", "comments", "user note", "note", "remarks"],
    "status": ["status", "application status", "state", "user state", "job status"],
    "description": ["description", "job description", "details", "summary", "overview"],
    "salary_text": ["salary", "compensation", "ctc", "pay", "package", "salary range"],
}


def _clean_header_name(text: str) -> str:
    cleaned = re.sub(r"[_\-]+", " ", str(text).lower().strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _map_headers(headers: list[str]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(headers):
        if not raw:
            continue
        cleaned = _clean_header_name(raw)
        matched = None
        for canonical, syns in HEADER_SYNONYMS.items():
            if cleaned == canonical or cleaned in syns:
                matched = canonical
                break
        if not matched:
            for canonical, syns in HEADER_SYNONYMS.items():
                if any(syn in cleaned for syn in syns):
                    matched = canonical
                    break
        if matched:
            mapping[idx] = matched
    return mapping


def _parse_score(val: Any) -> int:
    if val is None or val == "":
        return 75
    if isinstance(val, (int, float)):
        if 0.0 <= val <= 1.0:
            return int(round(val * 100))
        return max(0, min(100, int(round(val))))
    s = str(val).strip().rstrip("%").strip()
    try:
        f = float(s)
        if 0.0 <= f <= 1.0:
            return int(round(f * 100))
        return max(0, min(100, int(round(f))))
    except ValueError:
        return 75


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_platform(val: Any, link: str = "") -> str:
    if val:
        raw = str(val).strip().lower()
        if "linkedin" in raw:
            return "linkedin"
        if "naukri" in raw:
            return "naukri"
        if "indeed" in raw:
            return "indeed"
        if "glassdoor" in raw:
            return "glassdoor"
        if "hirist" in raw:
            return "hirist"
        if "instahyre" in raw:
            return "instahyre"
        if "wellfound" in raw or "angellist" in raw:
            return "wellfound"
        return raw
    link_l = (link or "").lower()
    if "linkedin.com" in link_l:
        return "linkedin"
    if "naukri.com" in link_l:
        return "naukri"
    if "indeed.com" in link_l:
        return "indeed"
    return "excel"


def _parse_status(val: Any) -> str | None:
    if not val:
        return None
    s = str(val).strip().lower()
    mapping = {
        "applied": "applied",
        "shortlisted": "shortlisted",
        "saved": "shortlisted",
        "interviewing": "interviewing",
        "interview": "interviewing",
        "offer": "offer",
        "offered": "offer",
        "rejected": "rejected",
        "declined": "rejected",
    }
    return mapping.get(s, None)


def _detect_city(location_text: str) -> str | None:
    loc_lower = location_text.lower()
    for city in CITIES:
        if city.lower() in loc_lower:
            return city
    if "remote" in loc_lower:
        return "Remote"
    return None


def parse_file_to_rows(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    fn_lower = filename.lower()
    raw_rows: list[list[Any]] = []

    if fn_lower.endswith(".csv"):
        text = None
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                text = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = file_bytes.decode("utf-8", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if any(cell.strip() for cell in row):
                raw_rows.append(row)
    else:
        wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            if any(cell is not None and str(cell).strip() != "" for cell in row):
                raw_rows.append([cell for cell in row])

    if not raw_rows:
        return []

    # Find the header row (the first row containing at least 2 recognized column keys)
    header_idx = 0
    header_mapping: dict[int, str] = {}
    for r_idx in range(min(5, len(raw_rows))):
        candidate_headers = [str(c or "").strip() for c in raw_rows[r_idx]]
        m = _map_headers(candidate_headers)
        if len(m) >= 2 or ("title" in m.values() or "company" in m.values()):
            header_idx = r_idx
            header_mapping = m
            break

    if not header_mapping and raw_rows:
        header_mapping = _map_headers([str(c or "").strip() for c in raw_rows[0]])

    results: list[dict[str, Any]] = []
    for r in raw_rows[header_idx + 1 :]:
        row_dict: dict[str, Any] = {}
        has_content = False
        for c_idx, key in header_mapping.items():
            if c_idx < len(r):
                val = r[c_idx]
                if val is not None and str(val).strip():
                    has_content = True
                row_dict[key] = val
        if has_content and (row_dict.get("title") or row_dict.get("company")):
            results.append(row_dict)

    return results


def import_jobs_from_excel(file_bytes: bytes, filename: str, db: Session) -> dict[str, Any]:
    rows = parse_file_to_rows(file_bytes, filename)
    if not rows:
        raise ValueError("No valid job rows found in file. Ensure headers include 'Job Title' or 'Company'.")

    # 1. Create or get an import Resume record
    resume = Resume(
        filename=filename,
        raw_text=f"Imported from Excel: {filename} with {len(rows)} opportunities.",
        parsed_profile={"source": "excel_import", "filename": filename, "imported_at": datetime.utcnow().isoformat()},
    )
    db.add(resume)
    db.flush()

    # Gather metadata
    titles = [str(r.get("title", "")).strip() for r in rows if r.get("title")]
    locations = [str(r.get("location", "")).strip() for r in rows if r.get("location")]
    cities = list(dict.fromkeys([_detect_city(loc) for loc in locations if _detect_city(loc)]))

    # 2. Create SearchRun
    run = SearchRun(
        resume_id=resume.id,
        roles=titles[:5] if titles else ["Excel Import"],
        locations=cities[:5] if cities else ["All Locations"],
        include_remote_india=True,
        work_arrangement="any",
        posted_within_days=14,
        platforms=list(dict.fromkeys([_parse_platform(r.get("platform"), r.get("listing_url", "")) for r in rows])),
        target_count=len(rows),
        min_score=50,
        status=RunStatus.COMPLETED,
        progress={"stage": "completed", "counts": {"final": len(rows), "collected": len(rows)}},
        estimate={"excel_import": True, "filename": filename, "row_count": len(rows)},
    )
    db.add(run)
    db.flush()

    imported_jobs: list[Job] = []

    for idx, r in enumerate(rows, start=1):
        title = str(r.get("title") or "Opportunity").strip()
        company = str(r.get("company") or "Company").strip()
        loc_str = str(r.get("location") or "").strip()
        city = _detect_city(loc_str)
        is_remote = "remote" in loc_str.lower() or "wfh" in loc_str.lower()
        work_mode = "remote" if is_remote else ("hybrid" if "hybrid" in loc_str.lower() else "office")
        score_val = _parse_score(r.get("score"))
        link = str(r.get("listing_url") or "").strip()
        platform = _parse_platform(r.get("platform"), link)
        posted = _parse_date(r.get("posted_date"))
        user_state = _parse_status(r.get("status"))
        notes = str(r.get("notes") or "").strip()
        desc = str(r.get("description") or "").strip()
        why_fits = str(r.get("why_fits") or "").strip()
        skills = str(r.get("key_skills_match") or "").strip()
        exp_summary = str(r.get("experience_summary") or "").strip()
        tier = str(r.get("company_tier") or "Tier 2").strip()

        job = Job(
            run_id=run.id,
            platform=platform,
            platform_job_id=f"xl_{run.id}_{idx}",
            title=title,
            company=company,
            location_text=loc_str or (city or "Not specified"),
            city=city,
            is_remote=is_remote,
            work_mode=work_mode,
            posted_date=posted,
            listing_url=link or None,
            apply_url=link or None,
            description=desc or why_fits or notes or f"{title} at {company}",
            user_state=user_state,
            user_note=notes or None,
        )
        db.add(job)
        db.flush()

        cat = "strong" if score_val >= 80 else ("moderate" if score_val >= 65 else "stretch")
        score = Score(
            job_id=job.id,
            total=score_val,
            breakdown={
                "experience": min(40, int(score_val * 0.4)),
                "skills": min(40, int(score_val * 0.4)),
                "tier": 10,
            },
            company_tier=tier,
            experience_summary=exp_summary or "Matches candidate experience level.",
            key_skills_match=skills or "Relevant stack match.",
            why_fits=why_fits or f"Strong alignment for {title} position.",
            notes=notes,
            category=cat,
            model="Excel Import",
        )
        db.add(score)

        ver = Verification(
            job_id=job.id,
            status="verified_active",
            method="excel_import",
            easy_apply=False,
            evidence={"imported_from": filename},
        )
        db.add(ver)

        imported_jobs.append(job)

    db.commit()

    return {
        "run_id": run.id,
        "filename": filename,
        "total_imported": len(imported_jobs),
        "roles": run.roles,
        "platforms": run.platforms,
    }


def generate_sample_template() -> bytes:
    """Generate a clean, styled Excel workbook template with sample data."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Ranked Opportunities"

    # Header row
    for idx, (name, width) in enumerate(COLUMNS, start=1):
        c = ws.cell(row=1, column=idx, value=name)
        c.font, c.fill, c.border = HEADER_FONT, HEADER_FILL, BORDER
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    sample_data = [
        [
            0.94,
            "Staff Software Engineer - Distributed Systems",
            "Stripe",
            "LinkedIn",
            "Tier 1 (Product Tech)",
            "Bengaluru (Remote)",
            "2026-10-18",
            "7+ yrs required, candidate has 8 yrs in high-throughput backend systems.",
            "Python, FastAPI, Kafka, PostgreSQL, Distributed Architecture",
            "Direct match with modern payments infrastructure and competitive compensation.",
            "https://www.stripe.com/jobs/staff-engineer",
            "Applied directly via referral portal. Contacted engineering manager on LinkedIn.",
        ],
        [
            0.88,
            "Senior Backend Engineer (Python / Go)",
            "Atlassian",
            "LinkedIn",
            "Tier 1 (Enterprise SaaS)",
            "Bengaluru (Hybrid)",
            "2026-10-19",
            "5-8 yrs experience in microservices and scalable cloud platforms.",
            "Python, Go, AWS, Docker, Kubernetes, GraphQL",
            "Strong focus on developer tooling (Jira/Confluence team), flexible hybrid policy.",
            "https://www.atlassian.com/careers/backend-eng",
            "Shortlisted for interview next week.",
        ],
        [
            0.85,
            "Lead AI / Machine Learning Engineer",
            "Freshworks",
            "Naukri",
            "Tier 1 (Indian Unicorn)",
            "Chennai / Hyderabad",
            "2026-10-15",
            "6+ yrs in software development with 3+ yrs in GenAI / LLM agentic pipelines.",
            "LangChain, Vector DBs, PyTorch, FastAPI, OpenAI API",
            "Leading the AI copilot platform team. High impact role with rapid product iterations.",
            "https://www.freshworks.com/careers/lead-ai-engineer",
            "Recruiter reached out on Naukri. Compensation: 45-55 LPA.",
        ],
        [
            0.82,
            "Full Stack Developer (React & Python)",
            "Swiggy",
            "Indeed",
            "Tier 2 (Consumer Tech)",
            "Remote (India)",
            "2026-10-20",
            "4-7 yrs full stack experience across modern React SPAs and Python backend APIs.",
            "React, TypeScript, Tailwind CSS, Python, Redis, SQL",
            "Fast-paced consumer logistics platform, full remote option available.",
            "https://www.swiggy.com/careers/fullstack-dev",
            "Applied on Indeed. Waiting for response.",
        ],
        [
            0.78,
            "Senior Cloud Platform Engineer",
            "PhonePe",
            "LinkedIn",
            "Tier 1 (Fintech)",
            "Bengaluru",
            "2026-10-21",
            "5+ yrs managing cloud-native infrastructure, reliability, and automated CI/CD.",
            "AWS, Terraform, Kubernetes, Linux, Prometheus, Grafana",
            "Crucial high-availability fintech infrastructure handling billions of transactions.",
            "https://www.phonepe.com/careers/cloud-platform",
            "Saved for application this weekend.",
        ],
    ]

    for row_idx, row in enumerate(sample_data, start=2):
        for col_idx, val in enumerate(row, start=1):
            c = ws.cell(row=row_idx, column=col_idx, value=val)
            fill = ALT_FILL if row_idx % 2 == 0 else WHITE_FILL
            c.font, c.fill, c.border, c.alignment = BODY_FONT, fill, BORDER, WRAP
            if col_idx == 1:
                c.number_format = "0%"
                c.alignment = Alignment(horizontal="center", vertical="top")
            elif col_idx == 11 and val:
                c.hyperlink = str(val)
                c.font = LINK_FONT

    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(sample_data) + 1}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
