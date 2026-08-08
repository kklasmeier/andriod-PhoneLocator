#!/usr/bin/env bash
# Fallback: obtain Let's Encrypt cert via DNS-01 (no inbound ports required).
# Use when ISP blocks ports 80/443 from the internet.
#
# You will be prompted to add a TXT record at afraid.org, then press Enter.
#
# Usage:
#   CERTBOT_EMAIL=you@example.com bash server/deploy/install-https-pisensors-dns.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${PHONE_LOCATOR_DOMAIN:-kklasmei.mooo.com}"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "${EMAIL}" ]]; then
  echo "ERROR: Set CERTBOT_EMAIL"
  exit 1
fi

echo "==> DNS-01 manual challenge for ${DOMAIN}"
echo "    At afraid.org add a TXT record when certbot prompts:"
echo "      Name:  _acme-challenge.kklasmei"
echo "      Type:  TXT"
echo "      Value: (shown by certbot)"
echo ""

sudo apt-get install -y certbot 2>/dev/null || true

sudo certbot certonly \
  --manual \
  --preferred-challenges dns \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos

echo ""
echo "==> Certificate obtained. Installing nginx HTTPS config..."
SKIP_CERT_REQUEST=1 CERTBOT_EMAIL="${EMAIL}" bash "${REPO_ROOT}/deploy/install-https-pisensors.sh"
