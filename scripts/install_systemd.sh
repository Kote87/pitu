#!/usr/bin/env bash
set -euo pipefail
UNIT_SRC="systemd/garmin-pull.service"
UNIT_DST="/etc/systemd/system/garmin-pull.service"
sudo cp "$UNIT_SRC" "$UNIT_DST"
sudo systemctl daemon-reload
sudo systemctl enable --now garmin-pull.service
sudo systemctl status garmin-pull.service --no-pager -n 20
