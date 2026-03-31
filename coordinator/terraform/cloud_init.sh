#!/bin/bash
# TerraForge Coordinator — Cloud Init / Startup Script
# Runs as root on first boot of the GCP e2-micro instance.
# Reads config from GCP instance metadata, installs Docker,
# writes all service configs, and starts the stack.
#
# Logs: /var/log/terraforge-startup.log

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

LOG=/var/log/terraforge-startup.log
exec > >(tee -a "$LOG") 2>&1

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  TerraForge Coordinator — Startup $(date -u '+%Y-%m-%dT%H:%M:%SZ')  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Read config from GCP instance metadata ──────────────────────────
METADATA="http://169.254.169.254/computeMetadata/v1/instance/attributes"
_meta() { curl -sf -H "Metadata-Flavor: Google" "${METADATA}/$1" 2>/dev/null || echo "${2:-}"; }

DOMAIN=$(_meta tf-domain)
ADMIN_TOKEN=$(_meta tf-admin-token)
ACME_EMAIL=$(_meta tf-acme-email)
HEADSCALE_VERSION=$(_meta tf-headscale-version "0.23.0")
TF_SERVER_VERSION=$(_meta tf-server-version "latest")

[[ -z "$DOMAIN" || -z "$ADMIN_TOKEN" || -z "$ACME_EMAIL" ]] && {
  echo "ERROR: Required metadata missing (tf-domain, tf-admin-token, tf-acme-email)"
  exit 1
}

echo "Domain:            $DOMAIN"
echo "ACME email:        $ACME_EMAIL"
echo "Headscale:         $HEADSCALE_VERSION"
echo "TerraForge Server: $TF_SERVER_VERSION"
echo ""

# ── System packages ──────────────────────────────────────────────────
echo "── [1/7] System packages"
apt-get update -qq
apt-get install -yqq curl ca-certificates gnupg lsb-release ufw jq
echo "✓ Done"
echo ""

# ── Docker CE ────────────────────────────────────────────────────────
echo "── [2/7] Docker CE"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -qq
apt-get install -yqq docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
echo "✓ Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"
echo ""

# ── Directory structure ──────────────────────────────────────────────
echo "── [3/7] Directory structure"
mkdir -p \
  /opt/terraforge/headscale \
  /opt/terraforge/data \
  /opt/terraforge/caddy/data \
  /opt/terraforge/caddy/config \
  /opt/terraforge/logs \
  /var/run/headscale \
  /var/log/caddy
chmod 770 /var/run/headscale
echo "✓ Done"
echo ""

# ── Headscale config ─────────────────────────────────────────────────
echo "── [4/7] Service configs"
cat > /opt/terraforge/headscale/config.yaml << HEADSCALE_EOF
---
server_url: https://${DOMAIN}
listen_addr: 0.0.0.0:8080
metrics_listen_addr: 127.0.0.1:9090
grpc_listen_addr: 0.0.0.0:50443
grpc_allow_insecure: false

private_key_path: /var/lib/headscale/private.key
noise:
  private_key_path: /var/lib/headscale/noise_private.key

ip_prefixes:
  - 100.64.0.0/10

derp:
  server:
    enabled: true
    region_id: 999
    region_code: "tf-derp"
    region_name: "TerraForge DERP"
    stun_listen_addr: "0.0.0.0:3478"
  urls:
    - https://controlplane.tailscale.com/derpmap/default
  auto_update_enabled: true
  update_frequency: 24h

disable_check_updates: true
ephemeral_node_inactivity_timeout: 30m
node_update_check_interval: 10s

database:
  type: sqlite3
  sqlite:
    path: /var/lib/headscale/db.sqlite

acme_url: https://acme-v02.api.letsencrypt.org/directory
acme_email: ${ACME_EMAIL}
tls_letsencrypt_hostname: ${DOMAIN}
tls_letsencrypt_listen: ":http"
tls_letsencrypt_cache_dir: /var/lib/headscale/cache
tls_letsencrypt_challenge_type: HTTP-01

log:
  level: info

dns_config:
  magic_dns: true
  base_domain: terraforge.internal
  nameservers:
    - 1.1.1.1
    - 8.8.8.8
  override_local_dns: false

unix_socket: /var/run/headscale/headscale.sock
unix_socket_permission: "0770"
HEADSCALE_EOF

# ── Caddyfile ────────────────────────────────────────────────────────
cat > /opt/terraforge/Caddyfile << CADDY_EOF
{
    email ${ACME_EMAIL}
    admin off
}

${DOMAIN} {
    # Headscale gRPC (Tailscale key exchange)
    @grpc { protocol grpc }
    reverse_proxy @grpc h2c://headscale:50443

    # Headscale REST API + DERP + STUN
    @headscale {
        path /api/v1/*
        path /machine/*
        path /key
        path /register
        path /oidc/*
        path /apple/*
        path /windows
        path /windows/*
        path /derp
        path /derp/*
        path /ts2021
        path /swagger/*
        path /openapi.yaml
    }
    reverse_proxy @headscale headscale:8080

    # TerraForge Server: /health, /join, /api/v1/*, /app, /
    reverse_proxy terraforge-server:8000

    log {
        output file /var/log/caddy/access.log {
            roll_size 10mb
            roll_keep 5
        }
    }
}
CADDY_EOF

# ── docker-compose.yml ───────────────────────────────────────────────
cat > /opt/terraforge/docker-compose.yml << COMPOSE_EOF
version: "3.9"

services:
  headscale:
    image: headscale/headscale:${HEADSCALE_VERSION}
    container_name: headscale
    restart: unless-stopped
    command: headscale serve
    volumes:
      - /opt/terraforge/headscale/config.yaml:/etc/headscale/config.yaml:ro
      - headscale_data:/var/lib/headscale
      - /var/run/headscale:/var/run/headscale
    expose:
      - "8080"
      - "50443"
      - "9090"
    networks:
      - tf
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:9090/metrics"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s

  terraforge-server:
    image: ghcr.io/terraforge/server:${TF_SERVER_VERSION}
    container_name: terraforge-server
    restart: unless-stopped
    environment:
      TF_ADMIN_TOKEN: "${ADMIN_TOKEN}"
      TF_HEADSCALE_URL: "http://headscale:8080"
      TF_HEADSCALE_API_KEY: ""
      TF_DB_PATH: "/data/terraforge.db"
      TF_PUBLIC_URL: "https://${DOMAIN}"
      TF_ENV: "production"
    volumes:
      - /opt/terraforge/data:/data
      - /var/run/headscale:/var/run/headscale:ro
    expose:
      - "8000"
    depends_on:
      headscale:
        condition: service_healthy
    networks:
      - tf
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s

  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - /opt/terraforge/Caddyfile:/etc/caddy/Caddyfile:ro
      - /opt/terraforge/caddy/data:/data
      - /opt/terraforge/caddy/config:/config
      - /var/log/caddy:/var/log/caddy
    depends_on:
      - headscale
      - terraforge-server
    networks:
      - tf

volumes:
  headscale_data:

networks:
  tf:
    driver: bridge
COMPOSE_EOF

echo "✓ All configs written"
echo ""

# ── UFW firewall ─────────────────────────────────────────────────────
echo "── [5/7] Firewall (UFW)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   comment "SSH"
ufw allow 80/tcp   comment "ACME HTTP-01"
ufw allow 443/tcp  comment "Headscale HTTPS + TerraForge"
ufw allow 443/udp  comment "HTTP/3 QUIC"
ufw allow 3478/udp comment "STUN/DERP relay"
ufw --force enable
echo "✓ Done"
echo ""

# ── Start services ────────────────────────────────────────────────────
echo "── [6/7] Starting services"
cd /opt/terraforge

# Pull with retry — network can be slow on first boot
for i in 1 2 3; do
  docker compose pull --quiet && break || {
    echo "  Pull attempt $i failed, retrying..."
    sleep 15
  }
done

docker compose up -d
echo "✓ Services started"
echo ""

# ── Wait for health ───────────────────────────────────────────────────
echo "── [7/7] Waiting for TerraForge Server health"
for i in $(seq 1 40); do
  if docker compose exec -T terraforge-server curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ Healthy after ${i} attempts"
    break
  fi
  printf "."
  sleep 5
done
echo ""

# ── Generate Headscale API key ────────────────────────────────────────
HS_KEY=$(docker exec headscale headscale apikeys create --expiration 9999d 2>/dev/null | tail -1 || true)
if [ -n "$HS_KEY" ]; then
  echo "TF_HEADSCALE_API_KEY=${HS_KEY}" > /opt/terraforge/.env
  docker compose restart terraforge-server 2>/dev/null || true
  echo "✓ Headscale API key stored → /opt/terraforge/.env"
else
  echo "WARNING: Could not generate Headscale API key — retry manually:"
  echo "  docker exec headscale headscale apikeys create --expiration 9999d"
fi

date -u > /opt/terraforge/.startup_complete

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Startup complete  $(date -u '+%Y-%m-%dT%H:%M:%SZ')              ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Dashboard:  https://${DOMAIN}                           ║"
echo "║  Health:     https://${DOMAIN}/health                    ║"
echo "║  API:        https://${DOMAIN}/api/v1                    ║"
echo "╚══════════════════════════════════════════════════════════╝"
