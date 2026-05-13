# syntax=docker/dockerfile:1.7
# MediFleet backend — FastAPI on Python 3.12-slim.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# psycopg2-binary ships its own libpq, but libpq5 is still needed at runtime
# when the host kernel/glibc combination doesn't pick up the bundled one.
# build-essential is kept out by design — we rely on prebuilt wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer caches across code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy application source.
COPY . .

# Drop privileges. /app is owned by the app user so writes from migrations or
# logs land somewhere safe.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 app \
 && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/ >/dev/null || exit 1

# Production start — same boot sequence as Render (seed → migrate → uvicorn).
CMD ["bash", "render-start.sh"]
