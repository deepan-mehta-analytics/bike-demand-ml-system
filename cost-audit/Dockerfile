FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached on source-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source after deps to maximise layer cache hit rate.
COPY . .

# Create a non-root user and transfer ownership of the app directory.
RUN useradd -m appuser && chown -R appuser /app

# Switch to non-root for the runtime process.
USER appuser

# Cloud Run injects the PORT environment variable; functions-framework honours it.
ENV PORT=8080

# Start the functions-framework HTTP server targeting the audit() handler.
CMD ["sh", "-c", "exec functions-framework --target=audit --port=${PORT:-8080}"]
