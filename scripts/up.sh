#!/usr/bin/env bash
# Start Job Finder: set up what is missing, then run the server in the background.
#   PORT=8000 HOST=127.0.0.1 scripts/up.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
PIDFILE="data/server.pid"
LOG="data/server.log"
mkdir -p data

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Job Finder is already running (pid $(cat "$PIDFILE")). Stop it with: make down"
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating the Python environment…"
  python3 -m venv .venv
fi
# Reinstall only when requirements.txt changed since the last install.
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  echo "Installing Python packages…"
  .venv/bin/pip install -q -r requirements.txt
  touch .venv/.installed
fi

if [ ! -d web/node_modules ]; then
  echo "Installing web packages…"
  (cd web && npm install --silent)
fi
# Rebuild the web app when any source file is newer than the last build.
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html web/package.json -newer web/dist/index.html -print -quit)" ]; then
  echo "Building the web app…"
  (cd web && npm run build --silent)
fi

if command -v ss >/dev/null && ss -ltn "sport = :$PORT" | grep -q LISTEN; then
  echo "Port $PORT is already in use. Choose another: make up PORT=8001" >&2
  exit 1
fi

setsid nohup .venv/bin/python -m jobfinder serve --host "$HOST" --port "$PORT" >"$LOG" 2>&1 </dev/null &
echo $! >"$PIDFILE"

for _ in $(seq 1 40); do
  if curl -fs "http://$HOST:$PORT/api/refresh" >/dev/null 2>&1; then
    echo "Job Finder is running at http://$HOST:$PORT  (log: $LOG)"
    [ -f data/jobs.db ] || echo "No jobs yet. Fetch them with: make refresh"
    exit 0
  fi
  if ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then break; fi
  sleep 0.25
done

echo "The server did not start. Last lines of $LOG:" >&2
tail -n 15 "$LOG" >&2 || true
rm -f "$PIDFILE"
exit 1
