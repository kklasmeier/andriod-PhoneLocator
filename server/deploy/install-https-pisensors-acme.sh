#!/usr/bin/env bash
# Phase 3 HTTPS via acme.sh TLS-ALPN-01 on port 443.
# Use when ISP blocks inbound port 80 and certbot HTTP-01 fails.
# Requires router TCP 443 → piSensors:443 (connection refused from outside = OK).
#
# Usage:
#   CERTBOT_EMAIL=kklasmei@yahoo.com bash server/deploy/install-https-pisensors-acme.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${PHONE_LOCATOR_DOMAIN:-kklasmei.mooo.com}"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "${EMAIL}" ]]; then
  echo "ERROR: Set CERTBOT_EMAIL, e.g.:"
  echo "  CERTBOT_EMAIL=you@example.com bash server/deploy/install-https-pisensors-acme.sh"
  exit 1
fi

ACME_HOME="${HOME}/.acme.sh"
ACME_SH="${ACME_HOME}/acme.sh"
CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"

if [[ ! -x "${ACME_SH}" ]]; then
  echo "==> Installing acme.sh"
  curl -fsS https://get.acme.sh | sh -s "email=${EMAIL}"
fi

echo "==> Requesting certificate (TLS-ALPN-01 on port 443)"
# Port 443 must be free — nginx should not be listening on 443 yet.
sudo "${ACME_SH}" --issue -d "${DOMAIN}" --alpn --force

echo "==> Installing certificate to ${CERT_DIR}"
sudo mkdir -p "${CERT_DIR}"
sudo "${ACME_SH}" --install-cert -d "${DOMAIN}" \
  --key-file "${CERT_DIR}/privkey.pem" \
  --fullchain-file "${CERT_DIR}/fullchain.pem" \
  --reloadcmd "sudo systemctl reload nginx"

echo "==> nginx HTTPS config"
SKIP_CERT_REQUEST=1 CERTBOT_EMAIL="${EMAIL}" bash "${REPO_ROOT}/deploy/install-https-pisensors.sh"

echo "==> Done."
echo "    curl -s https://${DOMAIN}/api/v1/health"
