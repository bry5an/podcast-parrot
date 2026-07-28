import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app import paths
from app.api import directory, episodes, profiles, progress
from app.db import engine, init_db
from app.services.recovery import recover_startup_state

FRONTEND_DIST = paths.resource_dir() / "frontend" / "dist"

_AUTH_EXEMPT_PATHS = {"/api/health"}


class AuthTokenMiddleware(BaseHTTPMiddleware):
    """Requires KOTOBA_AUTH_TOKEN (set per-launch by the packaged sidecar) on
    every /api/* request except health, so no other local process can drive
    this API. A no-op in dev, where the token is never set."""

    async def dispatch(self, request: Request, call_next):
        token = os.environ.get("KOTOBA_AUTH_TOKEN")
        if token and request.url.path.startswith("/api") and request.url.path not in _AUTH_EXEMPT_PATHS:
            if request.headers.get("x-kotoba-token") != token:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        recover_startup_state(session)
    yield


app = FastAPI(title="Kotoba", lifespan=lifespan)
app.add_middleware(AuthTokenMiddleware)

app.include_router(profiles.router)
app.include_router(directory.router)
app.include_router(episodes.router)
app.include_router(progress.router)


@app.get("/api/health", include_in_schema=False)
def health():
    return {"status": "ok"}


if FRONTEND_DIST.is_dir():

    @app.get("/", include_in_schema=False)
    def index():
        """Serves index.html with the per-launch auth token injected, so the
        SPA can attach it to its own /api/* requests. Registered ahead of the
        static mount below so this exact-path route wins over it."""
        html = (FRONTEND_DIST / "index.html").read_text()
        token = os.environ.get("KOTOBA_AUTH_TOKEN", "")
        injected = f"<script>window.KOTOBA_AUTH_TOKEN = {json.dumps(token)};</script></head>"
        return HTMLResponse(html.replace("</head>", injected, 1))

    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
