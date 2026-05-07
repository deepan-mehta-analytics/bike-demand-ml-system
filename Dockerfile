# ── Base Image ────────────────────────────────────────────────────────────
FROM python:3.11-slim                                        # official slim Python base; matches CI version

# ── Non-Root User ─────────────────────────────────────────────────────────
RUN useradd -m appuser                                       # create non-root user to avoid running as root in prod

# ── Working Directory ─────────────────────────────────────────────────────
WORKDIR /app                                                 # all subsequent COPY / RUN commands resolve from here

# ── Dependencies ──────────────────────────────────────────────────────────
COPY requirements.txt .                                      # copy manifest first to maximise layer caching
RUN pip install --no-cache-dir -r requirements.txt           # install pinned packages; no cache saves image size

# ── Application Code ──────────────────────────────────────────────────────
COPY --chown=appuser:appuser . .                             # copy source with correct file ownership

# ── Drop Privileges ───────────────────────────────────────────────────────
USER appuser                                                 # switch to non-root before exposing any network ports

# ── Network ───────────────────────────────────────────────────────────────
EXPOSE 8000                                                  # document the port uvicorn listens on

# ── Health Check ──────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

# ── Startup ───────────────────────────────────────────────────────────────
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]  # bind on all interfaces inside container
