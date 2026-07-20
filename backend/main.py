import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from config import settings
from database import init_db, SessionLocal
from api import auth, videos, tags, scan, categories, settings as settings_api
from models.user import User
from utils.security import get_password_hash

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("video-manager")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    db = SessionLocal()
    try:
        if not db.query(User).first():
            admin = User(
                username=settings.ADMIN_USERNAME,
                hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            logger.info(f"Created default admin user: {settings.ADMIN_USERNAME}")
    finally:
        db.close()
    settings.THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    Path("/app/database").mkdir(parents=True, exist_ok=True)
    logger.info(f"Video root: {settings.VIDEO_ROOT}")
    logger.info("VideoShelf ready.")

    # 启动后自动增量扫描（后台线程，不阻塞启动）
    import threading
    def _auto_scan():
        try:
            from services.scanner import scan_directory
            from database import SessionLocal
            logger.info("Auto incremental scan started...")
            s = SessionLocal()
            try:
                r = scan_directory(s, generate_thumbs=True, force_update=False)
                logger.info(f"Auto scan done: added={r.added}, updated={r.updated}, skipped={r.skipped}, removed={r.removed}")
            finally:
                s.close()
        except Exception as e:
            logger.exception(f"Auto scan failed: {e}")
    threading.Thread(target=_auto_scan, daemon=True).start()

    # 目录监控：优先读 Web 设置 enable_watcher，否则用环境变量 ENABLE_WATCHER
    try:
        watcher_on = settings.ENABLE_WATCHER
        try:
            import json
            from pathlib import Path as _P
            sf = _P("/app/database/app_settings.json")
            if sf.exists():
                data = json.loads(sf.read_text(encoding="utf-8"))
                if "enable_watcher" in data:
                    watcher_on = bool(data["enable_watcher"])
        except Exception:
            pass
        if watcher_on:
            from services.watcher import start_watcher, stop_watcher
            start_watcher()
        else:
            logger.info("File watcher disabled by settings")
    except Exception as e:
        logger.exception(f"Failed to start file watcher: {e}")

    yield

    try:
        from services.watcher import stop_watcher
        stop_watcher()
    except Exception:
        pass
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(tags.router)
app.include_router(scan.router)
app.include_router(categories.router)
app.include_router(settings_api.router)

app.mount(
    "/thumbnails",
    StaticFiles(directory=str(settings.THUMBNAIL_DIR)),
    name="thumbnails",
)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "video_root": str(settings.VIDEO_ROOT),
    }


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("thumbnails/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    file_path = FRONTEND_DIR / full_path
    if file_path.is_file():
        return FileResponse(file_path)
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {"message": "Frontend not built. API is available at /api/docs", "docs": "/api/docs"}
    )
