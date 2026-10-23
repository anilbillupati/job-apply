"""LLM client: Claude (Anthropic) and Gemini (Google AI Studio) with automatic provider routing.

Whichever key is configured wins. Priority: Anthropic UI key → Google UI key → Anthropic .env key → Google .env key.
All callers use structured_call() — the routing is transparent.
"""

import json
import logging

import anthropic

from app.config import get_settings
from app.logging_setup import redact, timed_call
from app.services import anthropic_key, google_key

log = logging.getLogger("llm")

# USD per million tokens: (input, output).
PRICES_ANTHROPIC = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
# Backward-compatibility alias
PRICES = PRICES_ANTHROPIC

PRICES_GEMINI = {
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-3.5-flash": (0.15, 0.60),
    "gemini-3.6-flash": (0.15, 0.60),
    "gemini-3.7-flash": (0.15, 0.60),
    "gemini-3.8-flash": (0.15, 0.60),
    "gemini-flash-lite-latest": (0.075, 0.30),
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Maps user-facing Claude model selections to the best responsive Gemini models
_CLAUDE_TO_GEMINI = {
    "claude-sonnet-5-5": "gemini-3.5-flash",
    "claude-opus-5-5": "gemini-3.6-flash",
}
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_FALLBACK_CHAIN = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-lite-latest", "gemini-3.8-flash"]


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    """No API key configured."""


def _active_provider() -> tuple[str | None, str]:
    """Return (api_key, provider) — provider is 'anthropic' or 'google'."""
    # Anthropic UI key first
    ant_key, _ = anthropic_key.resolve()
    if ant_key and "demo-mock" not in ant_key:
        return ant_key, "anthropic"
    # Google UI key
    gkey, _ = google_key.resolve()
    if gkey:
        return gkey, "google"
    # Anthropic .env key (may be a demo key)
    if ant_key:
        return ant_key, "anthropic"
    return None, "none"


def llm_available() -> bool:
    key, _ = _active_provider()
    return key is not None


def _anthropic_cost(model: str, usage) -> float:
    pin, pout = PRICES_ANTHROPIC.get(model, PRICES_ANTHROPIC["claude-sonnet-5-5"])
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cread = getattr(usage, "cache_read_input_tokens", 0) or 0
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (inp * pin + cread * pin * 0.1 + cwrite * pin * 1.25 + out * pout) / 1_000_000


def _gemini_cost(model: str, usage) -> float:
    pin, pout = PRICES_GEMINI.get(model, (0.15, 0.60))
    inp = getattr(usage, "prompt_token_count", 0) or 0
    out = getattr(usage, "candidates_token_count", 0) or 0
    return (inp * pin + out * pout) / 1_000_000


# ------------------------------------------------------------------ Anthropic client

_ant_client: anthropic.AsyncAnthropic | None = None
_ant_client_key: str | None = None
_fallbacks_ok = True


def make_client(api_key: str) -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=api_key, max_retries=3, timeout=300)


def get_client() -> anthropic.AsyncAnthropic:
    global _ant_client, _ant_client_key
    key, _ = anthropic_key.resolve()
    if not key:
        raise LLMUnavailable("No Anthropic API key")
    if _ant_client is None or _ant_client_key != key:
        _ant_client, _ant_client_key = make_client(key), key
    return _ant_client


# ------------------------------------------------------------------ Gemini client

_gem_client = None
_gem_client_key: str | None = None


def _get_gemini_client(api_key: str):
    global _gem_client, _gem_client_key
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise LLMError("google-generativeai is not installed (run: pip install google-generativeai)") from exc
    if _gem_client is None or _gem_client_key != api_key:
        genai.configure(api_key=api_key)
        _gem_client_key = api_key
        _gem_client = genai
    return _gem_client


# ------------------------------------------------------------------ unified call

async def _call_anthropic(
    api_key: str,
    *,
    model: str,
    system: list[dict],
    user: str,
    schema: dict,
    op: str,
    max_tokens: int,
    effort: str,
) -> tuple[dict, float]:
    global _fallbacks_ok
    client = make_client(api_key)
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

        cost = _anthropic_cost(model, resp.usage)
        info.update(
            cost_usd=round(cost, 5),
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

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


async def _call_gemini(
    api_key: str,
    *,
    model: str,
    system: list[dict],
    user: str,
    schema: dict,
    op: str,
    max_tokens: int,
    **_kwargs,
) -> tuple[dict, float]:
    import asyncio
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    preferred_model = _CLAUDE_TO_GEMINI.get(model, model if model in PRICES_GEMINI else DEFAULT_GEMINI_MODEL)

    # Prepare model candidate list starting with preferred
    candidates = [preferred_model] + [m for m in GEMINI_FALLBACK_CHAIN if m != preferred_model]

    # Build system instruction from system blocks
    system_text = "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))

    generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        max_output_tokens=max_tokens,
    )

    last_err: Exception | None = None
    for gem_model in candidates:
        gmodel = genai.GenerativeModel(
            model_name=gem_model,
            system_instruction=system_text,
            generation_config=generation_config,
        )

        with timed_call(log, "gemini", op, model=gem_model) as info:
            try:
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(None, lambda: gmodel.generate_content(user))
            except Exception as exc:
                msg = str(exc)
                # If model is 503 (demand spike) or 404 (unavailable/deprecated), try next model
                if "503" in msg or "404" in msg or "UNAVAILABLE" in msg or "NOT_FOUND" in msg:
                    log.warning("Gemini model %s returned transient error (%s); trying fallback", gem_model, msg[:120])
                    last_err = exc
                    continue
                raise LLMError(redact(f"Gemini error: {type(exc).__name__}: {exc}")) from None

            usage = getattr(resp, "usage_metadata", None)
            cost = _gemini_cost(gem_model, usage) if usage else 0.0
            info.update(
                cost_usd=round(cost, 5),
                input_tokens=getattr(usage, "prompt_token_count", 0),
                output_tokens=getattr(usage, "candidates_token_count", 0),
            )

        text = resp.text
        if not text:
            raise LLMError("no text in Gemini response")
        try:
            return json.loads(text), cost
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON from Gemini: {exc}") from None

    raise LLMError(redact(f"All Gemini fallback models exhausted: {last_err}")) from None


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
    """Call the active LLM (Claude or Gemini) with a JSON-schema output. Returns (parsed JSON, cost in USD)."""
    api_key, provider = _active_provider()
    if not api_key:
        raise LLMUnavailable("No LLM API key configured. Add an Anthropic or Google AI Studio key in Settings.")

    if provider == "google":
        return await _call_gemini(
            api_key, model=model, system=system, user=user,
            schema=schema, op=op, max_tokens=max_tokens,
        )
    return await _call_anthropic(
        api_key, model=model, system=system, user=user,
        schema=schema, op=op, max_tokens=max_tokens, effort=effort,
    )

