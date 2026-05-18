# Base Image
# official slim Python 3.11 base; matches CI python-version
FROM python:3.11-slim

# Non-Root User
# create a non-root user to avoid running as root in production
RUN useradd -m appuser

# Working Directory
# all subsequent COPY and RUN commands resolve relative to /app
WORKDIR /app

# Dependencies
# copy manifest first so pip install layer is cached independently of source changes
COPY requirements.txt .
# install pinned packages without pip cache to keep image size small
RUN pip install --no-cache-dir -r requirements.txt

# Application Code
# copy all source files with appuser ownership so non-root user can read them
COPY --chown=appuser:appuser . .

# Model Training
# switch to non-root user before training so artifact files are owned by appuser
# trains all four city models during the image build; .pkl files are baked into
# the image layer — no volume mount is required at runtime
USER appuser
RUN python -m models.train --city seoul --data data/raw/seoul/seoul_bike_sharing.csv && \
    python -m models.train --city london --data data/processed/london_bike_sharing.csv && \
    python -m models.train --city nyc --data data/processed/nyc_bike_sharing.csv && \
    python -m models.train --city dc --data data/processed/dc_bike_sharing.csv && \
    python -m models.train --city paris --data data/processed/paris_bike_sharing.csv && \
    python -m models.train --city chicago --data data/processed/chicago_bike_sharing.csv

# Network
# document the port uvicorn binds to inside the container
EXPOSE 8000

# Health Check
# polls the root endpoint every 30 s; marks container unhealthy after 3 failures
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')"

# Startup
# bind on all interfaces so the container port is reachable from the host
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
