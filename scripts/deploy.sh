#!/bin/bash

# Configuration
# Detection of the repository owner/name from the local git config
GIT_URL=$(git config --get remote.origin.url)
REPO_PATH=$(echo "$GIT_URL" | sed -E 's/.*github.com[:\/](.*)\.git/\1/' | tr '[:upper:]' '[:lower:]')
GITHUB_USER=$(echo "$REPO_PATH" | cut -d'/' -f1)

FRONTEND_IMAGE="ghcr.io/smashysubash/billsync-app"
BACKEND_IMAGE="ghcr.io/smashysubash/billsync-backend"

FRONTEND_CONTAINER="billsync-frontend"
BACKEND_CONTAINER="billsync-backend"

echo "🚀 Starting pull-based deployment..."

# Function to deploy an image
deploy_container() {
    local image=$1
    local name=$2
    local port=$3

    echo "📥 Pulling $image:latest..."
    docker pull $image:latest

    LATEST_ID=$(docker inspect --format='{{.Id}}' $image:latest)
    RUNNING_ID=$(docker inspect --format='{{.Image}}' $name 2>/dev/null || echo "none")

    if [ "$LATEST_ID" == "$RUNNING_ID" ]; then
        echo "✅ $name is already up to date."
    else
        echo "🔄 Updating $name..."
        docker stop $name 2>/dev/null
        docker rm $name 2>/dev/null
        docker run -d --name $name --restart unless-stopped -p $port $image:latest
        echo "✨ $name updated successfully."
    fi
}

deploy_container $FRONTEND_IMAGE $FRONTEND_CONTAINER "8080:80"
deploy_container $BACKEND_IMAGE $BACKEND_CONTAINER "9001:9001"

# Cleanup
echo "🧹 Cleaning up..."

docker image prune -f
