from typing import Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, SessionLocal
from models.user import User
from utils.security import get_current_active_user
from services.scanner import scan_directory, get_scan_status, ScanResult

router = APIRouter(prefix="/api/scan", tags=["scan"])


class ScanStatus(BaseModel):
    total_videos: int
    with_thumbnail: int
    without_thumbnail: int


class ScanResponse(BaseModel):
    message: str
    added: int = 0
    updated: int = 0
    skipped: int = 0
    removed: int = 0
    total_found: int = 0
    errors: list = []


_scan_running = False
_last_result: Optional[dict] = None


@router.get("/status", response_model=ScanStatus)
async def scan_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return get_scan_status(db)


@router.get("/last")
async def last_scan(
    current_user: User = Depends(get_current_active_user),
):
    global _last_result, _scan_running
    return {
        "running": _scan_running,
        "last_result": _last_result,
    }


@router.post("", response_model=ScanResponse)
async def start_scan(
    background_tasks: BackgroundTasks,
    force: bool = False,
    generate_thumbs: bool = True,
    current_user: User = Depends(get_current_active_user),
):
    global _scan_running, _last_result

    if _scan_running:
        raise HTTPException(status_code=409, detail="Scan already running")

    def _run_scan():
        global _scan_running, _last_result
        _scan_running = True
        db = SessionLocal()
        try:
            result: ScanResult = scan_directory(
                db,
                generate_thumbs=generate_thumbs,
                force_update=force,
            )
            _last_result = {
                "added": result.added,
                "updated": result.updated,
                "skipped": result.skipped,
                "removed": result.removed,
                "total_found": result.total_found,
                "errors": result.errors[:20],
            }
        except Exception as e:
            _last_result = {"error": str(e)}
        finally:
            db.close()
            _scan_running = False

    background_tasks.add_task(_run_scan)
    return ScanResponse(message="Scan started in background")


@router.post("/sync")
async def sync_scan(
    force: bool = False,
    generate_thumbs: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    global _scan_running
    if _scan_running:
        raise HTTPException(status_code=409, detail="Scan already running")
    _scan_running = True
    try:
        result = scan_directory(db, generate_thumbs=generate_thumbs, force_update=force)
        return ScanResponse(
            message="Scan completed",
            added=result.added,
            updated=result.updated,
            skipped=result.skipped,
            removed=result.removed,
            total_found=result.total_found,
            errors=result.errors[:20],
        )
    finally:
        _scan_running = False
