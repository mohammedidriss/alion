# ── Alion API — Railway deployment ────────────────────────────────────────────
# Multi-stage build: install deps with uv, then copy into a slim runtime image.
#
# CV / camera features (OpenCV VideoCapture, YOLOv8) are NOT available in this
# container — live video capture runs on the coach's laptop, not in the cloud.
# All data-management endpoints (fighters, sessions, HRV, etc.) work normally.
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── Dependency layer (cached unless pyproject.toml / uv.lock changes) ─────────
COPY pyproject.toml uv.lock README.md ./
# Only install core deps — no CV (opencv/mediapipe), no BLE (bleak), no YOLO.
# Those extras require hardware that isn't available in the cloud container.
RUN uv sync --frozen --no-dev --no-install-project \
    --no-extra cv --no-extra ble --no-extra yolo --no-extra ml 2>/dev/null \
    || uv sync --frozen --no-dev --no-install-project

# ── Application source ─────────────────────────────────────────────────────────
COPY packages/ packages/
COPY migrations/ migrations/
COPY alembic.ini ./

# Pre-create the data directory (Railway volume mounts here)
RUN mkdir -p /app/data/photos

# ── Runtime ────────────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app/packages
ENV ALION_DB_PATH=/app/data/alion.db

EXPOSE 8000

CMD ["sh", "-c", "uv run uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]
