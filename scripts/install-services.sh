#!/bin/bash
# Install TenderMate as user-level systemd services (auto-restart on crash)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"

mkdir -p "$SYSTEMD_DIR"

cp "$SCRIPT_DIR/tendermate-backend.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/tendermate-frontend.service" "$SYSTEMD_DIR/"

systemctl --user daemon-reload
systemctl --user enable tendermate-backend tendermate-frontend
systemctl --user start tendermate-backend tendermate-frontend

echo "TenderMate services installed and started."
echo ""
echo "Commands:"
echo "  systemctl --user status tendermate-backend"
echo "  systemctl --user status tendermate-frontend"
echo "  journalctl --user -u tendermate-backend -f"
echo "  journalctl --user -u tendermate-frontend -f"
echo "  systemctl --user restart tendermate-backend"
