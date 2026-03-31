#!/usr/bin/env bash
# TerraForge Phase 1 — Coordinator Deployment Script
# terraform init → validate → plan → apply → health check
#
# Usage:
#   ./deploy.sh                  Full deploy
#   ./deploy.sh --plan-only      terraform plan, no apply
#   ./deploy.sh --destroy        Tear down the coordinator

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="$SCRIPT_DIR/../terraform"
PLAN_ONLY=false
DESTROY=false

for arg in "$@"; do
  case $arg in
    --plan-only) PLAN_ONLY=true ;;
    --destroy)   DESTROY=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ── Colors ────────────────────────────────────────────────────────
R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' C='\033[0;36m' B='\033[1m' X='\033[0m'
info()    { echo -e "${C}▶${X} $*"; }
ok()      { echo -e "${G}✓${X} $*"; }
warn()    { echo -e "${Y}⚠${X} $*"; }
err()     { echo -e "${R}✗${X} $*" >&2; }
header()  { echo -e "\n${B}$*${X}\n"; }

header "TerraForge Phase 1 — Coordinator Deployment"

# ── Prerequisites ──────────────────────────────────────────────────
info "Checking prerequisites..."
if ! command -v terraform &>/dev/null; then
  err "Terraform not found. Install: https://developer.hashicorp.com/terraform/install"
  exit 1
fi
TF_VER=$(terraform version -json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['terraform_version'])" 2>/dev/null \
  || terraform version | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
ok "Terraform $TF_VER"

if ! command -v gcloud &>/dev/null; then
  warn "gcloud CLI not found. Ensure GOOGLE_APPLICATION_CREDENTIALS is set."
fi

# ── Check tfvars ───────────────────────────────────────────────────
TFVARS="$TERRAFORM_DIR/terraform.tfvars"
if [ ! -f "$TFVARS" ]; then
  err "terraform.tfvars not found at: $TFVARS"
  echo ""
  echo "Create it:"
  echo "  cp $TERRAFORM_DIR/terraform.tfvars.example $TFVARS"
  echo "  # Fill in project_id, domain, admin_token, acme_email"
  exit 1
fi

if grep -qE 'your-gcp-project-id|FILL THIS IN' "$TFVARS" 2>/dev/null; then
  err "terraform.tfvars still has placeholder values. Fill in all required fields."
  exit 1
fi
ok "terraform.tfvars OK"

# ── Init + Plan ────────────────────────────────────────────────────
cd "$TERRAFORM_DIR"

header "terraform init"
terraform init -upgrade

header "terraform validate"
terraform validate && ok "Config valid"

header "terraform plan"
terraform plan -out=tfplan

if $PLAN_ONLY; then
  info "Plan complete. Run without --plan-only to apply."
  exit 0
fi

# ── Destroy ────────────────────────────────────────────────────────
if $DESTROY; then
  warn "About to DESTROY the coordinator. All data will be lost."
  read -rp "Type 'yes' to confirm: " CONFIRM
  [ "$CONFIRM" = "yes" ] || { echo "Aborted."; exit 0; }
  header "terraform destroy"
  terraform destroy -auto-approve
  ok "Coordinator destroyed."
  exit 0
fi

# ── Apply ──────────────────────────────────────────────────────────
header "terraform apply"
terraform apply tfplan

# ── Outputs ───────────────────────────────────────────────────────
IP=$(terraform output -raw coordinator_ip 2>/dev/null || echo "")
URL=$(terraform output -raw coordinator_url 2>/dev/null || echo "")

header "Deployment Complete"
ok "IP:   $IP"
ok "URL:  $URL"
echo ""
info "Startup takes ~3-5 min. Monitor:"
echo "    ssh ubuntu@$IP tail -f /var/log/terraforge-startup.log"
echo ""
info "Verify Phase 1 acceptance criteria:"
echo "    $(dirname "$0")/health_check.sh $URL"
echo ""
warn "Next: Phase 2 — Node Join Flow"
