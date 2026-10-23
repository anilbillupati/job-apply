"""Stage 2 scoring: LLM rubric scoring in batches of 5, validated and retried once."""

import json
import logging

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.llm.client import LLMError, structured_call

log = logging.getLogger("scoring")

BATCH_SIZE = 5

RUBRIC = {
    "technical_skills": 30,
    "experience_seniority": 20,
    "role_domain": 15,
    "projects_achievements": 15,
    "location": 10,
    "education_mandatory": 5,
    "career_growth": 5,
}
RUBRIC_LABELS = {
    "technical_skills": "Technical skills",
    "experience_seniority": "Experience / seniority",
    "role_domain": "Role / domain",
    "projects_achievements": "Projects / achievements",
    "location": "Location",
    "education_mandatory": "Education / mandatory",
    "career_growth": "Career growth",
}
COMPANY_TIERS = [
    "Tier 1 – Global tech product",
    "Tier 1 – Global enterprise / bank (India GCC)",
    "Tier 2 – Established product / SaaS company",
    "Tier 2 – Funded startup / scale-up",
    "Tier 3 – Small or early-stage company",
    "IT services / consulting",
]
CATEGORIES = ["stretch", "strong", "safe"]

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "integer"},
                    "breakdown": {
                        "type": "object",
                        "properties": {k: {"type": "integer"} for k in RUBRIC},
                        "required": list(RUBRIC),
                        "additionalProperties": False,
                    },
                    "total": {"type": "integer"},
                    "company_tier": {"type": "string", "enum": COMPANY_TIERS},
                    "experience_summary": {"type": "string"},
                    "key_skills_match": {"type": "string"},
                    "why_fits": {"type": "string"},
                    "notes": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                },
                "required": [
                    "job_id",
                    "breakdown",
                    "total",
                    "company_tier",
                    "experience_summary",
                    "key_skills_match",
                    "why_fits",
                    "notes",
                    "category",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


class ScoreItem(BaseModel):
    job_id: int
    breakdown: dict[str, int]
    total: int
    company_tier: str
    experience_summary: str
    key_skills_match: str
    why_fits: str
    notes: str
    category: str

    @field_validator("breakdown")
    @classmethod
    def _bounds(cls, v: dict[str, int]) -> dict[str, int]:
        if set(v) != set(RUBRIC):
            raise ValueError(f"breakdown keys must be {sorted(RUBRIC)}")
        for k, mx in RUBRIC.items():
            if not 0 <= v[k] <= mx:
                raise ValueError(f"{k}={v[k]} outside 0..{mx}")
        return v

    @field_validator("company_tier")
    @classmethod
    def _tier(cls, v: str) -> str:
        if v not in COMPANY_TIERS:
            raise ValueError(f"unknown company_tier {v!r}")
        return v

    @field_validator("category")
    @classmethod
    def _cat(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"unknown category {v!r}")
        return v

    @field_validator("why_fits", "experience_summary", "key_skills_match")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @model_validator(mode="after")
    def _total(self):
        expected = sum(self.breakdown.values())
        if abs(self.total - expected) > 2:
            raise ValueError(f"total {self.total} does not match breakdown sum {expected}")
        self.total = expected
        return self


def validate_batch(data: dict, job_ids: list[int]) -> list[ScoreItem]:
    """Validate an LLM response against the schema and the batch it was asked about."""
    items = [ScoreItem.model_validate(r) for r in data.get("results", [])]
    got = sorted(i.job_id for i in items)
    if got != sorted(job_ids):
        raise ValueError(f"expected job_ids {sorted(job_ids)}, got {got}")
    return items


SYSTEM_RULES = """You score job listings against one candidate's resume profile for an Indian tech job search.

Score each job on this 100-point rubric (integers):
- technical_skills (0-30): overlap between the job's required stack and skills the candidate has used professionally.
  Skills only listed (not backed by experience) count for less.
- experience_seniority (0-20): fit between the candidate's years/level and what the listing asks.
- role_domain (0-15): fit of the role type and business domain with the candidate's history.
- projects_achievements (0-15): how directly the candidate's projects and measurable achievements map to the job.
- location (0-10): Hyderabad, Bengaluru, Chennai, Pune or India-remote fit; penalise onsite requirements elsewhere.
- education_mandatory (0-5): degree and any hard requirements (certifications, notice period, clearances).
- career_growth (0-5): learning and growth potential relative to the candidate's current role.
total must equal the sum of the breakdown.

Rules:
- Use only evidence from the resume profile. Never assume a skill the profile does not show.
- Do not inflate scores for company prestige. A famous company with a poor skills match scores low.
- Distinguish mandatory requirements from preferred ones. Penalise missing mandatory skills heavily;
  missing preferred skills only lightly.
- Never invent salaries, dates, requirements or facts about the company. Write "Not stated" when the listing
  does not say something you would otherwise mention.
- company_tier: classify from the company name and listing only; use "Tier 3 – Small or early-stage company"
  when you cannot tell.
- experience_summary: one sentence comparing required vs candidate experience, e.g.
  "Needs 2-5 yrs; candidate has 3.5 yrs (SDE II level)".
- key_skills_match: list the job's key skills, "✔ Skill" when the candidate meets it and "Gap: Skill" when not,
  separated by "; ".
- why_fits: 1-2 sentences that cite a specific resume achievement or project (quote its number if it has one).
- notes: risks and concerns: onsite/relocation requirements, bond, shift timings, missing mandatory skills,
  duplicate postings, vague listings. "None" if there are none.
- category: "stretch" (candidate is under-qualified but plausible), "strong" (good match),
  "safe" (candidate clearly meets or exceeds every mandatory requirement).
Return one result per job, using the job_id given."""


def profile_block(profile: dict) -> str:
    keys = [
        "total_years_experience",
        "current_title",
        "employers",
        "education",
        "certifications",
        "skills_professional",
        "skills_listed_only",
        "measurable_achievements",
        "best_fit_categories",
        "realistic_levels",
        "gaps",
    ]
    data = {k: profile.get(k) for k in keys}
    return (
        "<candidate_profile>\n"
        + json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)
        + "\n</candidate_profile>"
    )


def job_block(job) -> dict:
    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "platform": job.platform,
        "location": job.location_text or job.city or "Not stated",
        "remote": job.is_remote,
        "work_mode": job.work_mode,
        "posted_date": job.posted_date.isoformat() if job.posted_date else "Not stated",
        "experience_required": (
            f"{job.exp_min:g}-{job.exp_max:g} yrs"
            if job.exp_min is not None and job.exp_max is not None
            else f"{job.exp_min:g}+ yrs"
            if job.exp_min is not None
            else "Not stated"
        ),
        "salary": job.salary_text or "Not stated",
        "also_listed_on": [s.get("platform") for s in (job.alt_sources or [])],
        "description": (job.description or "")[:7000],
    }


async def score_batch(jobs: list, profile: dict, model: str) -> tuple[list[ScoreItem], float]:
    """Score up to 5 jobs in one call. System prompt + profile are cached across batches."""
    system = [
        {"type": "text", "text": SYSTEM_RULES},
        {"type": "text", "text": profile_block(profile), "cache_control": {"type": "ephemeral"}},
    ]
    ids = [j.id for j in jobs]
    user = "Score these jobs:\n" + json.dumps([job_block(j) for j in jobs], ensure_ascii=False, indent=1)
    total_cost = 0.0
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            data, cost = await structured_call(
                model=model, system=system, user=user, schema=SCORE_SCHEMA, op="score_batch", effort="medium"
            )
            total_cost += cost
            return validate_batch(data, ids), total_cost
        except (ValidationError, ValueError, LLMError) as exc:
            last_error = exc
            log.warning(f"score batch {ids} attempt {attempt + 1} invalid: {str(exc)[:300]}")
            user += f"\n\nYour previous answer failed validation: {str(exc)[:500]}\nReturn corrected JSON."
    raise LLMError(f"scoring failed for jobs {ids}: {last_error}")


# ------------------------------------------------------------------ heuristic fallback (no API key)


def heuristic_score(job, profile: dict) -> ScoreItem:
    """Deterministic stand-in used when no ANTHROPIC_API_KEY is set (demo mode). Labelled model='heuristic'."""
    d = job.prescore_detail or {}
    skills = d.get("matched_skills", [])
    tech = round(30 * min(1.0, d.get("skills", 0) / 40) - min(d.get("penalty", 0), 15) * 0.5)
    tech = max(0, min(30, tech))
    exp = round(d.get("experience", 10) / 20 * 20)
    role = 15 if d.get("title", 0) >= 25 else 8
    proj = min(15, 6 + len(skills))
    loc = 10 if d.get("location", 0) >= 15 else 8 if d.get("location", 0) else 3
    bd = {
        "technical_skills": tech,
        "experience_seniority": exp,
        "role_domain": role,
        "projects_achievements": proj,
        "location": loc,
        "education_mandatory": 4,
        "career_growth": 3,
    }
    total = sum(bd.values())
    achievements = profile.get("measurable_achievements") or []
    years = profile.get("total_years_experience") or 0
    exp_req = job_block(job)["experience_required"]
    gaps = d.get("stack_mismatches", [])
    return ScoreItem(
        job_id=job.id,
        breakdown=bd,
        total=total,
        company_tier="Tier 3 – Small or early-stage company",
        experience_summary=f"Needs {exp_req}; candidate has {years:g} yrs",
        key_skills_match="; ".join([f"✔ {s}" for s in skills[:8]] + [f"Gap: {g}" for g in gaps[:4]]) or "Not stated",
        why_fits=(
            f"Matches {', '.join(skills[:4]) or 'the role'}; relevant achievement: {achievements[0]}"
            if achievements
            else f"Matches {', '.join(skills[:4]) or 'the role'}."
        ),
        notes="Heuristic score (no ANTHROPIC_API_KEY configured); company tier not assessed.",
        category="safe" if total >= 82 else "strong" if total >= 70 else "stretch",
    )
