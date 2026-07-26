#!/usr/bin/env bash
# First-time install of Phone Locator API on PiSensors. Run from repo root on the Pi.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_ROOT="/opt/phone-locator"
ENV_DIR="/etc/phone-locator"
ENV_FILE="${ENV_DIR}/phone-locator.env"
DATA_DIR="/var/lib/phone-locator"
NGINX_SITE="/etc/nginx/sites-available/pivpngateway"
SNIPPET_MARKER="# phone-locator"

echo "==> Installing Phone Locator API to ${INSTALL_ROOT}"
sudo mkdir -p "${INSTALL_ROOT}" "${ENV_DIR}" "${DATA_DIR}"
sudo rsync -a --delete \
  --exclude venv \
  --exclude .env \
  --exclude data \
  "${REPO_ROOT}/app" \
  "${REPO_ROOT}/requirements.txt" \
  "${INSTALL_ROOT}/"
sudo chown -R pi:pi "${INSTALL_ROOT}"
sudo chown pi:pi "${DATA_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "==> Creating ${ENV_FILE}"
  TOKEN="$(openssl rand -hex 32)"
  sudo tee "${ENV_FILE}" >/dev/null <<EOF
PHONE_LOCATOR_API_TOKEN=${TOKEN}
PHONE_LOCATOR_BIND_HOST=127.0.0.1
PHONE_LOCATOR_BIND_PORT=8003
PHONE_LOCATOR_DATABASE_PATH=${DATA_DIR}/phone-locator.db
PHONE_LOCATOR_TIMEZONE=America/Detroit
EOF
  sudo chmod 640 "${ENV_FILE}"
  sudo chown root:pi "${ENV_FILE}"
  echo "    API token (save for phone app setup): ${TOKEN}"
else
  echo "==> Using existing ${ENV_FILE}"
fi

echo "==> Python venv"
python3 -m venv "${INSTALL_ROOT}/venv"
"${INSTALL_ROOT}/venv/bin/pip" install -q -U pip
"${INSTALL_ROOT}/venv/bin/pip" install -q -r "${INSTALL_ROOT}/requirements.txt"

echo "==> systemd"
sudo cp "${REPO_ROOT}/deploy/phone-locator.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable phone-locator.service
sudo systemctl restart phone-locator.service

if [[ -f "${NGINX_SITE}" ]] && ! grep -q "${SNIPPET_MARKER}" "${NGINX_SITE}"; then
  echo "==> Adding /locator/ to nginx (${NGINX_SITE})"
  sudo cp "${NGINX_SITE}" "${NGINX_SITE}.bak-phone-locator"
  sudo awk -v snippet="${REPO_ROOT}/deploy/nginx-locator.snippet" '
    /location \/ \{/ && !done {
      while ((getline line < snippet) > 0) print line
      print "    # phone-locator"
      done=1
    }
    { print }
  ' "${NGINX_SITE}.bak-phone-locator" | sudo tee "${NGINX_SITE}" >/dev/null
  sudo nginx -t
  sudo systemctl reload nginx
else
  echo "==> nginx: ${NGINX_SITE} already has phone-locator block or site file missing — check deploy/nginx-locator.snippet manually"
fi

echo "==> Health check"
sleep 1
curl -fsS "http://127.0.0.1:8003/api/v1/health"
echo ""
curl -fsS "http://127.0.0.1:8000/locator/api/v1/health" || echo "(nginx /locator/ path not ready yet)"
echo ""
echo "==> Done."
echo "    Direct:  http://$(hostname -I | awk '{print $1}'):8003/api/v1/health"
echo "    nginx:   http://$(hostname -I | awk '{print $1}'):8000/locator/api/v1/health"
echo "    Token:   sudo grep PHONE_LOCATOR_API_TOKEN ${ENV_FILE}"
