#!/usr/bin/env bash
# TerraForge Phase 1 — Acceptance Criteria Health Check
# Validates all Phase 1 acceptance criteria.
#
# Usage:
#   ./health_check.sh https://coordinator.yourdomain.com
#   ./health_check.sh    (reads URL from terraform output)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"

G='\033[0;32m' R='\033[0;31m' C='\033[0;36m' B='\033[1m' X='\033[0m'
pass()  { echo -e "  ${G}✓${X} $*"; }
fail()  { echo -e "  ${R}✗${X} $*"; FAILURES=$((FAILURES+1)); }
info()  { echo -e "  ${C}→${X} $*"; }
FAILURES=0

echo -e "${B}TerraForge Phase 1 — Acceptance Criteria${X}"
echo -e "${B}═════════════════════════════════════════${X}"
echo ""

# ── Resolve URL ────────────────────────────────────────────────────
if [ -n "${1:-}" ]; then
  BASE="${1%/}"
else
  if [ -f "$TERRAFORM_DIR/terraform.tfstate" ]; then
    BASE=$(cd "$TERRAFORM_DIR" && terraform output -raw coordinator_url 2>/dev/null || echo "")
  fi
  if [ -z "${BASE:-}" ]; then
    echo -e "${R}Usage: $0 <coordinator-url>${X}"
    echo "Example: $0 https://coordinator.yourdomain.com"
    exit 1
  fi
fi
echo -e "${C}Coordinator: $BASE${X}"
echo ""

# ── 1. /health returns 200 ─────────────────────────────────────────
echo "[ 1 ] TerraForge Server /health"
HTTP=$(curl -sk -o /tmp/tf_health.json -w "%{http_code}" "$BASE/health" 2>/dev/null || echo "000")
if [ "$HTTP" = "200" ]; then
  BODY=$(cat /tmp/tf_health.json 2>/dev/null || echo "")
  pass "HTTP 200 — $BODY"
else
  fail "HTTP $HTTP (expected 200)"
  info "Check: ssh ubuntu@IP tail -f /var/log/terraforge-startup.log"
fi

# ── 2. TLS certificate valid ────────────────────────────────────────
echo ""
echo "[ 2 ] TLS certificate (Let's Encrypt)"
DOMAIN="${BASE#https://}"
EXPIRY=$(echo | timeout 5 openssl s_client -servername "$DOMAIN" -connect "$DOMAIN:443" 2>/dev/null \
  | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")
if [ -n "$EXPIRY" ]; then
  pass "Valid — expires: $EXPIRY"
else
  TLS=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 "$BASE/" 2>/dev/null || echo "000")
  if [ "$TLS" != "000" ]; then
    pass "TLS handshake OK (openssl not available for expiry check)"
  else
    fail "TLS connection failed — cert may still be issuing (wait ~2 min)"
  fi
fi

# ── 3. Headscale API reachable ──────────────────────────────────────
echo ""
echo "[ 3 ] Headscale API"
HS=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/api/v1/machine" 2>/dev/null || echo "000")
case "$HS" in
  401|403) pass "HTTP $HS — Headscale API reachable (auth required — expected)" ;;
  200)     pass "HTTP 200 — Headscale API open" ;;
  *)       fail "HTTP $HS — Headscale API not responding" ;;
esac

# ── 4. DERP relay ──────────────────────────────────────────────────
echo ""
echo "[ 4 ] DERP relay"
DERP=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/derp" 2>/dev/null || echo "000")
case "$DERP" in
  200|426) pass "HTTP $DERP — DERP relay responding" ;;
  *)       fail "HTTP $DERP — DERP relay may not be ready" ;;
esac

# ── 5. Landing page served ──────────────────────────────────────────
echo ""
echo "[ 5 ] Landing page"
LAND=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/" 2>/dev/null || echo "000")
if [ "$LAND" = "200" ]; then
  pass "HTTP 200 — Landing page served"
else
  fail "HTTP $LAND — Landing page not serving"
fi

# ── 6. Phase 2 /join endpoint stub ─────────────────────────────────
echo ""
echo "[ 6 ] /join endpoint (Phase 2 stub)"
JOIN=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/join" 2>/dev/null || echo "000")
if [ "$JOIN" = "503" ] || [ "$JOIN" = "200" ]; then
  pass "HTTP $JOIN — /join endpoint responding (Phase 2 stub)"
else
  fail "HTTP $JOIN — /join not found"
fi

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo -e "${B}═════════════════════════════════════════${X}"
if [ "$FAILURES" -eq 0 ]; then
  echo -e "${G}${B}✓ Phase 1: ALL ACCEPTANCE CRITERIA PASSED${X}"
  echo ""
  echo "Coordinator is healthy. Proceed to Phase 2 (Node Join Flow)."
  echo ""
  echo "Next: terraforge coordinator phase2"
  exit 0
else
  echo -e "${R}${B}✗ $FAILURES check(s) failed${X}"
  echo ""
  echo "Troubleshoot:"
  echo "  ssh ubuntu@IP tail -f /var/log/terraforge-startup.log"
  echo "  ssh ubuntu@IP 'docker compose -f /opt/terraforge/docker-compose.yml logs'"
  exit 1
fi
