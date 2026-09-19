# syntax=docker/dockerfile:1

# ---- Build: resolve dependencies from uv.lock into a virtual environment ----
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.6 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# ---- Runtime: no build tools, non-root user, data on a volume ----
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 ichnos \
    && mkdir /data \
    && chown ichnos:ichnos /data
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ICHNOS_DATA_DIR=/data
USER ichnos
WORKDIR /app
EXPOSE 8000
CMD ["uvicorn", "ichnos.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
