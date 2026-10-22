"""Stage 1 scoring: a fast rule-based pre-score (0–100) used to pick what to verify and send to the LLM."""

import re
from dataclasses import dataclass

ALIASES: dict[str, list[str]] = {
    "spring boot": ["springboot", "spring-boot"],
    "javascript": ["js", "ecmascript"],
    "typescript": ["ts"],
    "kubernetes": ["k8s"],
    "postgresql": ["postgres"],
    "machine learning": ["ml"],
    "artificial intelligence": ["ai"],
    "large language models": ["llm", "llms"],
    "llm": ["large language model", "llms"],
    "generative ai": ["genai", "gen ai"],
    "amazon web services": ["aws"],
    "aws": ["amazon web services"],
    "google cloud": ["gcp"],
    "rest": ["restful", "rest api", "rest apis"],
    "node.js": ["nodejs", "node"],
    "react": ["reactjs", "react.js"],
    "ci/cd": ["cicd", "ci cd"],
    "microservices": ["micro services", "microservice"],
    "retrieval augmented generation": ["rag"],
    "rag": ["retrieval augmented generation", "retrieval-augmented generation"],
}

STACK_MAJOR = ["c#", ".net", "dotnet", "c++", "php", "ruby", "salesforce", "sap"]
STACK_MINOR = ["golang", "angular", "react"]

CATEGORY_TERMS: dict[str, list[str]] = {
    "Java": ["java", "spring", "j2ee"],
    "Backend": ["backend", "back-end", "back end", "server side", "api"],
    "Full Stack": ["full stack", "fullstack", "full-stack"],
    "Software Engineer": ["software engineer", "software developer", "sde", "software development engineer"],
    "Python": ["python", "django", "fastapi", "flask"],
    "AI/ML": ["machine learning", "ml", "ai", "data scientist", "deep learning", "nlp"],
    "GenAI": ["genai", "gen ai", "generative", "llm", "ai agent", "agentic", "rag"],
}
GENERIC_TITLE = ["developer", "engineer", "programmer", "sde"]


def _rx(term: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9+#])", re.I)


@dataclass
class SkillDict:
    patterns: list[tuple[str, float, list[re.Pattern]]]
    owned: set[str]

    @classmethod
    def from_profile(cls, profile: dict | None) -> "SkillDict":
        profile = profile or {}
        weights: dict[str, float] = {}
        display: dict[str, str] = {}
        for w, key in ((0.4, "skills_listed_only"), (1.0, "skills_professional")):
            for s in profile.get(key) or []:
                name = str(s).strip()
                if name:
                    weights[name.lower()] = w
                    display[name.lower()] = name
        pats = []
        for skill, w in weights.items():
            terms = [skill] + ALIASES.get(skill, [])
            pats.append((display[skill], w, [_rx(t) for t in terms]))
        owned = set(weights)
        for skill in list(owned):
            owned.update(ALIASES.get(skill, []))
        return cls(pats, owned)


def prescore(job, skills: SkillDict, roles: list[str], candidate_years: float, cities: list[str]) -> tuple[float, dict]:
    text = f"{job.title}\n{job.description or ''}"
    title = job.title.lower()

    matched, matched_w = [], 0.0
    for skill, w, pats in skills.patterns:
        if any(p.search(text) for p in pats):
            matched.append(skill)
            matched_w += w
    skill_pts = 40.0 * min(1.0, matched_w / 5.0)

    penalty = 0.0
    mismatches = []
    for term in STACK_MAJOR:
        if term in skills.owned:
            continue
        rx = _rx(term)
        if rx.search(title):
            penalty += 15
            mismatches.append(term)
        elif len(rx.findall(job.description or "")) >= 2:
            penalty += 8
            mismatches.append(term)
    minor = 0.0
    for term in STACK_MINOR:
        if term not in skills.owned and _rx(term).search(text):
            minor += 3
            mismatches.append(term)
    penalty += min(minor, 6)

    y = candidate_years
    if job.exp_min is None:
        exp_pts = 14.0
    else:
        upper = job.exp_max if job.exp_max is not None else job.exp_min + 3
        if job.exp_min <= y <= upper + 1:
            exp_pts = 20.0
        elif job.exp_min <= y + 1:
            exp_pts = 15.0
        elif job.exp_min <= y + 2.5:
            exp_pts = 8.0
        else:
            exp_pts = 0.0

    title_pts = 0.0
    for role in roles:
        if any(_rx(t).search(title) for t in CATEGORY_TERMS.get(role, [role.lower()])):
            title_pts = 25.0
            break
    if not title_pts and any(_rx(t).search(title) for t in GENERIC_TITLE):
        title_pts = 12.0

    if job.city in cities:
        loc_pts = 15.0
    elif job.is_remote:
        loc_pts = 13.0
    else:
        loc_pts = 0.0

    total = max(0.0, min(100.0, skill_pts + exp_pts + title_pts + loc_pts - penalty))
    detail = {
        "skills": round(skill_pts, 1), "experience": exp_pts, "title": title_pts, "location": loc_pts,
        "penalty": round(penalty, 1), "matched_skills": matched[:25], "stack_mismatches": mismatches,
    }
    return round(total, 1), detail
