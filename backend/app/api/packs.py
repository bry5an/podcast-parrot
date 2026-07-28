from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlmodel import SQLModel

from app.services import packs

router = APIRouter(prefix="/api", tags=["packs"])


class PackRead(SQLModel):
    name: str
    download_size_bytes: int
    installed: bool


class PackStatusRead(SQLModel):
    state: str
    bytes_done: int
    bytes_total: int
    error: str | None


def _require_catalog_entry(name: str) -> None:
    if name not in packs.CATALOG:
        raise HTTPException(status_code=404, detail="Unknown pack")


@router.get("/packs", response_model=list[PackRead])
def list_packs():
    return packs.list_packs()


@router.post("/packs/{name}", response_model=PackRead, status_code=202)
def start_pack_install(name: str, background_tasks: BackgroundTasks):
    _require_catalog_entry(name)

    entry = next(p for p in packs.list_packs() if p["name"] == name)
    if not entry["installed"] and not packs.is_downloading(name):
        background_tasks.add_task(packs.install_pack, name)

    return PackRead(**entry)


@router.get("/packs/{name}/status", response_model=PackStatusRead)
def get_pack_status(name: str):
    _require_catalog_entry(name)
    return packs.get_status(name)


@router.delete("/packs/{name}", status_code=204)
def delete_pack(name: str):
    _require_catalog_entry(name)
    packs.delete_pack(name)
