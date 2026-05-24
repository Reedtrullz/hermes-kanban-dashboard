#!/bin/bash
# Start Hermes Proposals Dashboard
set -e

cd /Users/reidar/Projectos/hermes-proposals-dashboard

# Ensure deps are installed
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

export HERMES_REQUIRE_AUTH="${HERMES_REQUIRE_AUTH:-0}"
exec .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8089
