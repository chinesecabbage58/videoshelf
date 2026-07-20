# VideoShelf

个人/局域网视频库管理工具。支持扫描本地视频、封面与预览图、标签、搜索、在线播放，适合部署在 NAS（如绿联）或 Docker 环境。

## 项目地址
- GitHub：https://github.com/chinesecabbage58/videoshelf
- Docker Hub：https://hub.docker.com/r/baibaibai122/videoshelf

## 功能

- 扫描指定目录中的视频并入库
- 自动生成封面图与多帧预览图（基于 FFmpeg）
- 标签筛选（支持多选）、搜索、排序
- 在线播放（支持移动端，避免自动全屏）
- 视频管理：重命名（同步源文件与缩略图）、简介、标签、删除源文件
- 文件监控：目录有新增视频时自动入库
- 设置多端同步（分页、预览图数量、刷新策略等）
- 适配 PC / 移动端

## 技术栈

| 部分 | 技术 |
|------|------|
| 后端 | Python 3.12、FastAPI、SQLAlchemy、SQLite |
| 前端 | Vue 3（单文件构建）、Tailwind CSS |
| 媒体 | FFmpeg / ffprobe（系统命令调用） |
| 部署 | Docker / Docker Compose |

## 依赖说明：FFmpeg

本项目通过调用系统中的 `ffmpeg` / `ffprobe` 命令生成缩略图与读取视频信息，**不内嵌 FFmpeg 源码**。

- 镜像构建时会安装发行版提供的 `ffmpeg` 软件包
- FFmpeg 本身遵循 [LGPL/GPL 等许可证](https://ffmpeg.org/legal.html)，与本项目的 MIT 许可相互独立
- 若你二次分发包含 FFmpeg 的镜像或安装包，请同时遵守 FFmpeg 及所启用编码器的许可要求

使用 MIT 许可本仓库源码是合适的。

## 快速开始（Docker）

### 镜像

```bash
docker pull baibaibai122/videoshelf:latest
# 或本地构建
docker build -t baibaibai122/videoshelf:latest .
```

### 运行示例

```bash
docker run -d --name videoshelf \
  -p 8080:8080 \
  -v /path/to/videos:/data/videos \
  -v /path/to/db:/app/database \
  -v /path/to/thumbs:/app/storage/thumbnails \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=请修改密码 \
  -e SECRET_KEY=请改成随机长字符串 \
  baibaibai122/videoshelf:latest
```

浏览器访问：`http://服务器IP:8080`

### 目录映射说明

| 容器路径 | 含义 |
|----------|------|
| `/data/videos` | 视频文件目录（可挂机械硬盘） |
| `/app/database` | SQLite 数据库与应用设置（建议 SSD） |
| `/app/storage/thumbnails` | 封面与预览图（建议 SSD） |

### docker-compose

见仓库内 `docker-compose.yml`，按注释修改主机路径后：

```bash
docker compose up -d
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `VIDEO_ROOT` | `/data/videos` | 视频根目录 |
| `DATABASE_URL` | SQLite 路径 | 数据库连接 |
| `THUMBNAIL_DIR` | `/app/storage/thumbnails` | 缩略图目录 |
| `ADMIN_USERNAME` | `admin` | 初始管理员用户名 |
| `ADMIN_PASSWORD` | `admin123` | 初始密码（请修改） |
| `SECRET_KEY` | 内置默认值 | JWT 密钥（请修改） |
| `ALLOW_DELETE_FILES` | `true` | 删除时是否允许删源文件 |
| `ENABLE_WATCHER` | `true` | 是否启用文件监控 |

## 本地开发（可选）

```bash
# 后端
cd backend
pip install -r requirements.txt
# 需本机已安装 ffmpeg
uvicorn main:app --reload --host 0.0.0.0 --port 8080

# 前端为单文件 dist/index.html，由后端静态托管
```

## 许可证

本项目源码采用 [MIT License](LICENSE)。

第三方：

- **FFmpeg**：独立许可证（LGPL/GPL 等），详见 https://ffmpeg.org/legal.html  
- 其他 Python 依赖见 `backend/requirements.txt` 中各包自身许可

## 免责声明

本工具仅供合法持有的视频文件的个人管理与局域网播放使用。请确保你拥有相应文件的使用权，并遵守当地法律法规。
