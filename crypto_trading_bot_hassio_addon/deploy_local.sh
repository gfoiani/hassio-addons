#!/bin/bash
set -e

IMAGE_NAME="crypto-trader"
CONTAINER_NAME="crypto-trader"

echo "Building $IMAGE_NAME..."
docker build \
  --platform=linux/amd64 \
  --build-arg BUILD_FROM=homeassistant/amd64-base:3.13 \
  -t "$IMAGE_NAME:latest" .

echo "Removing existing container (if any)..."
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

echo "Starting $CONTAINER_NAME..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --env-file .env \
  -v crypto-trader-data:/data \
  "$IMAGE_NAME:latest"

echo "Container started. Logs:"
docker logs -f "$CONTAINER_NAME"
