# JobRadar

Resume-matched job discovery across **LinkedIn, Naukri and Indeed**.

Upload a resume → pick roles and locations → scrape recent jobs through Apify → filter, de-duplicate and verify that
each job is still open → score each job against the resume with Claude → review the ranked list → export to Excel.

```
backend/    FastAPI + SQLAlchemy + Alembic + arq worker  (Python 3.11+)
frontend/   React 18 + TypeScript + Vite + TanStack Query/Table + Tailwind (shadcn/ui components)
docker-compose.yml   api · worker · web · redis
```

## Quick start (Docker)

```bash
cp .env.example .env          # add APIFY_TOKEN and ANTHROPIC_API_KEY
docker compose up --build     # UI on http://localhost:8080  (WEB_PORT=… to change)
docker compose exec api python -m scripts.seed_demo   # optional: offline demo run
```

The API is only reachable through the web container (`/api/*`), so it doesn't need a host port.

## Local development

```bash
make install     # venv + pip + Playwright Chromium + npm install
make seed        # loads a demo run from recorded fixtures (no Apify credit, no network)
make dev         # API on :8000 (runs execute in-process) + Vite on :5173
```

Without `make`:

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt && python -m playwright install chromium
python -m scripts.seed_demo
uvicorn app.main:app --reload --port 8000
# second terminal
cd frontend && npm install && npm run dev            # VITE_API_PROXY_TARGET=http://127.0.0.1:8000 by default
```

Migrations run automatically on API and worker start (`alembic upgrade head`). `make lint` runs ruff and the
TypeScript type-check.

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `APIFY_TOKEN` | — | Apify API token. Server-side only: never logged, returned, or shown in the UI. |
| `ANTHROPIC_API_KEY` | — | Resume analysis and job scoring. Without it a clearly labelled heuristic is used. |
| `LLM_MODEL` | `claude-sonnet-5-5` | `claude-opus-5-5` gives higher-quality scoring at about twice the cost. Also selectable in Settings. |
| `MAX_RUN_COST_USD` | `3.0` | Hard cap on estimated Apify spend per run (expansions included). |
| `DATABASE_URL` | SQLite file | e.g. `postgresql://user:pass@host:5432/jobradar` |
| `REDIS_URL` | — | When set, runs execute in the arq worker; otherwise as background tasks in the API process. |
| `RESPECT_ROBOTS_TXT` | `true` | Check robots.txt before each verification fetch. Disallowed URLs are marked *uncertain*. |
| `LLM_FALLBACKS` | `true` | Anthropic server-side refusal fallback (beta). |

Blank values (`KEY=`) mean "use the default".

## Apify key pool

Open **API keys** in the UI to add keys one by one or import them from an Excel/CSV file. Every cell containing an
`apify_api_…` token is imported, and another text cell in the same row becomes its label. Keys are encrypted at rest
(Fernet, see `JOBRADAR_SECRET_KEY` / `SECRET_KEY_FILE`). Only the last four characters are ever shown, and keys can be
disabled or deleted.

- **One key per day.** The first search of the day picks the active key used least recently and keeps it for the whole
  day (`KEY_ROTATION_TZ`, default Asia/Kolkata). Thirty keys cover about a month.
- **Automatic failover.** If the key is invalid (401/403) or out of credit (402 usage limit, or less credit left than
  the run's estimate), it is marked *failed today* and the next key takes over. Memory and concurrency 402s are retried
  on the same key.
- **Usage log.** Every daily pick, run, failover and connection test is logged with the time, key and run.
- Each Apify run remembers which key started it, because run and dataset IDs belong to that account.
- `APIFY_TOKEN` in `.env` is only used while the pool is empty.

## Anthropic API key

Settings → **Anthropic API key**: paste a key (`sk-ant-…`). It's verified with Anthropic (a models-list call, no
tokens), encrypted like the Apify keys, and takes priority over `ANTHROPIC_API_KEY` in `.env`. You can test, replace
or remove it there.

## Never the same job twice

When a run finishes, the job IDs in its ranked list (plus their cross-listings on other platforms) go into a
**seen history**, as do jobs you shortlist, apply to or reject. Later searches drop those IDs (filter reason "Already seen
in an earlier run"). Jobs that were only filtered out or couldn't be verified are not remembered, so they get another
chance. Settings shows the history and can clear it. The history survives deleting runs.

**Excluded companies:** set a default list in Settings, edit it per search in the wizard, or use *Exclude company* in
a job's detail panel.

## How a run works

1. **Resume analysis**: PDF/DOCX text (pypdf, python-docx) goes to Claude with a strict JSON schema. That gives
   years of experience, professional vs listed-only skills, verbatim measurable achievements, best-fit
   categories, realistic levels, gaps, and inconsistencies across multiple resumes. You can edit the profile before searching.
2. **Keywords**: two or three per role category, adjusted from the resume, and editable before starting.
3. **Cost check**: estimated items × price per platform. A run is refused if the estimate exceeds `MAX_RUN_COST_USD` or
   the remaining monthly Apify credit (`GET /v2/users/me/limits`).
4. **Scraping** (Apify, at most 10 concurrent runs, `maxTotalChargeUsd` on every run). HTTP 402 (free-plan
   memory/concurrency limit) is retried after 10–30 s instead of failing.
5. **Normalize → filter → dedupe**: HTML stripped, experience parsed, cities mapped, hard filters with reason codes
   (location, agency, seniority, irrelevant title, experience out of range). Cross-platform dedupe uses
   normalized company + title and is confirmed by description similarity (rapidfuzz ≥ 85) plus the same city. The
   most verifiable listing is kept and the others go to `alt_sources`.
6. **Rule-based pre-score** for every job. Jobs scoring 60+ are verified.
7. **Verification**: only *verified active* jobs reach the ranked list and the export (details below).
8. **LLM scoring**: the top 150 by pre-score, five per call, against a 100-point rubric. The rules and the
   resume profile are prompt-cached. Each response is validated against the schema and retried once. Jobs below
   `min_score` are dropped.
9. **Expand search** (when fewer than `target_count` jobs result): first synonym keywords, then a 14-day window,
   then deeper paging. The extra cost is shown and you must confirm. `min_score` is never lowered.

Every stage is idempotent and recorded per round, and Apify run/dataset IDs are stored. A crashed or restarted run resumes
from its last completed stage without paying Apify again. Logs are structured JSON, and every external call is
timed, with cost recorded where there is one.

## Costs per platform (approximate, free tier)

| Platform | Actor | Price | Per search | Memory |
|---|---|---|---|---|
| LinkedIn | `curious_coder~linkedin-jobs-scraper` | ~$0.002 / result | 25 results per URL, all URLs batched in one run | 512 MB |
| Naukri | `valig~naukri-jobs-scraper` | ~$0.0004 / result | 40 results, one run per keyword × location | 256 MB |
| Indeed | `valig~indeed-jobs-scraper` | ~$0.0001 / result | 40 results, one run per keyword × location | 256 MB |

Example: 6 keywords × (4 cities + remote) is 30 LinkedIn URLs (≈ $1.50) + 30 Naukri runs (≈ $0.48) +
30 Indeed runs (≈ $0.12), about $2.10 at most. Estimates assume every search returns its full limit, so real
spend is usually lower. LLM scoring with Sonnet 5.5 is roughly $0.04 per batch of 5 jobs.

## Verification

| Platform | Method | Result |
|---|---|---|
| LinkedIn | `GET /jobs-guest/jobs/api/jobPosting/{id}`, sequential, 1.2–1.5 s apart, retry on 429/5xx | "No longer accepting applications" → inactive · `apply-link-offsite` → active (company site) · `apply-link-onsite` → active, Easy Apply (excluded by default) · neither → uncertain |
| Naukri | Playwright (headless Chromium) renders the listing and reads `innerText` | "Posted:" + Apply and no expired text → active · captcha/block page → uncertain |
| Indeed | Scraped `expired` flag, then a fetch of the employer `jobUrl` (redirects followed) | apply text and no "no longer available / position filled / job closed" → active · unreachable, JS-only, or out-of-scope location (e.g. "Remote – US only") → uncertain |

Evidence for each check (matched strings, HTTP status, final URL, timestamp) is stored and shown in the job drawer.

## Compliance

- **No captcha solving or bypass, ever.** A captcha or block page marks the job *uncertain*.
- No logins and no login-gated pages; only public, logged-out views are read.
- Low request rates: LinkedIn checks are strictly sequential with 1.2–1.5 s gaps, Naukri renders are sequential with
  1.5–2.5 s gaps, and employer pages are fetched at most three at a time.
- robots.txt is checked before each verification fetch (`RESPECT_ROBOTS_TXT=true`), and disallowed URLs are never fetched.
  Some job sites disallow their job endpoints for generic crawlers. In that case those jobs stay *uncertain* and do not
  reach the ranked list. Turning the check off is your decision.
- Scraping goes through Apify actors under your Apify account. **You are responsible for complying with each site's
  terms of service** and with Apify's terms.

## Known limitations

- Indeed (`in.indeed.com/viewjob` returns 401/bot challenges) and Naukri (JS shell, reCAPTCHA on its JSON API)
  verification often ends up *uncertain*. Indeed jobs that apply on Indeed itself, without an employer URL, are always *uncertain*.
- Logged-out LinkedIn views can differ from logged-in ones (applicant counts, Easy Apply markers).
- Actor output fields can change; the mappers in `backend/app/scrapers/platforms.py` are defensive but may need updates.
- The cost estimate is an upper bound, and the Apify-reported `usageTotalUsd` is what gets recorded.
- Without `ANTHROPIC_API_KEY`, resume parsing and scoring use keyword heuristics, which are labelled as such in the UI and
  the export.

## Demo data

`python -m scripts.seed_demo` (or `make seed`) creates a sample two-resume candidate and runs the **whole pipeline** on
recorded actor datasets in `backend/fixtures/` (cross-posted duplicates, agencies, senior and irrelevant titles,
out-of-scope cities, closed and Easy Apply jobs). Verification runs the real classifiers on recorded pages, and nothing
touches the network. Add `--use-llm` to score with Claude, or `--export out.xlsx` to write the workbook. Expanding a demo
run also replays fixtures.

## API

| Method | Path | |
|---|---|---|
| POST | `/resumes` | multipart upload (one or more files) → parsed profile |
| PUT | `/resumes/{id}/profile` | save the edited profile |
| GET | `/settings/apify` | connection status, monthly usage and limit (never the token) |
| GET/PUT | `/settings` | model, blocklists, title and seniority exclusions |
| POST | `/keywords/suggest` | keywords for roles + resume |
| POST | `/runs` | create a draft run and get its cost estimate (`PATCH /runs/{id}` to edit) |
| POST | `/runs/{id}/start` · `/cancel` · `/expand` | start · cancel (aborts Apify runs) · expand (`{"confirm": false}` previews cost) |
| GET | `/runs/{id}` · `/runs/{id}/events` | status and stage counts · Server-Sent Events progress |
| GET | `/runs/{id}/jobs?status=&platform=&min_score=&q=&sort=&page=` | paginated job list |
| GET/PATCH | `/jobs/{id}` | full detail · set shortlisted/applied/rejected or a note |
| GET | `/runs/{id}/export.xlsx?full=false` | `LinkedIn_Naukri_Indeed_Ranked_Opportunities.xlsx` (`full=true` adds 5 report sheets) |
