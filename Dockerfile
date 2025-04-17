# syntax=docker/dockerfile:1.3

########################################
# Stage 1: Install dependencies
########################################
FROM python:3.9-slim AS builder

# Install system deps (ffmpeg, wget, git, CAs) for building and runtime
RUN apt-get update && apt-get install -y \
      ffmpeg \
      git \
      wget \
      ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements so this layer is cached unless requirements.txt changes
COPY requirements.txt .

# Use BuildKit cache for pip downloads
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --no-cache-dir \
      --default-timeout=300 \
      --retries=10 \
      -r requirements.txt


########################################
# Stage 2: Copy code and run
########################################
FROM python:3.9-slim

# Install only runtime deps
RUN apt-get update && apt-get install -y \
      ffmpeg \
      ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy in the Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages

# Copy your application code
COPY . .

# Expose and configure
ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
