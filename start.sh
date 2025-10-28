#!/usr/bin/env sh
set -e
cd /app
export ALEMBIC_DATABASE_URL="${ALEMBIC_DATABASE_URL:-$DATABASE_URL}"
alembic -c /app/alembic.ini upgrade head
exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
