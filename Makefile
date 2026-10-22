# JobRadar developer commands. Windows users: run these from Git Bash, or copy the commands.

PY ?= backend/.venv/bin/python
ifeq ($(OS),Windows_NT)
PY := backend/.venv/Scripts/python
endif

.PHONY: install dev api web worker lint seed up down seed-docker logs

install:  ## Create the backend venv and install backend + frontend dependencies
	cd backend && python -m venv .venv
	$(PY) -m pip install -r backend/requirements.txt
	$(PY) -m playwright install chromium
	cd frontend && npm install

dev:  ## API (port 8000, in-process runs) + Vite dev server (port 5173)
	$(MAKE) -j2 api web

api:
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

worker:  ## Optional: arq worker (needs REDIS_URL)
	cd backend && ../$(PY) -m arq app.worker.WorkerSettings

lint:  ## ruff for the backend, TypeScript type-check for the frontend
	cd backend && ../$(PY) -m ruff check app scripts alembic
	cd frontend && npm run lint

seed:  ## Load the offline demo run (recorded fixtures, no Apify spend)
	cd backend && ../$(PY) -m scripts.seed_demo

up:  ## Build and start api, worker, web and redis (UI on http://localhost:8080)
	docker compose up --build -d

down:
	docker compose down

seed-docker:  ## Load the demo run inside the running compose stack
	docker compose exec api python -m scripts.seed_demo

logs:
	docker compose logs -f api worker
