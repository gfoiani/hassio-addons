#!/bin/bash
# =====================================================================
# Local Docker build & run for development/testing.
# Mirrors the Home Assistant container environment.
# =====================================================================

set -e

export IMG_VERSION=$(git describe HEAD --always 2>/dev/null || echo "dev")
export CONTAINER_NAME=trading-bot
export BUILD_FROM=homeassistant/amd64-base:3.13

echo "Building image ${CONTAINER_NAME}:${IMG_VERSION} …"
docker build \
  --platform=linux/amd64 \
  --build-arg BUILD_FROM=${BUILD_FROM} \
  -t ${CONTAINER_NAME}:${IMG_VERSION} .

docker tag ${CONTAINER_NAME}:${IMG_VERSION} ${CONTAINER_NAME}:latest

# Remove existing container if present
CONTAINER_EXISTS="$(docker ps -a --format '{{.Names}}' | grep -c "^${CONTAINER_NAME}$" || true)"
if [[ $CONTAINER_EXISTS -ge "1" ]]; then
  echo "Removing existing container ${CONTAINER_NAME} …"
  docker rm -f ${CONTAINER_NAME}
fi

echo "Starting container …"
docker run -dit \
  --name ${CONTAINER_NAME} \
  -v ${CONTAINER_NAME}-storage:/usr/src/app/storage \
  --env-file .env \
  --restart=no \
  --log-opt max-size=50m \
  ${CONTAINER_NAME}:latest

echo ""
echo "Container started. Follow logs with:"
echo "  docker logs -f ${CONTAINER_NAME}"
echo ""
docker ps
