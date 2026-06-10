# =============================================================
# Dockerfile — XAU/USD Price Action Trading Bot
#
# Multi-stage build:
#   builder  → installs Python deps into /venv
#   runtime  → minimal production image
#
# Note: Wine/MT5 run on the host, not inside Docker.
#       The DWX broker communicates via a bind-mounted directory.
#
# Build:
#   docker build -t xaubot:latest .
#
# Run:
#   docker run --env-file .env \
#     -v $(pwd)/data:/app/data \
#     -v $(pwd)/logs:/app/logs \
#     -v $(pwd)/reports:/app/reports \
#     -p 8443:8443 -p 8502:8502 \
#     xaubot:latest
# =============================================================

# ─────────────────────────────────────────────────────────────────
# Stage 1: Builder — install Python dependencies
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Build-time system deps
RUN apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        gcc \
        g++ \
        libssl-dev \
        libffi-dev \
        build-essential \
        curl \
        && \
    rm -rf /var/lib/apt/lists/*

# Create a virtual environment in /venv
RUN python -m venv /venv
ENV PATH="/venv/bin:${PATH}"

# Upgrade pip
RUN pip install --upgrade pip --quiet

# Copy requirements and install
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt --quiet

# Copy backend requirements if they exist
COPY backend/requirements.txt /tmp/backend_requirements.txt 2>/dev/null || true
RUN if [ -f /tmp/backend_requirements.txt ]; then \
        pip install --no-cache-dir -r /tmp/backend_requirements.txt --quiet; \
    fi

# Install FastAPI stack for the backend
RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    httpx \
    "python-jose[cryptography]" \
    "passlib[bcrypt]" \
    sqlalchemy \
    aiosqlite \
    structlog \
    python-multipart \
    --quiet

# ─────────────────────────────────────────────────────────────────
# Stage 2: Runtime image
# ─────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="XAUBot" \
      description="XAU/USD Price Action Trading Bot" \
      version="1.0.0"

# Runtime system deps (minimal)
RUN apt-get update -qq && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        curl \
        ca-certificates \
        tzdata \
        && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Set timezone (overridable via TZ env var)
ENV TZ=Asia/Dubai
RUN ln -snf /usr/share/zoneinfo/${TZ} /etc/localtime && \
    echo ${TZ} > /etc/timezone

# Copy venv from builder
COPY --from=builder /venv /venv

# Ensure venv binaries are on PATH
ENV PATH="/venv/bin:${PATH}"
ENV VIRTUAL_ENV="/venv"

# Create application directory
WORKDIR /app

# Create a non-root user to run the bot
RUN groupadd -r botuser && useradd -r -g botuser -d /app botuser

# Copy application code
COPY --chown=botuser:botuser main.py               ./main.py
COPY --chown=botuser:botuser config.yaml           ./config.yaml
COPY --chown=botuser:botuser xau_bot/              ./xau_bot/
COPY --chown=botuser:botuser backend/              ./backend/
COPY --chown=botuser:botuser ui/                   ./ui/
COPY --chown=botuser:botuser scripts/              ./scripts/

# Copy .env.example (not .env — that is bind-mounted or injected at runtime)
COPY --chown=botuser:botuser .env.example          ./.env.example

# Create persistent data directories and set permissions
RUN mkdir -p \
        /app/data \
        /app/logs \
        /app/reports \
        /app/backups \
    && chown -R botuser:botuser \
        /app/data \
        /app/logs \
        /app/reports \
        /app/backups

# Declare volumes for persistent data
VOLUME ["/app/data", "/app/logs", "/app/reports", "/app/backups"]

# Expose API (HTTPS) and Streamlit UI ports
EXPOSE 8443 8502

# Switch to non-root user
USER botuser

# Environment variable defaults (overridden by .env or docker-compose)
ENV BOT_MODE=live \
    BOT_SYMBOL=XAUUSD! \
    BROKER_TYPE=dwx \
    DATA_DIR=/app/data \
    LOGS_DIR=/app/logs \
    REPORTS_DIR=/app/reports \
    BACKUP_DIR=/app/backups \
    API_PORT=8443 \
    UI_PORT=8502 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check — pings the API /health endpoint
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsk "https://localhost:${API_PORT:-8443}/health" > /dev/null 2>&1 || exit 1

# Default entrypoint: run the trading bot
CMD ["python", "main.py"]
