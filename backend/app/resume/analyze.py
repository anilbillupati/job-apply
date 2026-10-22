"""Resume analysis into a structured profile (LLM, with a clearly-labelled heuristic fallback)."""

import re
from datetime import date

from pydantic import BaseModel, Field, ValidationError

from app.llm.client import LLMError, llm_available, structured_call
from app.pipeline.text import parse_experience

_STR_LIST = {"type": "array", "items": {"type": "string"}}

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "total_years_experience": {"type": "number"},
        "current_title": {"type": "string"},
        "employers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                },
                "required": ["name", "title", "start", "end"],
                "additionalProperties": False,
            },
        },
        "education": _STR_LIST,
        "certifications": _STR_LIST,
        "skills_professional": _STR_LIST,
        "skills_listed_only": _STR_LIST,
        "measurable_achievements": _STR_LIST,
        "best_fit_categories": _STR_LIST,
        "realistic_levels": _STR_LIST,
        "gaps": _STR_LIST,
        "inconsistencies": _STR_LIST,
    },
    "required": [
        "total_years_experience", "current_title", "employers", "education", "certifications",
        "skills_professional", "skills_listed_only", "measurable_achievements", "best_fit_categories",
        "realistic_levels", "gaps", "inconsistencies",
    ],
    "additionalProperties": False,
}


class Employer(BaseModel):
    name: str
    title: str = ""
    start: str = ""
    end: str = ""


class Profile(BaseModel):
    total_years_experience: float = Field(ge=0, le=50)
    current_title: str = ""
    employers: list[Employer] = []
    education: list[str] = []
    certifications: list[str] = []
    skills_professional: list[str] = []
    skills_listed_only: list[str] = []
    measurable_achievements: list[str] = []
    best_fit_categories: list[str] = []
    realistic_levels: list[str] = []
    gaps: list[str] = []
    inconsistencies: list[str] = []


SYSTEM = """You analyse software-engineering resumes for an Indian job search.
You may receive several resumes from the same person (for example a Java-focused one and a GenAI-focused one).
Analyse them together as one candidate.

Rules:
- Use only evidence in the resumes. Never invent employers, dates, skills or numbers.
- total_years_experience: full-time professional experience in years (decimals allowed), from employment dates.
  Exclude internships unless they are the only experience.
- skills_professional: skills backed by an experience or project bullet (the bullet shows them used at work).
- skills_listed_only: skills that appear only in a skills/technologies section with no supporting bullet.
- measurable_achievements: copy bullets with numbers verbatim (e.g. "reduced latency by 60%").
- best_fit_categories: choose from Java, Backend, Full Stack, Software Engineer, Python, AI/ML, GenAI.
- realistic_levels: realistic job levels such as "SDE I", "SDE II", "Software Engineer II".
- gaps: missing skills or experience commonly required for the best-fit roles.
- inconsistencies: contradictions between resumes or within one (e.g. different start dates for the same job).
- Dates as written in the resume (e.g. "Jan 2022"); use "Present" for current roles.
Today's date is {today}."""


async def analyze_resume(raw_text: str, model: str) -> tuple[dict, float]:
    """Return (parsed_profile, llm_cost_usd)."""
    if not llm_available():
        return heuristic_profile(raw_text), 0.0
    system = [{"type": "text", "text": SYSTEM.format(today=date.today().isoformat())}]
    user = f"<resumes>\n{raw_text[:150_000]}\n</resumes>\n\nProduce the candidate profile."
    last_error = None
    total_cost = 0.0
    for _ in range(2):  # validate, retry once on failure
        try:
            data, cost = await structured_call(model=model, system=system, user=user, schema=PROFILE_SCHEMA,
                                               op="analyze_resume", effort="medium")
            total_cost += cost
            profile = Profile.model_validate(data).model_dump()
            profile["source"] = model
            return profile, total_cost
        except (ValidationError, LLMError) as exc:
            last_error = exc
            user += f"\n\nYour previous answer was invalid: {str(exc)[:500]}. Return valid JSON for the schema."
    raise LLMError(f"resume analysis failed: {last_error}")


# ------------------------------------------------------------------ heuristic fallback

SKILL_VOCAB = [
    "Java", "Spring Boot", "Spring", "Hibernate", "Microservices", "Kafka", "RabbitMQ", "REST", "GraphQL",
    "Python", "Django", "FastAPI", "Flask", "Node.js", "TypeScript", "JavaScript", "React", "Angular",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "AWS", "Azure", "GCP", "Docker",
    "Kubernetes", "Terraform", "Jenkins", "CI/CD", "Git", "Linux", "Machine Learning", "Deep Learning",
    "PyTorch", "TensorFlow", "scikit-learn", "NLP", "LLM", "RAG", "LangChain", "LangGraph", "Generative AI",
    "OpenAI", "Hugging Face", "Vector Database", "Pandas", "NumPy", "Spark", "Airflow", "JUnit", "Go",
]


def heuristic_profile(raw_text: str) -> dict:
    """Keyword-based profile used only when no ANTHROPIC_API_KEY is set. Marked source='heuristic'."""
    low = raw_text.lower()
    skills = [s for s in SKILL_VOCAB if re.search(r"(?<![a-z0-9])" + re.escape(s.lower()) + r"(?![a-z0-9])", low)]
    years = 0.0
    m = re.search(r"(\d{1,2}(?:\.\d)?)\+?\s*(?:years|yrs)", low)
    if m:
        years = float(m.group(1))
    else:
        lo, _ = parse_experience(raw_text)
        years = lo or 0.0
    achievements = [line.strip(" •-*\t") for line in raw_text.splitlines() if re.search(r"\d+\s*%|\d+x\b", line)]
    cats = []
    if any(s in skills for s in ("Java", "Spring Boot")):
        cats += ["Java", "Backend"]
    if "Python" in skills:
        cats.append("Python")
    if any(s in skills for s in ("LLM", "RAG", "LangChain", "Generative AI")):
        cats.append("GenAI")
    if any(s in skills for s in ("Machine Learning", "PyTorch", "TensorFlow")):
        cats.append("AI/ML")
    return Profile(
        total_years_experience=years,
        current_title="",
        skills_professional=skills,
        measurable_achievements=achievements[:10],
        best_fit_categories=cats or ["Software Engineer"],
        realistic_levels=["SDE I", "SDE II"] if years < 4 else ["SDE II", "Senior Software Engineer"],
        gaps=["Heuristic profile: set ANTHROPIC_API_KEY for a full analysis"],
    ).model_dump() | {"source": "heuristic"}
