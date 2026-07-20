from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models.video import Tag, Video
from models.user import User
from utils.security import get_current_active_user

router = APIRouter(prefix="/api/tags", tags=["tags"])


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = "#00c476"


class TagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None


class TagOut(BaseModel):
    id: int
    name: str
    color: Optional[str]
    video_count: int = 0

    class Config:
        from_attributes = True


@router.get("", response_model=List[TagOut])
async def list_tags(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tags = db.query(Tag).order_by(Tag.name).all()
    result = []
    for t in tags:
        count = db.query(Video).filter(Video.tags.any(Tag.id == t.id)).count()
        result.append(TagOut(id=t.id, name=t.name, color=t.color, video_count=count))
    return result


@router.post("", response_model=TagOut)
async def create_tag(
    data: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    existing = db.query(Tag).filter(Tag.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag already exists")
    tag = Tag(name=data.name.strip(), color=data.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return TagOut(id=tag.id, name=tag.name, color=tag.color, video_count=0)


@router.patch("/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: int,
    data: TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if data.name is not None:
        conflict = db.query(Tag).filter(Tag.name == data.name, Tag.id != tag_id).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Tag name already exists")
        tag.name = data.name.strip()
    if data.color is not None:
        tag.color = data.color
    db.commit()
    db.refresh(tag)
    count = db.query(Video).filter(Video.tags.any(Tag.id == tag.id)).count()
    return TagOut(id=tag.id, name=tag.name, color=tag.color, video_count=count)


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return {"ok": True}
