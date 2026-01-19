# Multi-stage build for a smaller final image
FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies needed for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only the requirements file for caching
COPY requirements_prod.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements_prod.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run the application with Gunicorn
CMD ["gunicorn", "-c", "gunicorn_conf.py", "main:app"]
