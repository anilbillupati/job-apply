import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.logging_setup import redact, setup_logging
from app.migrate import upgrade_db
from app.worker import resume_interrupted

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    upgrade_db()
    if not get_settings().redis_url:
        await resume_interrupted()  # with Redis, the arq worker owns resumption
    yield


app = FastAPI(title="JobRadar", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": redact(f"{type(exc).__name__}: {exc}")})


app.include_router(router)
