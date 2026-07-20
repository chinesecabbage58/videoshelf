from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, BigInteger, Float, Boolean, DateTime, ForeignKey, Text, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


video_tags = Table(
    "video_tags",
    Base.metadata,
    Column("video_id", Integer, ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Category(Base):
    """分类（类似文件夹）"""
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), default="#3b82f6")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    videos: Mapped[List["Video"]] = relationship("Video", back_populates="category")


class Tag(Base):
    """标签（关键词）"""
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(20), default="#6366f1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    videos: Mapped[List["Video"]] = relationship(
        "Video", secondary=video_tags, back_populates="tags"
    )


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    filepath: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    filesize: Mapped[int] = mapped_column(BigInteger, default=0)
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    codec: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    audio_codec: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bitrate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    thumbnail: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    preview_images: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rating: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 分类（一对多）
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    file_created: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    file_modified: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    scanned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="videos")
    tags: Mapped[List[Tag]] = relationship(
        "Tag", secondary=video_tags, back_populates="videos", lazy="selectin"
    )

    @property
    def resolution(self) -> Optional[str]:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "Unknown"
        seconds = int(self.duration)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
