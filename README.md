# Job Apply

Extract job postings from URLs, track them, and (later) automate the apply workflow.

- **Backend:** Python, FastAPI, SQLAlchemy 2, SQLite (swap via `DATABASE_URL`)
- **Frontend:** React 18, TypeScript, Vite, React Router

## Project structure

```
job-apply/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, CORS, router mount, table creation
│   │   ├── core/                    # settings (env-driven) and DB session
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── api/v1/
│   │   │   ├── router.py
│   │   │   └── endpoints/           # health, jobs (CRUD), extraction
│   │   └── services/
│   │       ├── job_service.py       # DB operations for jobs
│   │       └── extraction/          # fetch + pluggable extractors
│   │           ├── fetcher.py       # httpx page download
│   │           ├── base.py          # BaseExtractor interface
│   │           ├── jsonld.py        # schema.org JobPosting parser
│   │           ├── generic.py       # OpenGraph/meta fallback
│   │           └── registry.py      # ordered list of extractors
│   ├── tests/
│   └── requirements*.txt
├── frontend/
│   └── src/
│       ├── api/                     # typed fetch client + endpoints
│       ├── types/                   # shared TS types mirroring the API schemas
│       ├── hooks/                   # data hooks (useJobs)
│       ├── components/              # Layout, JobCard, StatusSelect
│       └── pages/                   # Jobs list, Extract, Job detail
└── docker-compose.yml
```

## Running locally

**Backend** (http://localhost:8000, docs at `/docs`):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # optional
uvicorn app.main:app --reload
```

**Frontend** (http://localhost:5173, proxies `/api` to the backend):

```bash
cd frontend
npm install
npm run dev
```

**Or with Docker:** `docker compose up --build`

## API

| Method | Path                    | Purpose                                         |
| ------ | ----------------------- | ----------------------------------------------- |
| GET    | `/api/v1/health`        | Health check                                    |
| GET    | `/api/v1/jobs`          | List jobs (`status`, `q`, `skip`, `limit`)      |
| POST   | `/api/v1/jobs`          | Create a job (upserts by `source_url`)          |
| GET    | `/api/v1/jobs/{id}`     | Get a job                                       |
| PATCH  | `/api/v1/jobs/{id}`     | Update fields, status or notes                  |
| DELETE | `/api/v1/jobs/{id}`     | Delete a job                                    |
| POST   | `/api/v1/extract`       | `{url, save}` → fetch, parse and optionally save |

Job statuses: `new`, `saved`, `applied`, `interviewing`, `offer`, `rejected`.

## How extraction works

`POST /extract` downloads the page, then tries each extractor in `registry.EXTRACTORS` in order
and returns the first result:

1. **`jsonld`** – reads the schema.org `JobPosting` JSON-LD most job boards embed for SEO
   (title, company, location, salary, employment type, description).
2. **`generic`** – falls back to OpenGraph/meta tags and the page title.

Re-extracting a URL refreshes the scraped fields but keeps your `status` and `notes`.

### Adding a site-specific extractor

```python
# app/services/extraction/greenhouse.py
class GreenhouseExtractor(BaseExtractor):
    name = "greenhouse"

    def can_handle(self, url):
        return "greenhouse.io" in url

    def extract(self, url, soup):
        ...  # return JobCreate(...) or None
```

Then add it to the front of `EXTRACTORS` in `registry.py`.

Pages that render jobs entirely with JavaScript (e.g. LinkedIn) won't contain the data in the raw
HTML; those need a headless browser (Playwright) fetcher or an official API.

## Tests

```bash
cd backend && pytest          # API + extractor tests, no network needed
cd frontend && npm run build  # typecheck + production build
```

## Next steps

- Alembic migrations (tables are currently created on startup)
- Playwright fetcher for JS-rendered pages
- Bulk extraction from job search result pages
- Resume/profile storage and the apply workflow
