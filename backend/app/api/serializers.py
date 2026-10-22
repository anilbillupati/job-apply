"""Model → JSON helpers (kept explicit so secrets or raw payloads never leak into responses)."""

from app.models import Job, Resume, SearchRun
from app.services.runs import EXPAND_LABEL, next_expand_step


def resume_out(r: Resume) -> dict:
    return {"id": r.id, "filename": r.filename, "chars": len(r.raw_text or ""),
            "parsed_profile": r.parsed_profile, "created_at": r.created_at}


def run_out(run: SearchRun, final_count: int | None = None) -> dict:
    p = run.progress or {}
    step = next_expand_step(run) if run.status == "completed" else None
    final = (p.get("counts") or {}).get("final") if final_count is None else final_count
    return {
        "id": run.id, "resume_id": run.resume_id, "roles": run.roles, "locations": run.locations,
        "include_remote_india": run.include_remote_india, "work_arrangement": run.work_arrangement,
        "posted_within_days": run.posted_within_days, "platforms": run.platforms,
        "exclude_linkedin_easy_apply": run.exclude_linkedin_easy_apply, "target_count": run.target_count,
        "min_score": run.min_score, "keywords": run.keywords, "exclude_companies": run.exclude_companies or [],
        "round": run.round, "expand_steps": run.expand_steps,
        "status": run.status, "progress": p, "cost_usd": run.cost_usd, "estimate": run.estimate,
        "created_at": run.created_at, "started_at": run.started_at, "finished_at": run.finished_at,
        "error": run.error,
        "final_count": final,
        "next_expand_step": step and {"step": step, "label": EXPAND_LABEL[step]},
        "tasks": [
            {"id": t.id, "round": t.round, "platform": t.platform, "status": t.status, "item_count": t.item_count,
             "cost_usd": t.cost_usd, "est_items": t.est_items, "max_charge_usd": t.max_charge_usd,
             "error": t.error, "keyword": (t.input or {}).get("keywords") or (t.input or {}).get("title"),
             "location": (t.input or {}).get("location") or ("remote" if (t.input or {}).get("wfhType") else None),
             "urls": len((t.input or {}).get("urls") or [])}
            for t in run.tasks
        ],
    }


def job_row(j: Job) -> dict:
    s, v = j.score, j.verification
    return {
        "id": j.id, "platform": j.platform, "title": j.title, "company": j.company, "city": j.city,
        "location_text": j.location_text, "is_remote": j.is_remote, "work_mode": j.work_mode,
        "posted_date": j.posted_date, "exp_min": j.exp_min, "exp_max": j.exp_max, "salary_text": j.salary_text,
        "listing_url": j.listing_url, "apply_url": j.apply_url, "employer_url": j.employer_url,
        "is_agency": j.is_agency, "duplicate_of": j.duplicate_of, "alt_sources": j.alt_sources,
        "filter_reason": j.filter_reason, "prescore": j.prescore, "user_state": j.user_state,
        "user_note": j.user_note, "applicants_text": j.applicants_text,
        "verification_status": v.status if v else None, "easy_apply": v.easy_apply if v else None,
        "score": s.total if s else None, "company_tier": s.company_tier if s else None,
        "category": s.category if s else None,
    }


def job_detail(j: Job) -> dict:
    out = job_row(j)
    s, v = j.score, j.verification
    out.update(
        description=j.description,
        prescore_detail=j.prescore_detail,
        verification=v and {"status": v.status, "method": v.method, "easy_apply": v.easy_apply,
                            "evidence": v.evidence, "checked_at": v.checked_at},
        score_detail=s and {"total": s.total, "breakdown": s.breakdown, "company_tier": s.company_tier,
                            "experience_summary": s.experience_summary, "key_skills_match": s.key_skills_match,
                            "why_fits": s.why_fits, "notes": s.notes, "category": s.category, "model": s.model,
                            "created_at": s.created_at},
    )
    return out
