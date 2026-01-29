FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY workers/requirements.txt .
COPY shared/ /app/shared/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY workers/ /app/workers/
COPY shared/ /app/shared/

# Run the worker (command will be overridden in docker-compose)
CMD ["python", "-m", "workers.text_extractor.worker"]
