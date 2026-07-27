#!/usr/bin/env bash
# Phase 3: HTTPS for Phone Locator on piSensors (kklasmei.mooo.com).
# Run from repo root on piSensors AFTER router forwards external 443 → piSensors:443.
#
# Prerequisites:
#   - Phone Locator API installed (install-pisensors.sh)
#   - DDNS kklasmei.mooo.com points at your home public IP
#   - Router: TCP 443 → 192.168.1.26:443
#   - Router: TCP 80 → 192.168.1.26:80 (Let's Encrypt HTTP-01; may already exist)
#
# Usage:
#   CERTBOT_EMAIL=you@example.com bash server/deploy/install-https-pisensors.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${PHONE_LOCATOR_DOMAIN:-kklasmei.mooo.com}"
NGINX_SITE="/etc/nginx/sites-available/phone-locator-https"
NGINX_ENABLED="/etc/nginx/sites-enabled/phone-locator-https"
WEBROOT="/var/www/certbot"
EMAIL="${CERTBOT_EMAIL:-}"

if [[ -z "${EMAIL}" ]]; then
  echo "ERROR: Set CERTBOT_EMAIL for Let's Encrypt, e.g.:"
  echo "  CERTBOT_EMAIL=you@example.com bash server/deploy/install-https-pisensors.sh"
  exit 1
fi

echo "==> Domain: ${DOMAIN}"
echo "==> Installing certbot"
sudo apt-get update -qq
sudo apt-get install -y certbot python3-certbot-nginx

echo "==> Webroot for ACME challenge"
sudo mkdir -p "${WEBROOT}"
sudo chown -R www-data:www-data "${WEBROOT}"

echo "==> nginx site: ${NGINX_SITE}"
sudo cp "${REPO_ROOT}/deploy/nginx-locator-https.conf" "${NGINX_SITE}"
sudo ln -sf "${NGINX_SITE}" "${NGINX_ENABLED}"
sudo nginx -t
sudo systemctl reload nginx

echo "==> Requesting certificate (HTTP-01 via webroot)"
sudo certbot certonly \
  --webroot \
  -w "${WEBROOT}" \
  -d "${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive \
  --keep-until-expiring

echo "==> Installing full HTTPS nginx config"
sudo tee "${NGINX_SITE}" >/dev/null <<EOF
# Phone Locator — ${DOMAIN} (managed by install-https-pisensors.sh)

server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Phone API (base URL https://${DOMAIN})
    location /api/v1/ {
        proxy_pass http://127.0.0.1:8003/api/v1/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Web dashboard (Phase 6) — same backend, path prefix
    location /locator/ {
        proxy_pass http://127.0.0.1:8003/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location = /locator {
        return 301 /locator/;
    }

    location / {
        return 404;
    }
}
EOF

sudo nginx -t
sudo systemctl reload nginx

echo "==> Certbot renewal timer"
sudo systemctl enable certbot.timer 2>/dev/null || true
sudo systemctl start certbot.timer 2>/dev/null || true

echo "==> Health checks"
sleep 1
curl -fsS "https://${DOMAIN}/api/v1/health" && echo ""
curl -fsS "https://${DOMAIN}/locator/api/v1/health" && echo ""

echo "==> Done."
echo "    Phone API URL: https://${DOMAIN}"
echo "    LAN (unchanged): http://192.168.1.26:8000/locator/"
echo ""
echo "    Update the phone app Settings → API URL to https://${DOMAIN}"
echo "    Then tap Test connection / Sync now."
echo ""
echo "    External test (off WiFi / cellular):"
echo "      curl -s https://${DOMAIN}/api/v1/health"
