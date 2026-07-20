FROM python:3.12-slim

# 使用国内 Debian 源，避免 apt 超时
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN groupadd -r appuser && useradd -r -g appuser -u 1000 -d /app -s /sbin/nologin appuser

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY backend/ /app/backend/
COPY frontend/dist/ /app/frontend/dist/

RUN mkdir -p /app/storage/thumbnails /app/database /data/videos \
    && chown -R appuser:appuser /app /data || true

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIDEO_ROOT=/data/videos \
    THUMBNAIL_DIR=/app/storage/thumbnails \
    DATABASE_URL=sqlite:////app/database/video_manager.db \
    PYTHONPATH=/app/backend

# 默认以 root 运行，方便 NAS 挂载不同硬盘时的权限兼容
# 如需非 root，可在 docker-compose.yml 中添加：user: "1000:1000"
# USER appuser

# 声明默认挂载点，方便 NAS / Docker UI 创建容器时自动列出
VOLUME ["/data/videos", "/app/database", "/app/storage/thumbnails"]

# 镜像说明标签（部分 NAS 会读取）
LABEL   org.opencontainers.image.title="VideoShelf"   org.opencontainers.image.description="个人视频库管理。请映射: /data/videos=视频目录, /app/database=数据库, /app/storage/thumbnails=缩略图"   videoshelf.volume.videos="/data/videos"   videoshelf.volume.database="/app/database"   videoshelf.volume.thumbnails="/app/storage/thumbnails"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

WORKDIR /app/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
