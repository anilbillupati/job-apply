"""User-editable settings stored in the database, with defaults."""

from sqlalchemy.orm import Session

from app.config import ALLOWED_MODELS, get_settings
from app.models import AppSetting

DEFAULTS: dict = {
    # Company names (case-insensitive substrings) treated as agencies / talent marketplaces.
    "agency_blocklist": [
        "Turing", "Toptal", "Crossover", "Braintrust", "Andela", "Uplers", "Mercor",
        "Outlier", "Alignerr", "Micro1", "Talent500", "Instahyre", "Hirist", "Flexing It",
    ],
    # Companies never wanted; pre-filled into each new search's exclusion list.
    "excluded_companies": [],
    # Employers whose names match the agency regex but who hire directly.
    "agency_allowlist": ["Tata Consultancy Services"],
    # Title terms that make a job irrelevant for the candidate.
    "title_exclusions": [
        "tutor", "teacher", "trainer", "sales", "qa", "quality assurance", "test engineer", "tester",
        "sap", "salesforce", ".net", "dotnet", "c#", "c++", "ios", "android", "php", "mainframe",
        "support engineer", "business analyst",
    ],
    # Seniority words that exclude a title (Senior/Sr can be allowed back, see below).
    "seniority_exclusions": [
        "senior", "sr", "lead", "principal", "staff", "manager", "director", "architect",
        "intern", "internship", "trainee", "fresher", "head", "vp",
    ],
    # When set (e.g. 4), "Senior"/"Sr" titles are allowed if the listing asks for at most N years.
    "allow_senior_max_years": None,
    "llm_model": None,  # None means use LLM_MODEL from the environment
    "llm_top_n": 150,
}


def get_setting(db: Session, key: str):
    row = db.get(AppSetting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def all_settings(db: Session) -> dict:
    out = {k: get_setting(db, k) for k in DEFAULTS}
    out["llm_model"] = out["llm_model"] or get_settings().llm_model
    out["allowed_models"] = ALLOWED_MODELS
    return out


def update_settings(db: Session, values: dict) -> dict:
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        if key == "llm_model" and value is not None and value not in ALLOWED_MODELS:
            raise ValueError(f"llm_model must be one of {ALLOWED_MODELS}")
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    db.commit()
    return all_settings(db)


def llm_model(db: Session) -> str:
    return get_setting(db, "llm_model") or get_settings().llm_model
