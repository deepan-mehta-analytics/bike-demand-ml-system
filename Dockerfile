# ── Base Image ────────────────────────────────────────────────────────────
# official slim Python base; matches CI version
FROM python:3.11-slim

# ── Non-Root User ─────────────────────────────────────────────────────────
# create non-root user to avoid running as root in prod
RUN useradd -m appuser

# ── Working Directory ─────────────────────────────────────────────────────
# all subsequent COPY / RUN commands resolve from here
WORKDIR /app

# ── Dependencies ──────────────────────────────────────────────────────────
# copy manifest first to maximise layer caching
COPY requirements.txt .
# install pinned packages; no cache saves image size
RUN pip install --no-cache-dir -r requirements.txt

# ── Application Code ──────────────────────────────────────────────────────
# copy source with correct file ownership
COPY --chown=appuser:appuser . .

# ── Drop Privileges ───────────────────────────────────────────────────────
# switch to non-root before exposing any network ports
USER appuser

# ── Network ───────────────────────────────────────────────────────────────
# document the port uvicorn listens on
EXPOSE 8000

# ── Health Check ──────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

# ── Startup ───────────────────────────────────────────────────────────────
# bind on all interfaces inside container
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
