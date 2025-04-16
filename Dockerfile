# Use official Python slim image
FROM python:3.9-slim

# Avoid Python writing pyc files and buffering logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create app directory
WORKDIR /app

# Install system dependencies (including ffmpeg)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=300 --retries=10 -r requirements.txt

# Copy rest of the app
COPY . .

# Expose the port (8080 is used by your app)
EXPOSE 8080

# Set the port env var explicitly
ENV PORT=8080

# Run your app
CMD ["python", "app.py"]
