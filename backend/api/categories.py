from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models.video import Category, Video
from models.user import User
from utils.security import get_current_active_user

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = "#3b82f6"


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None


class CategoryOut(BaseModel):
    id: int
    name: str
    color: Optional[str]
    video_count: int = 0

    class Config:
        from_attributes = True


@router.get("", response_model=List[CategoryOut])
async def list_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cats = db.query(Category).order_by(Category.name).all()
    result = []
    for c in cats:
        count = db.query(Video).filter(Video.category_id == c.id).count()
        result.append(CategoryOut(id=c.id, name=c.name, color=c.color, video_count=count))
    return result


@router.post("", response_model=CategoryOut)
async def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    existing = db.query(Category).filter(Category.name == data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="分类已存在")
    cat = Category(name=data.name.strip(), color=data.color)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryOut(id=cat.id, name=cat.name, color=cat.color, video_count=0)


@router.patch("/{cat_id}", response_model=CategoryOut)
async def update_category(
    cat_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    if data.name is not None:
        conflict = db.query(Category).filter(Category.name == data.name, Category.id != cat_id).first()
        if conflict:
            raise HTTPException(status_code=400, detail="分类名称已存在")
        cat.name = data.name.strip()
    if data.color is not None:
        cat.color = data.color
    db.commit()
    db.refresh(cat)
    count = db.query(Video).filter(Video.category_id == cat.id).count()
    return CategoryOut(id=cat.id, name=cat.name, color=cat.color, video_count=count)


@router.delete("/{cat_id}")
async def delete_category(
    cat_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    # 清除关联视频的分类
    db.query(Video).filter(Video.category_id == cat_id).update({"category_id": None})
    db.delete(cat)
    db.commit()
    return {"ok": True}
