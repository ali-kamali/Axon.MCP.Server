# Build stage
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    libcurl4 \
    libcurl4-gnutls-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements files
COPY requirements.txt requirements-dev.txt /tmp/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Install runtime dependencies with NTLM support
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    libcurl4 \
    libcurl4-gnutls-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create app directory
WORKDIR /app

# Create non-root user
RUN useradd -m -u 1000 axon && \
    chown -R axon:axon /app

# Copy application code
COPY --chown=axon:axon . /app/

# Create cache directory
RUN mkdir -p /app/cache && chown -R axon:axon /app/cache

# Switch to non-root user
USER axon

# Expose ports
EXPOSE 8001 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

# Default command (can be overridden in docker-compose)
CMD ["/opt/venv/bin/uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]

