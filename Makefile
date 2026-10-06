# Job Finder
#   make up        start the app (sets up anything missing first)
#   make down      stop it
#   make refresh   fetch jobs from every source
#   make pay       look up pay on AmbitionBox for jobs that do not state it
#   make status    is it running?
#   make logs      follow the server log
#   make test      run the tests
PORT ?= 8000
HOST ?= 127.0.0.1
PY   := .venv/bin/python

.PHONY: up down restart refresh pay status logs test

up:
	@PORT=$(PORT) HOST=$(HOST) scripts/up.sh

down:
	@scripts/down.sh

restart: down up

refresh:
	@$(PY) -m jobfinder run

pay:
	@$(PY) -m jobfinder pay --limit 500

status:
	@if [ -f data/server.pid ] && kill -0 $$(cat data/server.pid) 2>/dev/null; then \
		echo "Running (pid $$(cat data/server.pid))."; \
	else echo "Not running."; fi

logs:
	@tail -f data/server.log

test:
	@$(PY) -m pytest -q tests
