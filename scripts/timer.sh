#!/usr/bin/env bash
# The daily timers:  scripts/timer.sh on | off | status
#   jobfinder-refresh  07:00  fetch every job source
#   jobfinder-repair   08:00  propose fixes for sources that broke (you approve them)
cd "$(dirname "$0")/.."
UNITS="$HOME/.config/systemd/user"
TIMERS="jobfinder-refresh.timer jobfinder-repair.timer"
case "${1:-status}" in
  on)
    mkdir -p "$UNITS"
    for unit in jobfinder-refresh.service jobfinder-refresh.timer jobfinder-repair.service jobfinder-repair.timer; do
      sed "s#@REPO@#$(pwd -P)#g" "deploy/systemd/$unit" > "$UNITS/$unit"
    done
    systemctl --user daemon-reload
    for timer in $TIMERS; do systemctl --user enable --now "$timer" >/dev/null 2>&1; done
    systemctl --user list-timers $TIMERS --no-legend | awk '{print "next run", $1, $2, $3, "·", $NF}'
    ;;
  off)
    for timer in $TIMERS; do systemctl --user disable --now "$timer" >/dev/null 2>&1; done
    echo "Daily fetch and repair off."
    ;;
  status)
    systemctl --user list-timers $TIMERS --all --no-legend 2>/dev/null | grep . || echo "Daily timers not installed (make up installs them)."
    ;;
esac
