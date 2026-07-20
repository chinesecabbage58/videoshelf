import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

from utils.path import get_thumbnail_path, thumb_rel_name

logger = logging.getLogger(__name__)


def generate_thumbnail(
    video_path: Path,
    video_id: int,
    duration: Optional[float] = None,
    num_previews: int = 4,
    filename: Optional[str] = None,
) -> Tuple[Optional[str], List[str]]:
    """
    生成封面和预览图。
    文件名与视频名称对应：{视频主名}_{id}_thumb.jpg / _preview_00.jpg
    """
    name = filename or video_path.name
    thumb_path = get_thumbnail_path(video_id, "thumb", name)
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    if duration and duration > 10:
        seek_time = min(duration * 0.1, 30)
    elif duration and duration > 2:
        seek_time = duration * 0.3
    else:
        seek_time = 0

    vf = "scale=640:360:force_original_aspect_ratio=increase,crop=640:360"

    def _run_ffmpeg(seek: float, output: Path) -> bool:
        try:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(max(0, seek)),
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", vf,
                "-q:v", "3",
                str(output),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                err = (proc.stderr or "")[-300:]
                logger.warning(f"ffmpeg failed (seek={seek}): {err}")
                return False
            return output.exists() and output.stat().st_size > 0
        except Exception as e:
            logger.error(f"ffmpeg exception: {e}")
            return False

    success = _run_ffmpeg(seek_time, thumb_path)
    if not success and seek_time > 0:
        success = _run_ffmpeg(0, thumb_path)
    if not success:
        logger.error(f"Failed to generate thumbnail for video_id={video_id}")
        return None, []

    thumbnail_rel = thumb_rel_name(video_id, "thumb", name)
    previews: List[str] = []

    if duration and duration > 3 and num_previews > 0:
        for i in range(num_previews):
            t = duration * (i + 1) / (num_previews + 1)
            kind = f"preview_{i:02d}"
            prev_path = get_thumbnail_path(video_id, kind, name)
            if _run_ffmpeg(t, prev_path):
                previews.append(thumb_rel_name(video_id, kind, name))

    return thumbnail_rel, previews


def regenerate_thumbnail(
    video_path: Path,
    video_id: int,
    duration: Optional[float] = None,
    num_previews: int = 4,
    filename: Optional[str] = None,
) -> Tuple[Optional[str], List[str]]:
    name = filename or video_path.name
    return generate_thumbnail(
        video_path, video_id, duration, num_previews=num_previews, filename=name
    )
