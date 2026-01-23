FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/api/src:/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Debug: Verify services directory exists and show structure
RUN echo "=== Checking directory structure ===" && \
    ls -la /app/ && \
    echo "=== Checking api/src ===" && \
    ls -la /app/api/src/ && \
    echo "=== Checking services ===" && \
    ls -la /app/api/src/services/ && \
    echo "=== Services files ===" && \
    ls -la /app/api/src/services/*.py || echo "No .py files in services"

# Use only 1 worker to avoid session cache issues (each worker has separate memory)
# For production with multiple instances, consider using Redis or database for session storage
CMD exec env PYTHONPATH=/app/api/src:/app gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 300 --access-logfile - --error-logfile - --log-level info app:app