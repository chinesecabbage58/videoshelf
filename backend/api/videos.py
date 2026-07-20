import json
import mimetypes
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import desc, asc
from pydantic import BaseModel, Field
from jose import jwt, JWTError

from database import get_db
from models.video import Video, Tag
from models.user import User
from utils.security import get_current_active_user, get_user_by_username
from utils.path import is_safe_path, get_relative_path
from config import settings
from services.thumbnail import regenerate_thumbnail

router = APIRouter(prefix="/api/videos", tags=["videos"])


class TagOut(BaseModel):
    id: int
    name: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class CategoryOut(BaseModel):
    id: int
    name: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class VideoOut(BaseModel):
    id: int
    filename: str
    relative_path: str
    filesize: int
    duration: Optional[float]
    duration_str: str
    resolution: Optional[str]
    width: Optional[int]
    height: Optional[int]
    codec: Optional[str]
    audio_codec: Optional[str]
    bitrate: Optional[int]
    fps: Optional[float]
    thumbnail: Optional[str]
    preview_images: Optional[List[str]] = None
    rating: int
    score: Optional[int]
    favorite: bool
    notes: Optional[str]
    file_created: Optional[datetime]
    file_modified: Optional[datetime]
    scanned_at: datetime
    tags: List[TagOut] = []
    category: Optional[CategoryOut] = None
    category_id: Optional[int] = None

    class Config:
        from_attributes = True


class VideoUpdate(BaseModel):
    filename: Optional[str] = Field(None, min_length=1, max_length=512)
    rating: Optional[int] = Field(None, ge=0, le=5)
    score: Optional[int] = Field(None, ge=0, le=10)
    favorite: Optional[bool] = None
    notes: Optional[str] = None
    tag_ids: Optional[List[int]] = None
    category_id: Optional[int] = None


class VideoListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[VideoOut]


def video_to_out(v: Video) -> VideoOut:
    previews = []
    if v.preview_images:
        try:
            previews = json.loads(v.preview_images)
        except Exception:
            pass
    return VideoOut(
        id=v.id,
        filename=v.filename,
        relative_path=v.relative_path,
        filesize=v.filesize,
        duration=v.duration,
        duration_str=v.duration_str,
        resolution=v.resolution,
        width=v.width,
        height=v.height,
        codec=v.codec,
        audio_codec=v.audio_codec,
        bitrate=v.bitrate,
        fps=v.fps,
        thumbnail=v.thumbnail,
        preview_images=previews,
        rating=v.rating,
        score=v.score,
        favorite=v.favorite,
        notes=v.notes,
        file_created=v.file_created,
        file_modified=v.file_modified,
        scanned_at=v.scanned_at,
        tags=[TagOut.model_validate(t) for t in v.tags],
        category=CategoryOut.model_validate(v.category) if v.category else None,
        category_id=v.category_id,
    )


def _authenticate_by_token(token: str, db: Session) -> Optional[User]:
    """通过 token 字符串验证用户"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username: str = payload.get("sub")
        if not username:
            return None
        return get_user_by_username(db, username)
    except JWTError:
        return None


@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    q: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    tag_id: Optional[int] = Query(None),
    tag_ids: Optional[str] = Query(None, description="逗号分隔的多个标签ID，如 1,2,3"),
    favorite: Optional[bool] = Query(None),
    min_rating: Optional[int] = Query(None, ge=0, le=5),
    folder: Optional[str] = Query(None),
    category_id: Optional[int] = Query(None),
    sort: str = Query("scanned_at"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(Video).options(selectinload(Video.tags), joinedload(Video.category))

    if q:
        from models.video import Category
        from sqlalchemy import or_
        q_like = f"%{q}%"
        query = query.outerjoin(Video.tags).outerjoin(Category, Video.category_id == Category.id).filter(
            or_(
                Video.filename.ilike(q_like),
                Video.notes.ilike(q_like),
                Tag.name.ilike(q_like),
                Category.name.ilike(q_like),
            )
        ).distinct()
    if tag:
        query = query.join(Video.tags).filter(Tag.name == tag).distinct()
    if tag_id:
        query = query.join(Video.tags).filter(Tag.id == tag_id).distinct()
    if tag_ids:
        try:
            ids = [int(x.strip()) for x in tag_ids.split(',') if x.strip().isdigit()]
        except Exception:
            ids = []
        if ids:
            query = query.join(Video.tags).filter(Tag.id.in_(ids)).distinct()
    if favorite is not None:
        query = query.filter(Video.favorite == favorite)
    if min_rating is not None:
        query = query.filter(Video.rating >= min_rating)
    if folder:
        folder = folder.strip("/").replace("..", "")
        query = query.filter(Video.relative_path.like(f"{folder}%"))
    if category_id is not None:
        query = query.filter(Video.category_id == category_id)

    sort_map = {
        "filename": Video.filename,
        "filesize": Video.filesize,
        "duration": Video.duration,
        "rating": Video.rating,
        "scanned_at": Video.scanned_at,
        "file_modified": Video.file_modified,
        "created": Video.file_created,
    }
    sort_col = sort_map.get(sort, Video.scanned_at)
    query = query.order_by(desc(sort_col) if order == "desc" else asc(sort_col))

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return VideoListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[video_to_out(v) for v in items],
    )




@router.post("/regenerate-all-thumbnails")
async def regen_all_thumbs(
    background_tasks: BackgroundTasks,
    preview_count: int = Query(4, ge=0, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """按指定预览图数量，后台批量重新生成所有视频的封面与预览帧"""
    videos = db.query(Video).all()
    ids = [v.id for v in videos]

    def _do_all():
        from database import SessionLocal
        from pathlib import Path as P
        import json as _json
        session = SessionLocal()
        try:
            for vid in ids:
                v = session.query(Video).filter(Video.id == vid).first()
                if not v:
                    continue
                path = P(v.filepath)
                if not path.exists():
                    continue
                try:
                    thumb, previews = regenerate_thumbnail(
                        path, vid, v.duration, num_previews=preview_count,
                        filename=v.filename or path.name,
                    )
                    if thumb:
                        v.thumbnail = thumb
                        v.preview_images = _json.dumps(previews)
                        session.commit()
                except Exception:
                    try:
                        session.rollback()
                    except Exception:
                        pass
        finally:
            session.close()

    background_tasks.add_task(_do_all)
    return {"message": "批量重新生成已开始", "total": len(ids), "preview_count": preview_count}


@router.get("/{video_id}", response_model=VideoOut)
async def get_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    video = (
        db.query(Video)
        .options(selectinload(Video.tags), joinedload(Video.category))
        .filter(Video.id == video_id)
        .first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video_to_out(video)


@router.patch("/{video_id}", response_model=VideoOut)
async def update_video(
    video_id: int,
    data: VideoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    video = (
        db.query(Video)
        .options(selectinload(Video.tags), joinedload(Video.category))
        .filter(Video.id == video_id)
        .first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if data.filename is not None:
        new_name = data.filename.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="文件名不能为空")
        if new_name != video.filename:
            old_name = video.filename
            old_path = Path(video.filepath)
            # 同时重命名源文件（仅当文件存在且在安全路径内）
            if old_path.exists() and is_safe_path(old_path):
                new_path = old_path.parent / new_name
                if new_path.exists() and new_path.resolve() != old_path.resolve():
                    raise HTTPException(status_code=400, detail="目标文件名已存在")
                try:
                    old_path.rename(new_path)
                    video.filepath = str(new_path.resolve())
                    video.relative_path = get_relative_path(new_path)
                    video.filename = new_name
                except OSError as e:
                    raise HTTPException(status_code=400, detail=f"重命名源文件失败: {e}")
            else:
                # 文件不存在时只更新数据库记录
                video.filename = new_name

            # 同步重命名缩略图与预览图，使文件名与新视频名对应
            try:
                from utils.path import get_thumbnail_path, thumb_rel_name
                from config import settings as app_settings
                import json as _json

                def _rename_thumb(old_rel: str, new_rel: str):
                    if not old_rel:
                        return
                    op = app_settings.THUMBNAIL_DIR / old_rel
                    np = app_settings.THUMBNAIL_DIR / new_rel
                    if op.exists():
                        if np.exists() and np.resolve() != op.resolve():
                            try:
                                np.unlink()
                            except OSError:
                                pass
                        op.rename(np)

                new_thumb_rel = thumb_rel_name(video.id, "thumb", new_name)
                if video.thumbnail:
                    _rename_thumb(video.thumbnail, new_thumb_rel)
                video.thumbnail = new_thumb_rel

                new_previews = []
                try:
                    old_previews = _json.loads(video.preview_images) if video.preview_images else []
                except Exception:
                    old_previews = []
                for idx, old_rel in enumerate(old_previews):
                    kind = f"preview_{idx:02d}"
                    new_rel = thumb_rel_name(video.id, kind, new_name)
                    _rename_thumb(old_rel, new_rel)
                    new_previews.append(new_rel)
                # 兼容旧的 id 命名文件：尝试迁移
                if not old_previews:
                    for idx in range(20):
                        kind = f"preview_{idx:02d}"
                        legacy = app_settings.THUMBNAIL_DIR / f"{video.id}_{kind}.jpg"
                        if not legacy.exists():
                            break
                        new_rel = thumb_rel_name(video.id, kind, new_name)
                        _rename_thumb(f"{video.id}_{kind}.jpg", new_rel)
                        new_previews.append(new_rel)
                video.preview_images = _json.dumps(new_previews)
            except Exception as e:
                # 缩略图重命名失败不阻断视频重命名
                import logging
                logging.getLogger(__name__).warning(f"rename thumbs failed: {e}")
    if data.rating is not None:
        video.rating = data.rating
    if data.score is not None:
        video.score = data.score
    if data.favorite is not None:
        video.favorite = data.favorite
    if data.notes is not None:
        video.notes = data.notes
    if data.tag_ids is not None:
        tags = db.query(Tag).filter(Tag.id.in_(data.tag_ids)).all()
        video.tags = tags
    if data.category_id is not None:
        if data.category_id == 0:
            video.category_id = None
        else:
            from models.video import Category
            cat = db.query(Category).filter(Category.id == data.category_id).first()
            if not cat:
                raise HTTPException(status_code=400, detail="分类不存在")
            video.category_id = data.category_id

    video.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(video)
    return video_to_out(video)


@router.delete("/{video_id}")
async def delete_video(
    video_id: int,
    delete_file: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.thumbnail:
        for p in settings.THUMBNAIL_DIR.glob(f"{video_id}_*.jpg"):
            try:
                p.unlink()
            except OSError:
                pass

    filepath = video.filepath
    db.delete(video)
    db.commit()

    deleted_file = False
    if delete_file and settings.ALLOW_DELETE_FILES:
        p = Path(filepath)
        if p.exists() and is_safe_path(p):
            try:
                p.unlink()
                deleted_file = True
            except OSError:
                pass

    return {"ok": True, "deleted_file": deleted_file}


@router.post("/{video_id}/regenerate-thumbnail")
async def regen_thumb(
    video_id: int,
    background_tasks: BackgroundTasks,
    preview_count: int = Query(4, ge=0, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    path = Path(video.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file missing on disk")

    def _do():
        from database import SessionLocal
        session = SessionLocal()
        try:
            v = session.query(Video).filter(Video.id == video_id).first()
            if not v:
                return
            thumb, previews = regenerate_thumbnail(path, video_id, v.duration, num_previews=preview_count, filename=v.filename or path.name)
            if thumb:
                v.thumbnail = thumb
                v.preview_images = json.dumps(previews)
                session.commit()
        finally:
            session.close()

    background_tasks.add_task(_do)
    return {"message": "Thumbnail regeneration started"}


@router.get("/{video_id}/stream")
async def stream_video(
    video_id: int,
    token: Optional[str] = Query(None, description="JWT token for video tag playback"),
    db: Session = Depends(get_db),
):
    """
    视频流接口。
    支持两种认证方式：
    1. Authorization: Bearer <token>  （API 调用）
    2. ?token=<token>               （供 <video> 标签使用）
    """
    user = None

    # 优先使用 URL 参数中的 token（video 标签会用这个）
    if token:
        user = _authenticate_by_token(token, db)

    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized - missing or invalid token")

    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    path = Path(video.filepath)
    if not path.exists() or not is_safe_path(path):
        raise HTTPException(status_code=404, detail="File not found or access denied")

    # 更好的 MIME 类型处理
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        ext = path.suffix.lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".flv": "video/x-flv",
            ".m4v": "video/x-m4v",
            ".wmv": "video/x-ms-wmv",
        }
        mime = mime_map.get(ext, "video/mp4")

    # HTTP 头只能是 latin-1，中文文件名需 RFC 5987 编码
    from urllib.parse import quote
    ascii_name = path.name.encode("ascii", "ignore").decode("ascii") or f"video{path.suffix}"
    utf8_name = quote(video.filename or path.name)
    content_disposition = f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"

    return FileResponse(
        path,
        media_type=mime,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": content_disposition,
            "Cache-Control": "public, max-age=3600",
        },
    )




@router.get("/{video_id}/recommendations", response_model=List[VideoOut])
async def recommend_videos(
    video_id: int,
    limit: int = Query(12, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """根据分类和标签推荐相似视频"""
    video = (
        db.query(Video)
        .options(selectinload(Video.tags), joinedload(Video.category))
        .filter(Video.id == video_id)
        .first()
    )
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    tag_ids = [t.id for t in (video.tags or [])]
    cat_id = video.category_id

    candidates = (
        db.query(Video)
        .options(selectinload(Video.tags), joinedload(Video.category))
        .filter(Video.id != video_id)
        .all()
    )

    scored = []
    for c in candidates:
        score = 0
        if cat_id and c.category_id == cat_id:
            score += 10
        c_tag_ids = {t.id for t in (c.tags or [])}
        score += len(set(tag_ids) & c_tag_ids) * 3
        if video.favorite and c.favorite:
            score += 1
        if abs((video.rating or 0) - (c.rating or 0)) <= 1 and (video.rating or 0) > 0:
            score += 1
        if score > 0:
            scored.append((score, c))

    scored.sort(key=lambda x: (-x[0], -(x[1].rating or 0)))
    # 如果相似结果不够，用高评分/收藏补齐
    result_ids = {c.id for _, c in scored}
    if len(scored) < limit:
        extras = (
            db.query(Video)
            .options(selectinload(Video.tags), joinedload(Video.category))
            .filter(Video.id != video_id)
            .order_by(desc(Video.favorite), desc(Video.rating), desc(Video.scanned_at))
            .limit(limit * 2)
            .all()
        )
        for e in extras:
            if e.id not in result_ids:
                scored.append((0, e))
                result_ids.add(e.id)
            if len(scored) >= limit:
                break

    return [video_to_out(c) for _, c in scored[:limit]]


@router.get("/{video_id}/download")
async def download_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    path = Path(video.filepath)
    if not path.exists() or not is_safe_path(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=video.filename, media_type="application/octet-stream")
