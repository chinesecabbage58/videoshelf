import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from models.video import Video
from services.video_info import get_video_metadata
from services.thumbnail import generate_thumbnail
from utils.path import get_relative_path, is_safe_path

logger = logging.getLogger(__name__)


class ScanResult:
    def __init__(self):
        self.added = 0
        self.updated = 0
        self.skipped = 0
        self.removed = 0
        self.errors: List[str] = []
        self.total_found = 0


def scan_directory(
    db: Session,
    root: Optional[Path] = None,
    generate_thumbs: bool = True,
    force_update: bool = False,
) -> ScanResult:
    if root is None:
        root = settings.VIDEO_ROOT

    result = ScanResult()

    if not root.exists():
        logger.warning(f"Video root does not exist: {root}")
        result.errors.append(f"Directory not found: {root}")
        return result

    if not is_safe_path(root, settings.VIDEO_ROOT):
        result.errors.append("Invalid scan path")
        return result

    # 收集文件
    video_files: List[Path] = []
    for ext in settings.SUPPORTED_EXTENSIONS:
        video_files.extend(root.rglob(f"*{ext}"))
        video_files.extend(root.rglob(f"*{ext.upper()}"))
    video_files = list({p.resolve() for p in video_files if p.is_file()})
    result.total_found = len(video_files)

    for fpath in video_files:
        try:
            # 每次处理前确保 session 干净
            try:
                db.rollback()
            except Exception:
                pass

            if not is_safe_path(fpath):
                result.skipped += 1
                continue

            abs_path = str(fpath.resolve())
            rel_path = get_relative_path(fpath)
            meta = get_video_metadata(fpath)

            # 每次重新查询，避免脏对象
            video = db.query(Video).filter(Video.filepath == abs_path).first()

            if video:
                need_update = force_update or video.filesize != meta["filesize"]
                if video.file_modified and meta.get("file_modified"):
                    if video.file_modified != meta["file_modified"]:
                        need_update = True

                if need_update:
                    video.filename = fpath.name
                    video.relative_path = rel_path
                    video.filesize = meta["filesize"] or 0
                    video.duration = meta.get("duration")
                    video.width = meta.get("width")
                    video.height = meta.get("height")
                    video.codec = meta.get("codec")
                    video.audio_codec = meta.get("audio_codec")
                    video.bitrate = meta.get("bitrate")
                    video.fps = meta.get("fps")
                    video.file_created = meta.get("file_created")
                    video.file_modified = meta.get("file_modified")
                    video.scanned_at = datetime.utcnow()
                    video.updated_at = datetime.utcnow()
                    db.commit()
                    result.updated += 1
                else:
                    result.skipped += 1
            else:
                video = Video(
                    filename=fpath.name,
                    filepath=abs_path,
                    relative_path=rel_path,
                    filesize=meta.get("filesize") or 0,
                    duration=meta.get("duration"),
                    width=meta.get("width"),
                    height=meta.get("height"),
                    codec=meta.get("codec"),
                    audio_codec=meta.get("audio_codec"),
                    bitrate=meta.get("bitrate"),
                    fps=meta.get("fps"),
                    file_created=meta.get("file_created"),
                    file_modified=meta.get("file_modified"),
                    scanned_at=datetime.utcnow(),
                )
                db.add(video)
                db.commit()
                db.refresh(video)
                result.added += 1

            # 生成缩略图
            if generate_thumbs and video and video.id:
                if not video.thumbnail or force_update:
                    try:
                        thumb, previews = generate_thumbnail(
                            fpath, video.id, meta.get("duration"),
                            filename=video.filename or fpath.name,
                        )
                        if thumb:
                            # 重新取对象再写，避免 session 问题
                            v2 = db.query(Video).filter(Video.id == video.id).first()
                            if v2:
                                v2.thumbnail = thumb
                                v2.preview_images = json.dumps(previews)
                                db.commit()
                    except Exception as te:
                        logger.warning(f"Thumbnail failed for {fpath.name}: {te}")
                        try:
                            db.rollback()
                        except Exception:
                            pass

        except Exception as e:
            logger.exception(f"Error processing {fpath}")
            result.errors.append(f"{fpath.name}: {str(e)[:200]}")
            try:
                db.rollback()
            except Exception:
                pass

    # 清理数据库中已不存在的视频（切换目录 / 删除文件后同步）
    try:
        existing_paths = {str(p.resolve()) for p in video_files}
        all_db_videos = db.query(Video).all()
        for v in all_db_videos:
            if v.filepath not in existing_paths:
                # 删除对应缩略图
                # 删除缩略图（兼容旧 id 命名 + 新「视频名_id」命名）
                to_del = set()
                if v.thumbnail:
                    to_del.add(settings.THUMBNAIL_DIR / v.thumbnail)
                try:
                    import json as _json
                    for rel in (_json.loads(v.preview_images) if v.preview_images else []):
                        to_del.add(settings.THUMBNAIL_DIR / rel)
                except Exception:
                    pass
                for p in settings.THUMBNAIL_DIR.glob(f"{v.id}_*.jpg"):
                    to_del.add(p)
                for p in settings.THUMBNAIL_DIR.glob(f"*_{v.id}_*.jpg"):
                    to_del.add(p)
                for p in to_del:
                    try:
                        if p.exists():
                            p.unlink()
                    except OSError:
                        pass
                db.delete(v)
                result.removed += 1
        if result.removed:
            db.commit()
            logger.info(f"Pruned {result.removed} missing videos from database")
    except Exception as e:
        logger.exception(f"Prune missing videos failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass

    return result


def get_scan_status(db: Session) -> Dict[str, Any]:
    total = db.query(Video).count()
    with_thumb = db.query(Video).filter(Video.thumbnail.isnot(None)).count()
    return {
        "total_videos": total,
        "with_thumbnail": with_thumb,
        "without_thumbnail": total - with_thumb,
    }
