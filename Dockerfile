
# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV HOME=/app
ENV PRISMA_QUERY_ENGINE_BINARY=/app/prisma/query-engine
ENV PRISMA_QUERY_ENGINE_LIBRARY=/app/prisma/libquery_engine.so

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        postgresql-client \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Create reference data directory
RUN mkdir -p app/services/reference_data

# Download the reference data Excel file from Google Drive
RUN wget "https://drive.google.com/uc?export=download&id=11936bqbr4B85MpSOC2scDZcf7js-PZAe" -O "app/services/reference_data/2025 Labl IQ Rate Analyzer Template.xlsx"

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser

# Generate Prisma client as root (before switching user)
RUN prisma generate

# Ensure Prisma binary is in the correct location and has proper permissions
RUN find /app -name "query-engine*" -exec chmod +x {} \; || true
RUN find /app -name "libquery_engine*" -exec chmod +x {} \; || true

# Change ownership of all files to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
