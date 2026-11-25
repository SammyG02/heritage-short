#!/bin/sh
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "First run: installing. This takes a few minutes."; python3 -m venv .venv; }
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  echo "A file called .env was created. Add your keys to it, save it, then run ./start.sh again."
  exit 0
fi
.venv/bin/python -m pipeline web
