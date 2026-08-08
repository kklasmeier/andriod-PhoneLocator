#!/usr/bin/env bash
# Deploy Phone Locator API from git clone to /opt/phone-locator (run on PiSensors after pull).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_ROOT="/opt/phone-locator"

echo "==> Deploy Phone Locator API to ${INSTALL_ROOT}"
sudo rsync -a --delete \
  --exclude venv \
  --exclude .env \
  --exclude data \
  "${REPO_ROOT}/server/app" \
  "${REPO_ROOT}/server/requirements.txt" \
  "${REPO_ROOT}/web" \
  "${INSTALL_ROOT}/"
sudo chown -R pi:pi "${INSTALL_ROOT}"

if [[ ! -d "${INSTALL_ROOT}/venv" ]]; then
  python3 -m venv "${INSTALL_ROOT}/venv"
fi
"${INSTALL_ROOT}/venv/bin/pip" install -q -U pip
"${INSTALL_ROOT}/venv/bin/pip" install -q -r "${INSTALL_ROOT}/requirements.txt"

sudo systemctl restart phone-locator
echo "==> Done. Health: http://$(hostname -I | awk '{print $1}'):8000/locator/api/v1/health"
echo "==> Dashboard: http://$(hostname -I | awk '{print $1}'):8000/locator/"
