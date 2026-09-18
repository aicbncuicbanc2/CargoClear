FROM python:3.12-slim

# Fail fast and log straight through to Cloud Run's log capture.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# The dataset must be in the image: the pipeline reads data/inbox and
# data/attachments at runtime, and data/loader.py is imported by name.
# data/ is gitignored, so this COPY is the only thing putting it in the
# container — without it every page 500s on a missing loader module.
COPY data ./data

# Configuration. GEMINI_API_KEY is deliberately NOT set here: it is a
# secret, passed at run time (`docker run -e GEMINI_API_KEY=...`, or a
# Cloud Run secret/env var). The app starts without it and simply skips the
# Gemini fallback, so a missing key degrades rather than crashes.
ENV PORT=8080 \
    DATASET_SOURCE=/app/data

# Drop privileges — Cloud Run does not require root and the app never writes
# to disk.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

# Cloud Run injects $PORT; the default above covers local `docker run`.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
