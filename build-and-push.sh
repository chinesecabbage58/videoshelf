#!/bin/bash
# 构建并推送到 Docker Hub: baibaibai122/videoshelf
# 使用前请先登录: docker login

set -e

IMAGE="baibaibai122/videoshelf"
TAG="${1:-latest}"

echo "==> 构建镜像 ${IMAGE}:${TAG} ..."
docker build -t ${IMAGE}:${TAG} -t ${IMAGE}:latest .

echo "==> 推送到 Docker Hub ..."
docker push ${IMAGE}:${TAG}
if [ "$TAG" != "latest" ]; then
  docker push ${IMAGE}:latest
fi

echo "==> 完成！镜像地址: https://hub.docker.com/r/baibaibai122/videoshelf"
echo "拉取命令: docker pull baibaibai122/videoshelf:latest"
