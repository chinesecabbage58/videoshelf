from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import json
from pathlib import Path

from database import get_db
from models.user import User
from utils.security import get_current_active_user
from config import settings as app_config

router = APIRouter(prefix="/api/settings", tags=["settings"])

SETTINGS_FILE = Path("/app/database/app_settings.json")

DEFAULTS = {
    "preview_count": 4,
    "page_size": 24,
    "mgmt_page_size": 20,
    "refresh_enabled": False,
    "refresh_interval": "1440",
    "refresh_custom_min": 60,
    "enable_watcher": True,
}


def _load() -> dict:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            out = DEFAULTS.copy()
            out.update({k: v for k, v in data.items() if k in DEFAULTS})
            return out
    except Exception:
        pass
    return DEFAULTS.copy()


def _save(data: dict) -> dict:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    cur = _load()
    for k in DEFAULTS:
        if k in data and data[k] is not None:
            cur[k] = data[k]
    SETTINGS_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


class AppSettings(BaseModel):
    preview_count: int = Field(4, ge=0, le=20)
    page_size: int = Field(24, ge=6, le=100)
    mgmt_page_size: int = Field(20, ge=5, le=100)
    refresh_enabled: bool = False
    refresh_interval: str = "1440"
    refresh_custom_min: int = Field(60, ge=5, le=10080)
    enable_watcher: bool = True


class AppSettingsUpdate(BaseModel):
    preview_count: Optional[int] = Field(None, ge=0, le=20)
    page_size: Optional[int] = Field(None, ge=6, le=100)
    mgmt_page_size: Optional[int] = Field(None, ge=5, le=100)
    refresh_enabled: Optional[bool] = None
    refresh_interval: Optional[str] = None
    refresh_custom_min: Optional[int] = Field(None, ge=5, le=10080)
    enable_watcher: Optional[bool] = None


@router.get("", response_model=AppSettings)
async def get_settings(current_user: User = Depends(get_current_active_user)):
    return AppSettings(**_load())


@router.put("", response_model=AppSettings)
async def update_settings(
    data: AppSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
):
    payload = data.model_dump(exclude_unset=True)
    result = _save(payload)
    # 运行时开关文件监控
    if "enable_watcher" in payload:
        try:
            from services.watcher import start_watcher, stop_watcher, is_watcher_running
            if payload["enable_watcher"]:
                if not is_watcher_running():
                    start_watcher()
            else:
                stop_watcher()
        except Exception:
            pass
    return AppSettings(**result)
