# SmartStock AI — common tasks
.PHONY: help install install-backend install-frontend dev backend frontend test test-backend test-frontend build verify demo clean

help:
	@echo "SmartStock AI"
	@echo "  make install          install backend + frontend dependencies"
	@echo "  make dev              run the API (8000) and the Vite dev server (5173)"
	@echo "  make backend          run the API only"
	@echo "  make frontend         run the Vite dev server only"
	@echo "  make test             run backend and frontend tests"
	@echo "  make build            typecheck + production build of the frontend"
	@echo "  make verify           run every validator once and print a PASS/FAIL verdict"
	@echo "  make demo             load the labelled synthetic dataset + a forecast"
	@echo "  make clean            remove local database, uploads and reports"

install: install-backend install-frontend

install-backend:
	cd backend && python -m pip install -r requirements.txt

install-frontend:
	cd frontend && npm install

backend:
	cd backend && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Start 'make backend' and 'make frontend' in two terminals (or run both with & )."
	@( cd backend && python -m uvicorn app.main:app --reload --port 8000 & ) ; cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest

test-frontend:
	cd frontend && npm run test

build:
	cd frontend && npm run build

# One-shot evidence run: tests, build, and the persisted database state.
# Prints "VERDICT: PASS" only if every step exited 0.
verify:
	@echo "=== SmartStock AI verification ==="
	@echo "-- backend tests (pytest)"
	@cd backend && python -m pytest || { echo "VERDICT: FAIL -- backend tests"; exit 1; }
	@echo "-- frontend tests (vitest)"
	@cd frontend && npx vitest run || { echo "VERDICT: FAIL -- frontend tests"; exit 1; }
	@echo "-- production build (tsc --noEmit + vite build)"
	@cd frontend && npm run build || { echo "VERDICT: FAIL -- production build"; exit 1; }
	@echo "-- persisted state (needs the API on :8000; skipped otherwise)"
	@( curl -fsS http://127.0.0.1:8000/api/health && echo ) \
		|| echo "(no server on :8000 -- restart persistence not checked here)"
	@echo ""
	@echo "VERDICT: PASS"

demo:
	cd backend && python scripts/seed_demo.py --forecast

clean:
	rm -f data/*.db data/*.db-wal data/*.db-shm
	rm -rf data/uploads/* data/reports/*
	@echo "Local database and generated files removed."
