#!/usr/bin/env bash
# TerraForge Setup Script
# Run: bash setup.sh

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

print_banner() {
cat << 'EOF'

  ████████╗███████╗██████╗ ██████╗  █████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
     ██╔══╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
     ██║   █████╗  ██████╔╝██████╔╝███████║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
     ██║   ██╔══╝  ██╔══██╗██╔══██╗██╔══██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
     ██║   ███████╗██║  ██║██║  ██║██║  ██║██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
     ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

  AI-Powered Coder Workspace Template Generator
  Setup Script v1.0

EOF
}

step() { echo -e "${CYAN}${BOLD}▶ $1${RESET}"; }
ok()   { echo -e "${GREEN}✓ $1${RESET}"; }
warn() { echo -e "${YELLOW}⚠ $1${RESET}"; }
err()  { echo -e "${RED}✗ $1${RESET}"; }

print_banner

# ── Check Python ─────────────────────────────────────────────────────
step "Checking Python..."
if ! command -v python3 &>/dev/null; then
    err "Python 3 not found. Install from https://python.org"
    exit 1
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 11) else 1)'; then
    ok "Python $PYTHON_VERSION ✓"
else
    warn "Python $PYTHON_VERSION found — Python 3.11+ recommended"
fi

# ── Create virtualenv ─────────────────────────────────────────────────
step "Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    ok "Created .venv"
else
    ok "Existing .venv found"
fi

source .venv/bin/activate

# ── Install dependencies ──────────────────────────────────────────────
step "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
ok "Dependencies installed"

# ── Check optional tools ──────────────────────────────────────────────
step "Checking optional tools..."
if command -v terraform &>/dev/null; then
    ok "terraform found ($(terraform version -json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("terraform_version","?"))' 2>/dev/null || terraform version | head -1))"
else
    warn "terraform not found — install from https://terraform.io for HCL validation (optional)"
fi

if command -v coder &>/dev/null; then
    ok "coder CLI found — template push enabled"
else
    warn "coder CLI not found — install from https://coder.com/docs/install to push templates"
fi

# ── Check LLM providers ───────────────────────────────────────────────
step "Scanning for LLM providers..."
python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from src.llm.router import detect_providers

async def scan():
    providers = await detect_providers()
    if providers:
        print(f'  Found {len(providers)} provider(s):')
        for p in providers:
            tag = 'LOCAL' if p.type.value in ['ollama','lmstudio','openai_compatible'] else 'CLOUD'
            print(f'    [{tag}] {p.name} → {p.model}')
    else:
        print('  No providers detected yet.')
        print('  → Install Ollama: https://ollama.ai')
        print('  → Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY')
asyncio.run(scan())
" 2>/dev/null || warn "Provider scan failed (this is OK at setup time)"

if [ -z "${GOOGLE_API_KEY:-}" ]; then
    echo -e "  ${YELLOW}Tip: Set GOOGLE_API_KEY to use Gemini 1.5 Flash for free cloud generation (1500 req/day).${RESET}"
    echo -e "       Get a free key at: https://aistudio.google.com/apikey"
fi

# ── Make executable ───────────────────────────────────────────────────
chmod +x terraforge.py

# ── Create .env template ──────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cat > .env << 'ENVEOF'
# TerraForge Environment Configuration
# Rename this file to .env and fill in your values

# ── Cloud LLM Providers (optional — local LLMs work without these) ──
GOOGLE_API_KEY=AIza...          # Gemini 1.5 Flash — free tier (1500 req/day)
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...

# ── Coder Instance (optional — for --push flag) ─────────────────────
# CODER_URL=https://coder.yourcompany.com
# CODER_SESSION_TOKEN=your-token-here
ENVEOF
    ok "Created .env template"
fi

# ── Done ──────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}════════════════════════════════════════${RESET}"
echo -e "${GREEN}${BOLD}  TerraForge is ready!${RESET}"
echo -e "${GREEN}${BOLD}════════════════════════════════════════${RESET}"
echo ""
echo -e "  ${BOLD}Quick start:${RESET}"
echo ""
echo -e "  ${CYAN}source .venv/bin/activate${RESET}"
echo ""
echo -e "  ${CYAN}python terraforge.py --detect${RESET}                    # See available LLMs"
echo -e "  ${CYAN}python terraforge.py --interactive${RESET}               # Guided wizard"
echo -e "  ${CYAN}python terraforge.py examples/python-ml.yaml${RESET}     # From spec file"
echo -e "  ${CYAN}python terraforge.py \"go microservices workspace\"${RESET} # Natural language"
echo ""
echo -e "  ${BOLD}VS Code:${RESET} Open this folder → Ctrl+Shift+P → ${CYAN}Tasks: Run Task${RESET}"
echo ""
