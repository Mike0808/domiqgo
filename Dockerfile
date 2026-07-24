FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependency layer first so code changes don't re-resolve packages.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Build the static manifest at image build time. DEBUG=1 with a dummy key is
# fine here: collectstatic touches no database and no real settings.
RUN SECRET_KEY=build-only DEBUG=1 python manage.py collectstatic --noinput

RUN useradd --create-home app && mkdir -p /data && chown -R app:app /app /data
USER app

EXPOSE 8000
ENTRYPOINT ["/app/deploy/docker/entrypoint.sh"]
