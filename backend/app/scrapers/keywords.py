"""Search keyword generation per role category."""

ROLE_CATEGORIES = ["Java", "Backend", "Full Stack", "Software Engineer", "Python", "AI/ML", "GenAI"]

BASE_KEYWORDS: dict[str, list[str]] = {
    "Java": ["java developer", "java backend developer"],
    "Backend": ["backend developer"],
    "Full Stack": ["full stack developer java"],
    "Software Engineer": ["software engineer", "software developer"],
    "Python": ["python developer", "python backend developer"],
    "AI/ML": ["machine learning engineer", "ai engineer"],
    "GenAI": ["generative ai engineer", "llm engineer", "ai agent developer"],
}

# Extra keywords added when the resume shows the matching skill.
RESUME_BOOSTS: dict[str, list[tuple[str, str]]] = {
    "Java": [("spring boot", "spring boot developer"), ("microservices", "java microservices developer")],
    "Backend": [("node", "node.js backend developer"), ("golang", "golang developer")],
    "Full Stack": [("react", "full stack developer react"), ("python", "full stack developer python")],
    "Python": [("django", "django developer"), ("fastapi", "fastapi developer")],
    "AI/ML": [("pytorch", "deep learning engineer"), ("nlp", "nlp engineer")],
    "GenAI": [("rag", "rag engineer"), ("langchain", "langchain developer")],
}

# Used by "Expand search" step 1.
SYNONYMS: dict[str, list[str]] = {
    "Java": ["j2ee developer", "spring boot developer", "java software engineer"],
    "Backend": ["backend engineer", "api developer", "server side developer"],
    "Full Stack": ["full stack engineer", "fullstack developer"],
    "Software Engineer": ["sde", "software development engineer", "application developer"],
    "Python": ["python engineer", "python software engineer", "django developer"],
    "AI/ML": ["ml engineer", "applied scientist", "data scientist machine learning"],
    "GenAI": ["genai developer", "ai ml engineer llm", "prompt engineer"],
}


def _profile_skill_text(profile: dict | None) -> str:
    if not profile:
        return ""
    skills = (profile.get("skills_professional") or []) + (profile.get("skills_listed_only") or [])
    return " ".join(str(s).lower() for s in skills)


def generate_keywords(roles: list[str], profile: dict | None, per_category: int = 3) -> dict[str, list[str]]:
    """Two or three keywords per selected role category, nudged by the resume's skills."""
    skills = _profile_skill_text(profile)
    out: dict[str, list[str]] = {}
    for role in roles:
        base = list(BASE_KEYWORDS.get(role, [role.lower() + " developer"]))
        for skill, kw in RESUME_BOOSTS.get(role, []):
            if skill in skills and kw not in base:
                base.append(kw)
        out[role] = base[: max(per_category, len(BASE_KEYWORDS.get(role, [])))]
    return out


def synonym_keywords(keywords: dict[str, list[str]]) -> dict[str, list[str]]:
    """Synonyms not already present, per category."""
    used = {k.lower() for kws in keywords.values() for k in kws}
    out: dict[str, list[str]] = {}
    for cat in keywords:
        extra = [s for s in SYNONYMS.get(cat, []) if s.lower() not in used]
        if extra:
            out[cat] = extra[:2]
    return out


def flatten(keywords: dict[str, list[str]]) -> list[str]:
    seen: list[str] = []
    for kws in keywords.values():
        for k in kws:
            k = k.strip()
            if k and k.lower() not in {s.lower() for s in seen}:
                seen.append(k)
    return seen
