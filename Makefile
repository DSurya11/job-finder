# Job Finder
#   make up        start the app and the daily 07:00 fetch (sets up anything missing first)
#   make down      stop both; stays off until make up
#   make timer-status / timer-logs   the daily fetch (07:00) and repair (08:00): next run, last output
#   make fixes / approve ID=3         source fixes the repair agent proposed; nothing applies until approved
#   make refresh   fetch jobs from every source
#   make pay       look up pay on AmbitionBox for jobs that do not state it
#   make status    is it running?
#   make logs      follow the server log
#   make test      run the tests
PORT ?= 8000
HOST ?= 127.0.0.1
PY   := .venv/bin/python

.PHONY: up down restart refresh pay status logs test timer-status timer-logs fixes approve

up:
	@PORT=$(PORT) HOST=$(HOST) scripts/up.sh
	@scripts/timer.sh on

down:
	@scripts/down.sh
	@scripts/timer.sh off

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

timer-status:
	@scripts/timer.sh status

timer-logs:
	@journalctl --user -u jobfinder-refresh -u jobfinder-repair -n 60 --no-pager

fixes:            ## proposed fixes for broken job sources (approve: make approve ID=3)
	@$(PY) -m jobfinder fixes

approve:
	@$(PY) -m jobfinder fixes --approve $(ID)
