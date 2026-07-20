from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional
import os


class Settings(BaseSettings):
    APP_NAME: str = "VideoShelf"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string-please"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    VIDEO_ROOT: Path = Path(os.getenv("VIDEO_ROOT", "/data/videos"))
    THUMBNAIL_DIR: Path = Path(os.getenv("THUMBNAIL_DIR", "/app/storage/thumbnails"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////app/database/video_manager.db")

    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    SUPPORTED_EXTENSIONS: set = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv", ".ts", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg", ".vob", ".f4v", ".asf", ".rm", ".rmvb", ".ogv"}
    THUMBNAIL_COUNT: int = 3
    THUMBNAIL_WIDTH: int = 480

    ALLOW_DELETE_FILES: bool = os.getenv("ALLOW_DELETE_FILES", "true").lower() == "true"
    ENABLE_WATCHER: bool = os.getenv("ENABLE_WATCHER", "true").lower() == "true"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
settings.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
Path("/app/database").mkdir(parents=True, exist_ok=True)
