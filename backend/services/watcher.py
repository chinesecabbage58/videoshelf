"""监控视频目录，有新增/修改文件时自动增量扫描。"""
import logging
import threading
import time
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_observer = None
_debounce_timer: Optional[threading.Timer] = None
_lock = threading.Lock()
DEBOUNCE_SECONDS = 8  # 连续写入时合并触发


def _run_scan():
    from database import SessionLocal
    from services.scanner import scan_directory
    try:
        db = SessionLocal()
        try:
            result = scan_directory(db, generate_thumbs=True, force_update=False)
            logger.info(
                f"[watcher] scan done: added={result.added}, updated={result.updated}, "
                f"skipped={result.skipped}, removed={result.removed}, errors={len(result.errors)}"
            )
        finally:
            db.close()
    except Exception as e:
        logger.exception(f"[watcher] scan failed: {e}")


def _schedule_scan():
    global _debounce_timer
    with _lock:
        if _debounce_timer is not None:
            _debounce_timer.cancel()
        _debounce_timer = threading.Timer(DEBOUNCE_SECONDS, _run_scan)
        _debounce_timer.daemon = True
        _debounce_timer.start()
        logger.info(f"[watcher] scheduled scan in {DEBOUNCE_SECONDS}s")


def is_watcher_running() -> bool:
    return _observer is not None and getattr(_observer, "is_alive", lambda: False)()


def start_watcher():
    """启动目录监控（后台线程）。"""
    global _observer
    if is_watcher_running():
        logger.info("[watcher] already running")
        return
    # 清理旧实例
    if _observer is not None:
        try:
            _observer.stop()
            _observer.join(timeout=3)
        except Exception:
            pass
        _observer = None
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        logger.warning("watchdog not installed, file watcher disabled")
        return

    class VideoHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
                logger.info(f"[watcher] created: {path.name}")
                _schedule_scan()

        def on_modified(self, event):
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
                logger.info(f"[watcher] modified: {path.name}")
                _schedule_scan()

        def on_moved(self, event):
            if event.is_directory:
                return
            dest = Path(event.dest_path)
            if dest.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
                logger.info(f"[watcher] moved: {dest.name}")
                _schedule_scan()

    root = settings.VIDEO_ROOT
    if not root.exists():
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"[watcher] cannot create video root: {e}")
            return

    observer = Observer()
    observer.schedule(VideoHandler(), str(root), recursive=True)
    observer.daemon = True
    observer.start()
    _observer = observer
    logger.info(f"[watcher] monitoring {root} (recursive)")


def stop_watcher():
    global _observer, _debounce_timer
    if _debounce_timer:
        _debounce_timer.cancel()
        _debounce_timer = None
    if _observer:
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None
        logger.info("[watcher] stopped")
