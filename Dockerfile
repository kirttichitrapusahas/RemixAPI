# syntax=docker/dockerfile:1.3

########################################
# Single‑stage app image, reusing prebuilt deps
########################################
FROM gcr.io/ai-song-generator-453309/remix-deps:latest

# Install only runtime system deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ffmpeg \
      ca-certificates \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy your application code
COPY . .

# Cloud Run listens on $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["python", "app.py"]
