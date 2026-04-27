#!/usr/bin/env bash
# Install the GestureSlides systemd user service.
# Run once after cloning / relocating the repo.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="gesture_slides"
SERVICE_FILE="${SCRIPT_DIR}/gesture_slides.service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

if [[ ! -f "$SERVICE_FILE" ]]; then
    echo "ERROR: gesture_slides.service not found in ${SCRIPT_DIR}" >&2
    exit 1
fi

# Rewrite WorkingDirectory to the actual repo location.
mkdir -p "$SYSTEMD_USER_DIR"
sed "s|WorkingDirectory=.*|WorkingDirectory=${SCRIPT_DIR}|g" \
    "$SERVICE_FILE" > "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"

systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}.service"
systemctl --user start  "${SERVICE_NAME}.service"

echo ""
echo "✓ GestureSlides service installed and started."
echo "  Status : systemctl --user status ${SERVICE_NAME}"
echo "  Logs   : journalctl --user -u ${SERVICE_NAME} -f"
echo "  Stop   : systemctl --user stop ${SERVICE_NAME}"
echo "  Disable: systemctl --user disable ${SERVICE_NAME}"
