#!/bin/bash
set -e

IMAGE_NAME="crypto-trader"
CONTAINER_NAME="crypto-trader"

echo "Building $IMAGE_NAME..."
docker build \
  --build-arg BUILD_FROM=python:3.11-alpine \
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
