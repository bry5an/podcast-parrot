from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import paths
from app.api import directory, episodes, profiles, progress
from app.db import init_db

FRONTEND_DIST = paths.resource_dir() / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Kotoba", lifespan=lifespan)

app.include_router(profiles.router)
app.include_router(directory.router)
app.include_router(episodes.router)
app.include_router(progress.router)

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
