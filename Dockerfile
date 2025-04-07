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
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy rest of the app
COPY . .

# Expose the port Render will bind to
EXPOSE 10000

# Run your app
CMD ["python", "app.py"]
