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
sudo mkdir -p "${WEBROOT}/.well-known/acme-challenge"
sudo chown -R www-data:www-data "${WEBROOT}"

echo "==> nginx site: ${NGINX_SITE}"
sudo cp "${REPO_ROOT}/deploy/nginx-locator-https.conf" "${NGINX_SITE}"
sudo ln -sf "${NGINX_SITE}" "${NGINX_ENABLED}"
sudo nginx -t
sudo systemctl reload nginx

echo "==> Requesting certificate"
request_cert() {
  if sudo certbot certonly \
    --webroot \
    -w "${WEBROOT}" \
    -d "${DOMAIN}" \
    --email "${EMAIL}" \
    --agree-tos \
    --non-interactive \
    --keep-until-expiring; then
    return 0
  fi
  echo ""
  echo "==> HTTP-01 (port 80) failed"
  echo "    Your ISP likely blocks inbound port 80."
  echo "    Try TLS-ALPN-01 on port 443 instead:"
  echo "      CERTBOT_EMAIL=${EMAIL} bash server/deploy/install-https-pisensors-acme.sh"
  echo "    Or DNS challenge (no inbound ports):"
  echo "      CERTBOT_EMAIL=${EMAIL} bash server/deploy/install-https-pisensors-dns.sh"
  return 1
}

if [[ "${SKIP_CERT_REQUEST:-}" != "1" ]]; then
  if ! request_cert; then
    echo ""
    echo "ERROR: Could not obtain certificate."
    echo "  1. Router WAN IP must match kklasmei.mooo.com (check router status page)"
    echo "  2. TCP 443 → 192.168.1.26:443 must be open from the internet"
    echo "  3. If port 80 blocked by ISP, use acme.sh on port 443:"
    echo "       CERTBOT_EMAIL=${EMAIL} bash server/deploy/install-https-pisensors-acme.sh"
    echo "  4. Or DNS challenge (no inbound ports):"
    echo "       CERTBOT_EMAIL=${EMAIL} bash server/deploy/install-https-pisensors-dns.sh"
    exit 1
  fi
else
  echo "==> Skipping certificate request (cert already obtained)"
fi

if [[ ! -f /etc/letsencrypt/options-ssl-nginx.conf ]]; then
  echo "==> Creating default SSL options (certbot templates not present)"
  sudo mkdir -p /etc/letsencrypt
  sudo tee /etc/letsencrypt/options-ssl-nginx.conf >/dev/null <<'SSLOPTS'
ssl_session_cache shared:le_nginx_SSL:10m;
ssl_session_timeout 1440m;
ssl_session_tickets off;
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers off;
SSLOPTS
  if [[ ! -f /etc/letsencrypt/ssl-dhparams.pem ]]; then
    sudo openssl dhparam -out /etc/letsencrypt/ssl-dhparams.pem 2048
  fi
fi

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
