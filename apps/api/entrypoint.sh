#!/bin/sh
set -eu
alembic -c alembic.ini upgrade head
python -c "from patchpilot.demo.seed import seed_database; seed_database()"
exec uvicorn patchpilot.main:app --host 0.0.0.0 --port 8000

