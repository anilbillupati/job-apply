"""Background execution: arq + Redis when REDIS_URL is set, otherwise asyncio tasks in the API process.

Start the worker with:  arq app.worker.WorkerSettings
"""

import asyncio
import logging
import time

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.logging_setup import setup_logging
from app.models import RunStatus, SearchRun
from app.pipeline.runner import execute_run

log = logging.getLogger("worker")

_local_tasks: dict[int, asyncio.Task] = {}


async def enqueue_run(run_id: int, resume: bool = False) -> str:
    """Queue a run. Returns the backend used ('arq' or 'inprocess')."""
    url = get_settings().redis_url
    if url:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(url))
        try:
            with SessionLocal() as db:
                rnd = db.get(SearchRun, run_id).round
            job_id = f"run-{run_id}-r{rnd}" + (f"-resume{int(time.time())}" if resume else "")
            await pool.enqueue_job("run_pipeline", run_id, _job_id=job_id)
        finally:
            await pool.aclose()
        return "arq"
    task = _local_tasks.get(run_id)
    if task and not task.done():
        return "inprocess"
    _local_tasks[run_id] = asyncio.create_task(execute_run(run_id))
    return "inprocess"


def interrupted_run_ids() -> list[int]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(SearchRun.id).where(
                    SearchRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.CANCELLING])
                )
            )
        )


async def resume_interrupted() -> None:
    """Pick up runs that were queued or mid-flight when the process stopped."""
    for run_id in interrupted_run_ids():
        with SessionLocal() as db:
            run = db.get(SearchRun, run_id)
            if run.status == RunStatus.CANCELLING:
                run.status = RunStatus.CANCELLED
                db.commit()
                continue
        log.info(f"resuming interrupted run {run_id}")
        await enqueue_run(run_id, resume=True)


# ------------------------------------------------------------------ arq worker


async def run_pipeline(ctx, run_id: int) -> None:
    await execute_run(run_id)


async def startup(ctx) -> None:
    setup_logging()
    from app.migrate import upgrade_db

    upgrade_db()
    asyncio.create_task(resume_interrupted())


def _redis_settings():
    from arq.connections import RedisSettings

    return RedisSettings.from_dsn(get_settings().redis_url or "redis://localhost:6379")


class WorkerSettings:
    functions = [run_pipeline]
    on_startup = startup
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 6 * 60 * 60
    keep_result = 3600
