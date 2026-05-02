#!/bin/bash

# Usage: ./rollback.sh <commit-sha>
SHA=$1

if [ -z "$SHA" ]; then
    echo "❌ Error: Please provide a commit SHA for rollback."
    echo "Usage: ./rollback.sh <commit-sha>"
    exit 1
fi

IMAGE_NAME="ghcr.io/$(git config --get remote.origin.url | sed 's/.*\/\([^ ]*\)\.git/\1/' | tr '[:upper:]' '[:lower:]')"
CONTAINER_NAME="billsync-frontend"
PORT_MAPPING="8080:80"

echo "⏪ Rolling back to version sha-$SHA..."

# 1. Pull the specific SHA image
echo "📥 Pulling image version sha-$SHA..."
docker pull $IMAGE_NAME:sha-$SHA

if [ $? -ne 0 ]; then
    echo "❌ Error: Could not find image with tag sha-$SHA"
    exit 1
fi

# 2. Stop and remove existing container
if [ "$(docker ps -aq -f name=$CONTAINER_NAME)" ]; then
    echo "🛑 Stopping existing container..."
    docker stop $CONTAINER_NAME
    docker rm $CONTAINER_NAME
fi

# 3. Run the specific version
echo "🏃 Starting container with version sha-$SHA..."
docker run -d \
    --name $CONTAINER_NAME \
    --restart unless-stopped \
    -p $PORT_MAPPING \
    $IMAGE_NAME:sha-$SHA

echo "✅ Rollback to $SHA complete!"
