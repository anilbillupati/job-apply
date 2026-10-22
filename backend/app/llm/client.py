"""Anthropic client helper: strict-JSON calls with prompt caching, refusal handling and cost accounting."""

import json
import logging

import anthropic

from app.config import get_settings
from app.logging_setup import redact, timed_call
from app.services import anthropic_key

log = logging.getLogger("llm")

# USD per million tokens: (input, output). Cache reads bill at 0.1x input, cache writes at 1.25x.
PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    """No API key configured."""


def usage_cost(model: str, usage) -> float:
    pin, pout = PRICES.get(model, PRICES["claude-sonnet-5-5"])
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cread = getattr(usage, "cache_read_input_tokens", 0) or 0
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (inp * pin + cread * pin * 0.1 + cwrite * pin * 1.25 + out * pout) / 1_000_000


_client: anthropic.AsyncAnthropic | None = None
_client_key: str | None = None
_fallbacks_ok = True


def make_client(api_key: str) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=api_key, max_retries=3, timeout=300)


def get_client() -> anthropic.AsyncAnthropic:
    """Client for the key saved in the UI, else ANTHROPIC_API_KEY. Rebuilt when the key changes."""
    global _client, _client_key
    key, _ = anthropic_key.resolve()
    if not key:
        raise LLMUnavailable("No Anthropic API key: add one in Settings or set ANTHROPIC_API_KEY")
    if _client is None or _client_key != key:
        _client, _client_key = make_client(key), key
    return _client


def llm_available() -> bool:
    return anthropic_key.resolve()[0] is not None


async def structured_call(
    *,
    model: str,
    system: list[dict],
    user: str,
    schema: dict,
    op: str,
    max_tokens: int = 16000,
    effort: str = "medium",
) -> tuple[dict, float]:
    """Call Claude with a JSON-schema output format. Returns (parsed JSON, cost in USD)."""
    global _fallbacks_ok
    client = get_client()
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    with timed_call(log, "anthropic", op, model=model) as info:
        try:
            if get_settings().llm_fallbacks and _fallbacks_ok:
                try:
                    resp = await client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
                except anthropic.BadRequestError as exc:
                    if "fallback" not in str(exc).lower():
                        raise
                    log.warning("server-side fallbacks rejected; continuing without them")
                    _fallbacks_ok = False
                    resp = await client.messages.create(**kwargs)
            else:
                resp = await client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            raise LLMError(redact(f"{type(exc).__name__}: {exc}")) from None

        cost = usage_cost(model, resp.usage)
        info.update(cost_usd=round(cost, 5), input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    cache_read=getattr(resp.usage, "cache_read_input_tokens", 0),
                    stop_reason=resp.stop_reason)

    if resp.stop_reason == "refusal":
        raise LLMError("model declined the request (refusal)")
    if resp.stop_reason == "max_tokens":
        raise LLMError("response truncated at max_tokens")
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), None)
    if not text:
        raise LLMError("no text block in response")
    try:
        return json.loads(text), cost
    except json.JSONDecodeError as exc:
        raise LLMError(f"invalid JSON from model: {exc}") from None
