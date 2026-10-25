#!/usr/bin/env bash
# The daily fetch timer:  scripts/timer.sh on | off | status
cd "$(dirname "$0")/.."
UNITS="$HOME/.config/systemd/user"
case "${1:-status}" in
  on)
    mkdir -p "$UNITS"
    for unit in jobfinder-refresh.service jobfinder-refresh.timer; do
      sed "s#@REPO@#$(pwd -P)#g" "deploy/systemd/$unit" > "$UNITS/$unit"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now jobfinder-refresh.timer >/dev/null 2>&1
    echo "Daily fetch on: $(systemctl --user list-timers jobfinder-refresh.timer --no-legend | awk '{print "next run", $1, $2, $3}')"
    ;;
  off)
    systemctl --user disable --now jobfinder-refresh.timer >/dev/null 2>&1
    echo "Daily fetch off."
    ;;
  status)
    systemctl --user list-timers jobfinder-refresh.timer --all --no-legend 2>/dev/null | grep . || echo "Daily fetch not installed (make up installs it)."
    ;;
esac
