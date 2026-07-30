# Testing

## Running tests

```
make test            # backend + frontend
make test-backend     # cd backend && uv run pytest
make test-frontend     # cd frontend && npm run test
```

Backend tests live in `backend/tests/`, split into `unit/` and `integration/`. Integration tests exercise the FastAPI app through `TestClient`, including `tests/integration/test_health_and_auth.py`, which requires a built frontend (`frontend/dist`) to exist — `app.main` only registers the `/` route (index.html with the auth token injected) when it does. Run `cd frontend && npm run build` first if that test is failing locally for no obvious reason.

Frontend tests live alongside the source they cover (`*.test.tsx`) and run with Vitest + Testing Library under `happy-dom`.

## Linting

```
make lint
```

Backend: `uv run ruff check .`. Frontend: `npm run lint` (oxlint).

## Continuous integration

`.github/workflows/ci.yml` runs on every PR into `main` and on `v*` tags, as three jobs:

- **backend** — builds the frontend (needed for the health/auth integration test, see above), then runs `uv sync --locked`, `pytest`, and `ruff check .`.
- **frontend** — `npm ci`, `npm run build`, `npm run lint`, `npm run test`.
- **macos** — a full Tauri build (`prepare_sidecars.sh` + `tauri build -b app dmg`) followed by `desktop/scripts/smoke_test.sh`, which launches the bundled app's actual embedded binary and asserts `/api/health` responds. This job is gated behind a `changes` job that only runs it on PRs touching `backend/`, `desktop/`, or `frontend/` (docs-only PRs skip it); tag pushes always run it. It's the slowest job (up to 45 minutes) since it builds whisper.cpp from source — see [`development.md`](development.md#desktop-app-tauri) for why — though that build is cached between runs keyed on `prepare_sidecars.sh`.

Only the `macos` job builds a `.dmg`; it's uploaded as a workflow artifact (`kotoba-macos-dmg`), not published as a GitHub Release.

## Manual verification

For UI changes, it's worth actually running the app (`make dev-web` or `make dev`) and exercising the feature in a browser or the native window rather than relying on the test suite alone — the test suite verifies code correctness, not that a feature behaves the way a user expects.
