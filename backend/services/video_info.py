import json
import subprocess
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_video_metadata(filepath: Path) -> Dict[str, Any]:
    result = {
        "duration": None,
        "width": None,
        "height": None,
        "codec": None,
        "audio_codec": None,
        "bitrate": None,
        "fps": None,
        "filesize": 0,
        "file_created": None,
        "file_modified": None,
    }

    if not filepath.exists():
        return result

    try:
        result["filesize"] = filepath.stat().st_size
        stat = filepath.stat()
        result["file_modified"] = datetime.fromtimestamp(stat.st_mtime)
        result["file_created"] = datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_ctime))
    except OSError as e:
        logger.warning(f"Cannot stat {filepath}: {e}")

    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(filepath),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            logger.warning(f"ffprobe failed for {filepath}: {proc.stderr}")
            return result

        data = json.loads(proc.stdout)

        fmt = data.get("format", {})
        if "duration" in fmt:
            result["duration"] = float(fmt["duration"])
        if "bit_rate" in fmt:
            try:
                result["bitrate"] = int(fmt["bit_rate"])
            except (ValueError, TypeError):
                pass

        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type")
            if codec_type == "video" and result["width"] is None:
                result["width"] = stream.get("width")
                result["height"] = stream.get("height")
                result["codec"] = stream.get("codec_name")
                avg_frame_rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
                if avg_frame_rate and "/" in str(avg_frame_rate):
                    num, den = avg_frame_rate.split("/")
                    try:
                        if float(den) != 0:
                            result["fps"] = round(float(num) / float(den), 2)
                    except (ValueError, ZeroDivisionError):
                        pass
            elif codec_type == "audio" and result["audio_codec"] is None:
                result["audio_codec"] = stream.get("codec_name")

    except subprocess.TimeoutExpired:
        logger.error(f"ffprobe timeout for {filepath}")
    except Exception as e:
        logger.error(f"Error getting metadata for {filepath}: {e}")

    return result
