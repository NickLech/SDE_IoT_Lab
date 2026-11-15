#!/bin/sh
# Switch single devices on/off from the host terminal.
#
#   ./ctl.sh status                      all devices of all zones
#   ./ctl.sh zone2 status                devices of zone2
#   ./ctl.sh zone2 stop soil-2           switch OFF one sensor   (shows "offline" on the dashboard)
#   ./ctl.sh zone2 start soil-2          switch it back ON
#   ./ctl.sh zone1 stop temperature      also: soil-1 soil-2 soil-3 temperature humidity sprinkler
#   ./ctl.sh zone3 stop all              the whole zone's devices (the container keeps running)
#   ./ctl.sh zone3 restart sprinkler
#
# Rain is global:  ./ctl.sh rain stop | start   (stops/starts the container)
set -e
cd "$(dirname "$0")"

if [ "$1" = "status" ]; then
  for z in zone1 zone2 zone3; do
    echo "== $z"; docker compose exec -T "$z" zonectl status
  done
  exit 0
fi

target="$1"; shift || { sed -n '2,13p' "$0"; exit 1; }
if [ "$target" = "rain" ]; then
  case "${1:-status}" in
    stop|start|restart) exec docker compose "$1" rain ;;
    *) exec docker compose ps rain ;;
  esac
fi
[ $# -ge 1 ] || set -- status
exec docker compose exec -T "$target" zonectl "$@"
