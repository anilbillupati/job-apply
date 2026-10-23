"""Cost estimation for a run (or an expansion round) before anything is paid for."""

from app.llm.client import PRICES_ANTHROPIC as PRICES
from app.scrapers.keywords import flatten
from app.scrapers.platforms import PLATFORMS, TaskSpec, build_tasks

# Rough per-batch token use for LLM scoring (5 jobs): input incl. cached profile, output incl. thinking.
_BATCH_IN, _BATCH_OUT = 7000, 3500
# Share of scraped unique jobs that typically survive filters + verification to reach the LLM.
_LLM_SHARE = 0.25


def plan_tasks(
    run,
    keywords: list[str] | None = None,
    window_days: int | None = None,
    depth: int = 1,
    naukri_limit: int | None = None,
) -> list[TaskSpec]:
    kws = keywords if keywords is not None else flatten(run.keywords or {})
    years = float((run.resume.parsed_profile or {}).get("total_years_experience") or 0)
    specs: list[TaskSpec] = []
    for platform in PLATFORMS:
        if platform in (run.platforms or []):
            specs += build_tasks(
                platform,
                kws,
                run.locations or [],
                run.include_remote_india,
                window_days or run.posted_within_days,
                years,
                depth,
                naukri_limit=naukri_limit if naukri_limit is not None else 30,
            )
    return specs


def estimate(
    specs: list[TaskSpec],
    model: str,
    llm_top_n: int,
    cap: float,
    spent: float = 0.0,
    remaining_credit: float | None = None,
) -> dict:
    per: dict[str, dict] = {}
    for s in specs:
        p = per.setdefault(s.platform, {"runs": 0, "items": 0, "cost_usd": 0.0})
        p["runs"] += 1
        p["items"] += s.est_items
        p["cost_usd"] += s.est_cost
    for p in per.values():
        p["cost_usd"] = round(p["cost_usd"], 4)
    apify_total = round(sum(p["cost_usd"] for p in per.values()), 4)
    items = sum(p["items"] for p in per.values())

    pin, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    llm_jobs = min(llm_top_n, int(items * _LLM_SHARE))
    batches = -(-llm_jobs // 5)
    llm_cost = round(batches * (_BATCH_IN * pin + _BATCH_OUT * pout) / 1_000_000, 3)

    budget_left = round(cap - spent, 4)
    reasons = []
    if apify_total > budget_left:
        reasons.append(
            f"Estimated Apify cost ${apify_total:.2f} exceeds the remaining run cap ${budget_left:.2f} "
            f"(MAX_RUN_COST_USD=${cap:.2f}). Remove keywords, locations or platforms."
        )
    if remaining_credit is not None and apify_total > remaining_credit:
        reasons.append(
            f"Estimated Apify cost ${apify_total:.2f} exceeds the remaining monthly Apify credit "
            f"${remaining_credit:.2f}."
        )
    return {
        "platforms": per,
        "apify_total_usd": apify_total,
        "est_items": items,
        "llm_estimate_usd": llm_cost,
        "llm_model": model,
        "cap_usd": cap,
        "spent_usd": round(spent, 4),
        "remaining_credit_usd": remaining_credit,
        "ok": not reasons,
        "reasons": reasons,
    }
