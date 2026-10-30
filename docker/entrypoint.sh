#!/bin/sh
# Backend container entrypoint.
#
# 1. Run Alembic migrations to create/upgrade the schema. Compose only starts
#    this container after Postgres reports healthy.
# 2. Start uvicorn.
#
# Any failure in migration aborts startup (set -e) so we never serve against
# an out-of-date schema.
#
# PORT: hosting platforms often inject a $PORT the app must bind. We use it
# when present and fall back to 8000 so local `docker compose` is unchanged.

set -e

echo "[entrypoint] running database migrations..."
alembic upgrade head

echo "[entrypoint] starting uvicorn on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"