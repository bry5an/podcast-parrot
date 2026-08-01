.PHONY: help install dev dev-web dev-backend dev-frontend sidecars build test test-backend test-frontend lint clean

help:
	@echo "podcast-parrot (Ausculto) — make targets"
	@echo ""
	@echo "  install       Install backend + frontend dependencies"
	@echo "  dev           Build sidecars and run the full desktop app (npx tauri dev)"
	@echo "  dev-web       Run backend + frontend dev servers only (no Tauri shell)"
	@echo "  dev-backend   Run the backend dev server alone (uvicorn --reload :8420)"
	@echo "  dev-frontend  Run the frontend dev server alone (vite)"
	@echo "  sidecars      Build the kotoba-backend + whisper-cli sidecars for Tauri"
	@echo "  build         Build the distributable desktop app (.app + .dmg)"
	@echo "  test          Run backend + frontend test suites"
	@echo "  lint          Lint backend (ruff) + frontend (oxlint)"
	@echo "  clean         Remove build artifacts (dist/, build/, sidecar binaries)"

install:
	cd backend && uv sync
	cd frontend && npm install

dev: sidecars
	cd desktop && npx tauri dev

dev-web:
	@trap 'kill 0' EXIT INT TERM; \
	(cd backend && uv run uvicorn app.main:app --reload --port 8420) & \
	(cd frontend && npm run dev) & \
	wait

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8420

dev-frontend:
	cd frontend && npm run dev

sidecars:
	./desktop/scripts/prepare_sidecars.sh

build: sidecars
	cd desktop && npx tauri build -b app dmg

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm run test

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

clean:
	rm -rf backend/build backend/dist frontend/dist
	rm -rf desktop/src-tauri/binaries desktop/src-tauri/target
