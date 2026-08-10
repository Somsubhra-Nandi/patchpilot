FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs npm ca-certificates && npm install -g @openai/codex && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY patchpilot ./patchpilot
COPY tests ./tests
COPY entrypoint.sh ./entrypoint.sh
RUN pip install --upgrade pip && pip install '.[dev]' && chmod +x entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"
CMD ["./entrypoint.sh"]
