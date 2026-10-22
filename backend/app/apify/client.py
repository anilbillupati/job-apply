"""Thin async wrapper over the Apify REST API (v2)."""

import asyncio
import logging
import random

import httpx

from app.logging_setup import redact, timed_call

log = logging.getLogger("apify")

API = "https://api.apify.com/v2"
TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


class ApifyError(Exception):
    pass


class ApifyCapacityError(ApifyError):
    """HTTP 402: memory or concurrency limit reached on the account. Retryable."""


class ApifyAuthError(ApifyError):
    pass


async def request_with_retry(
    client: httpx.AsyncClient, method: str, url: str, *, attempts: int = 4, **kwargs
) -> httpx.Response:
    """httpx request with exponential backoff on connection errors, 429 and 5xx."""
    delay = 1.5
    for attempt in range(1, attempts + 1):
        try:
            resp = await client.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            if attempt == attempts:
                raise
            log.warning(redact(f"transport error on {method} {url}: {exc}; retrying"))
        else:
            if resp.status_code != 429 and resp.status_code < 500:
                return resp
            if attempt == attempts:
                return resp
            retry_after = resp.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                delay = max(delay, float(retry_after))
        await asyncio.sleep(delay + random.uniform(0, 0.5))
        delay *= 2
    raise RuntimeError("unreachable")


class ApifyClient:
    def __init__(self, token: str, timeout: float = 90.0):
        if not token:
            raise ApifyAuthError("APIFY_TOKEN is not configured")
        self._http = httpx.AsyncClient(
            base_url=API,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    def _check(self, resp: httpx.Response, what: str) -> dict:
        if resp.status_code == 402:
            raise ApifyCapacityError(f"{what}: account limit reached (HTTP 402)")
        if resp.status_code in (401, 403):
            raise ApifyAuthError(f"{what}: authentication failed (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise ApifyError(redact(f"{what}: HTTP {resp.status_code} {resp.text[:300]}"))
        return resp.json()

    async def start(self, actor: str, input: dict, memory_mb: int, max_total_charge_usd: float) -> dict:
        params = {"memory": memory_mb, "maxTotalChargeUsd": round(max_total_charge_usd, 4)}
        with timed_call(log, "apify", "start", actor=actor, memory_mb=memory_mb):
            resp = await request_with_retry(self._http, "POST", f"/acts/{actor}/runs", params=params, json=input)
            return self._check(resp, f"start {actor}")["data"]

    async def get_run(self, run_id: str, wait_secs: int = 0) -> dict:
        params = {"waitForFinish": wait_secs} if wait_secs else None
        resp = await request_with_retry(self._http, "GET", f"/actor-runs/{run_id}", params=params)
        return self._check(resp, f"get run {run_id}")["data"]

    async def wait(self, run_id: str, should_stop=None) -> dict:
        """Poll until the run reaches a terminal status. `should_stop` is an async callable."""
        with timed_call(log, "apify", "wait", run_id=run_id) as info:
            while True:
                data = await self.get_run(run_id, wait_secs=60)
                if data.get("status") in TERMINAL:
                    info["status"] = data.get("status")
                    info["cost_usd"] = data.get("usageTotalUsd")
                    return data
                if should_stop and await should_stop():
                    await self.abort(run_id)
                    return await self.get_run(run_id)

    async def items(self, dataset_id: str, page_size: int = 1000) -> list[dict]:
        out: list[dict] = []
        offset = 0
        with timed_call(log, "apify", "items", dataset_id=dataset_id) as info:
            while True:
                params = {"clean": 1, "format": "json", "offset": offset, "limit": page_size}
                resp = await request_with_retry(self._http, "GET", f"/datasets/{dataset_id}/items", params=params)
                if resp.status_code >= 400:
                    self._check(resp, f"dataset {dataset_id}")
                batch = resp.json()
                out.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            info["count"] = len(out)
        return out

    async def abort(self, run_id: str) -> None:
        with timed_call(log, "apify", "abort", run_id=run_id):
            resp = await request_with_retry(self._http, "POST", f"/actor-runs/{run_id}/abort")
            if resp.status_code > 400:  # 400 means the run already finished
                self._check(resp, f"abort {run_id}")

    async def me(self) -> dict:
        with timed_call(log, "apify", "me"):
            resp = await request_with_retry(self._http, "GET", "/users/me")
            return self._check(resp, "users/me")["data"]

    async def limits(self) -> dict:
        with timed_call(log, "apify", "limits"):
            resp = await request_with_retry(self._http, "GET", "/users/me/limits")
            return self._check(resp, "users/me/limits")["data"]


def summarize_limits(data: dict) -> dict:
    """Pick the monthly usage and limit out of the /users/me/limits payload."""
    current = data.get("current") or {}
    limits = data.get("limits") or {}
    used = float(current.get("monthlyUsageUsd") or 0.0)
    limit = float(limits.get("maxMonthlyUsageUsd") or 0.0)
    return {
        "monthly_usage_usd": round(used, 4),
        "monthly_limit_usd": round(limit, 2),
        "remaining_usd": round(max(limit - used, 0.0), 4) if limit else None,
        "cycle_end": (data.get("monthlyUsageCycle") or {}).get("endAt"),
        "max_concurrent_runs": limits.get("maxConcurrentActorJobs"),
        "max_memory_mb": limits.get("maxActorMemoryGbytes") and int(limits["maxActorMemoryGbytes"] * 1024),
    }
