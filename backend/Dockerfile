# Shared image for both the FastAPI backend and the Celery worker
# (compose overrides `command:` per-service; the image itself is identical).
FROM python:3.11-slim

# --- System deps -----------------------------------------------------------
# - curl/gnupg/apt-transport-https: needed to add Microsoft's apt repo
# - unixodbc + msodbcsql17: pyodbc's runtime driver for the MSSQL DATABASE_URL
#   (matches the "ODBC Driver 17 for SQL Server" name baked into .env's connection string)
#   (app/database/__init__.py connects via an `odbc_connect=` connection string)
# - build-essential/unixodbc-dev: headers pyodbc needs to build its wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        apt-transport-https \
        build-essential \
        unixodbc-dev \
    && curl -sSL -o /usr/share/keyrings/microsoft-prod.gpg https://packages.microsoft.com/keys/microsoft.asc \
    && curl -sSL https://packages.microsoft.com/config/debian/12/prod.list -o /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- uv ----------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps first so this layer is cached across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
