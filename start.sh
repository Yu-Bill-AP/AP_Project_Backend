#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt
venv/bin/alembic upgrade head
venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
