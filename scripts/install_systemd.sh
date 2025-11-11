#!/usr/bin/env bash
set -euo pipefail
USER_INST="${1:-$USER}"
UNIT_SRC="systemd/garmin-pull@.service"
sudo cp "$UNIT_SRC" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now "garmin-pull@${USER_INST}.service"
sudo systemctl status "garmin-pull@${USER_INST}.service" --no-pager -n 30 || true
echo
echo ">>> Logs en vivo:"
echo "journalctl -u garmin-pull@${USER_INST}.service -f"
