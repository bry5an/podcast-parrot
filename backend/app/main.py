from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import paths
from app.api import directory, episodes, models, profiles, progress
from app.db import engine, init_db
from app.services.recovery import recover_startup_state

FRONTEND_DIST = paths.resource_dir() / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        recover_startup_state(session)
    yield


app = FastAPI(title="Kotoba", lifespan=lifespan)

app.include_router(profiles.router)
app.include_router(directory.router)
app.include_router(episodes.router)
app.include_router(models.router)
app.include_router(progress.router)

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
