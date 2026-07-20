from pathlib import Path
from typing import Optional
import re
from config import settings


def is_safe_path(path: Path, base: Path = None) -> bool:
    if base is None:
        base = settings.VIDEO_ROOT
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        return str(resolved).startswith(str(base_resolved))
    except (OSError, ValueError):
        return False


def get_relative_path(filepath: str | Path) -> str:
    p = Path(filepath)
    try:
        return str(p.relative_to(settings.VIDEO_ROOT))
    except ValueError:
        return str(p)


def resolve_video_path(relative_or_absolute: str) -> Optional[Path]:
    p = Path(relative_or_absolute)
    if not p.is_absolute():
        p = settings.VIDEO_ROOT / p
    if not is_safe_path(p):
        return None
    return p.resolve()


def sanitize_media_stem(filename: str, video_id: int | None = None) -> str:
    """从视频文件名得到可用于缩略图的安全主名（与视频名对应）。"""
    stem = Path(filename or "video").stem
    # 去掉不安全字符，保留中文、字母数字、下划线、横线、空格
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem)
    stem = stem.strip(" .")
    if not stem:
        stem = "video"
    # 限制长度，避免文件系统问题
    if len(stem) > 80:
        stem = stem[:80]
    # 附带 id 保证唯一（同名视频在不同目录时不冲突）
    if video_id is not None:
        return f"{stem}_{video_id}"
    return stem


def get_thumbnail_path(video_id: int, kind: str = "thumb", filename: str | None = None) -> Path:
    """
    缩略图路径。优先用视频文件名主名，保证与视频名对应。
    例如: 我的视频_12_thumb.jpg / 我的视频_12_preview_00.jpg
    """
    stem = sanitize_media_stem(filename or str(video_id), video_id)
    return settings.THUMBNAIL_DIR / f"{stem}_{kind}.jpg"


def thumb_rel_name(video_id: int, kind: str = "thumb", filename: str | None = None) -> str:
    return get_thumbnail_path(video_id, kind, filename).name
