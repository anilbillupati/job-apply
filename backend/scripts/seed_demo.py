"""Load the demo: a sample resume plus a full pipeline run over recorded Apify fixtures.

No Apify credit is spent and no job sites are contacted. Scoring uses the LLM only with --use-llm
(and ANTHROPIC_API_KEY set); otherwise the labelled heuristic scorer is used.

    python -m scripts.seed_demo [--use-llm] [--export out.xlsx]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal  # noqa: E402
from app.demo import FixtureApify, FixtureVerifier, demo_profile, demo_resume_text  # noqa: E402
from app.export.excel import build_workbook  # noqa: E402
from app.logging_setup import setup_logging  # noqa: E402
from app.migrate import upgrade_db  # noqa: E402
from app.models import Resume, RunStatus, SearchRun  # noqa: E402
from app.pipeline.estimate import plan_tasks  # noqa: E402
from app.pipeline.runner import Deps, empty_progress, execute_run, final_jobs_query  # noqa: E402
from app.scrapers.keywords import generate_keywords  # noqa: E402
from app.services.runs import create_tasks  # noqa: E402

ROLES = ["Java", "Backend", "Python", "GenAI"]
CITIES = ["Hyderabad", "Bengaluru", "Chennai", "Pune"]


async def seed(use_llm: bool, export: str | None, min_score: int) -> int:
    upgrade_db()
    with SessionLocal() as db:
        resume = Resume(filename="Demo_Candidate_Java.pdf + Demo_Candidate_GenAI.pdf (demo)",
                        raw_text=demo_resume_text(), parsed_profile=demo_profile())
        db.add(resume)
        db.commit()
        run = SearchRun(
            resume_id=resume.id, roles=ROLES, locations=CITIES, include_remote_india=True,
            posted_within_days=7, platforms=["linkedin", "naukri", "indeed"], exclude_linkedin_easy_apply=True,
            target_count=60, min_score=min_score, keywords=generate_keywords(ROLES, resume.parsed_profile),
            status=RunStatus.QUEUED, progress=empty_progress(),
        )
        db.add(run)
        db.commit()
        run.estimate = {"demo": True, "note": "Recorded fixtures; no Apify credit spent."}
        create_tasks(db, run, plan_tasks(run), 1)
        run_id = run.id

    deps = Deps(apify_factory=FixtureApify, verifier_factory=FixtureVerifier, use_llm=use_llm)
    await execute_run(run_id, deps)

    with SessionLocal() as db:
        run = db.get(SearchRun, run_id)
        c = (run.progress or {}).get("counts", {})
        print(f"\nDemo run #{run.id}: status={run.status}")
        print(f"  collected={c.get('collected')} unique={c.get('unique')} passed_filters={c.get('passed_filters')} "
              f"after_dedupe={c.get('after_dedupe')} verified={c.get('verified')} scored={c.get('scored')} "
              f"final={c.get('final')}")
        print(f"  filtered: {c.get('filtered')}")
        if run.error:
            print(f"  error: {run.error}")
        if export:
            jobs = final_jobs_query(db, run)
            Path(export).write_bytes(build_workbook(jobs, full=False, run=run))
            print(f"  exported {len(jobs)} rows to {export}")
        print(f"\nOpen http://localhost:5173/runs/{run.id}/results to explore it.")
        return run.id


def main() -> None:
    setup_logging()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--use-llm", action="store_true", help="score with Claude (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--export", help="also write the Excel export to this path")
    ap.add_argument("--min-score", type=int, default=65)
    args = ap.parse_args()
    asyncio.run(seed(args.use_llm, args.export, args.min_score))


if __name__ == "__main__":
    main()
