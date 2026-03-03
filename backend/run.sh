#!/usr/bin/env bash
# Run VISHWAAS Master backend (from backend directory)
cd "$(dirname "$0")"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
