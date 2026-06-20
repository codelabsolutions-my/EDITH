# EDITH server image. Python 3.12 to match the Azure Container Apps deploy target
# (local dev/test may use a newer interpreter; the code targets 3.12+).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: libpq for psycopg2 (yoyo migration runner).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

# App source + migrations.
COPY app ./app
COPY migrations ./migrations

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
