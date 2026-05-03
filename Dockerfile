# Use official Python image pinned to stable Debian Bookworm
FROM python:3.12-slim-bookworm

# Set work directory
WORKDIR /app

# Install system dependencies with retries for network resilience
RUN apt-get update || (sleep 5 && apt-get update) && \
    apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    libgl1-mesa-glx && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Expose FastAPI port
EXPOSE 9001

# Run FastAPI app
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "9001"]
