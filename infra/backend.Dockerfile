FROM python:3.12.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./backend/
RUN uv sync --project backend --locked --no-dev
COPY backend ./backend
RUN useradd --uid 10001 --create-home lattice \
    && mkdir -p /data/storage /data/models /data/beat \
    && chown -R lattice:lattice /data
ENV PATH="/app/backend/.venv/bin:$PATH" PYTHONPATH=/app/backend
USER lattice
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
