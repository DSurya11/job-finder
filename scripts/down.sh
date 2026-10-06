#!/usr/bin/env bash
# Stop Job Finder. Always exits 0: stopping something that is not running is fine.
cd "$(dirname "$0")/.."
PIDFILE="data/server.pid"

stopped=0
if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    stopped=1
  fi
  rm -f "$PIDFILE"
fi
# Catch a server started by hand from this folder, without touching a fetch in progress.
for pid in $(pgrep -f "jobfinder serv[e]" 2>/dev/null); do
  if [ "$(readlink -f "/proc/$pid/cwd" 2>/dev/null)" = "$(pwd -P)" ]; then
    kill "$pid" 2>/dev/null && stopped=1
    for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
  fi
done

if [ "$stopped" = 1 ]; then echo "Job Finder stopped."; else echo "Job Finder was not running."; fi
exit 0
