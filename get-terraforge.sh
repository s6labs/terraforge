#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  TerraForge — Universal One-Line Installer
#  Usage:  curl -fsSL https://get.terraforge.io | bash
#          curl -fsSL https://raw.githubusercontent.com/s6labs/terraforge/main/get-terraforge.sh | bash
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="s6labs/terraforge"
BINARY_NAME="terraforge"
INSTALL_DIR=""   # resolved below

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}→${RESET} $*"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET} $*"; }
die()     { echo -e "${RED}✗ ERROR:${RESET} $*" >&2; exit 1; }

# ── Banner ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ████████╗███████╗██████╗ ██████╗  █████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗"
echo "     ██╔══╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝"
echo "     ██║   █████╗  ██████╔╝██████╔╝███████║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  "
echo "     ██║   ██╔══╝  ██╔══██╗██╔══██╗██╔══██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  "
echo "     ██║   ███████╗██║  ██║██║  ██║██║  ██║██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗"
echo "     ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
echo -e "${RESET}  ${CYAN}AI-Powered Coder Workspace Template Generator — S6Labs${RESET}"
echo ""

# ── Detect OS and Architecture ────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux*)  OS_FAMILY="linux"  ;;
  Darwin*) OS_FAMILY="darwin" ;;
  MINGW*|MSYS*|CYGWIN*) OS_FAMILY="windows" ;;
  *) die "Unsupported operating system: $OS" ;;
esac

case "$ARCH" in
  x86_64|amd64)   ARCH_NORM="amd64" ;;
  aarch64|arm64)  ARCH_NORM="arm64" ;;
  *) die "Unsupported architecture: $ARCH" ;;
esac

# Map to asset names matching the release workflow
case "${OS_FAMILY}-${ARCH_NORM}" in
  linux-amd64)  ASSET="terraforge-linux-amd64.tar.gz" ;;
  linux-arm64)  ASSET="terraforge-linux-arm64.tar.gz" ;;
  darwin-amd64) ASSET="terraforge-macos-intel.tar.gz" ;;
  darwin-arm64) ASSET="terraforge-macos-arm64.tar.gz" ;;
  windows-amd64) ASSET="terraforge-windows-amd64.zip" ;;
  *) die "No pre-built binary for ${OS_FAMILY}-${ARCH_NORM}. Install via: pip install terraforge" ;;
esac

info "Detected: ${OS_FAMILY}/${ARCH_NORM}"

# ── Fetch the latest release version ─────────────────────────────────────────
info "Fetching latest release..."

if command -v curl &>/dev/null; then
  FETCH="curl -fsSL"
elif command -v wget &>/dev/null; then
  FETCH="wget -qO-"
else
  die "Neither curl nor wget found. Install one and retry."
fi

LATEST_JSON=$($FETCH "https://api.github.com/repos/${REPO}/releases/latest")
VERSION=$(echo "$LATEST_JSON" | grep '"tag_name"' | head -1 | sed -E 's/.*"([^"]+)".*/\1/')

if [[ -z "$VERSION" ]]; then
  die "Could not determine latest version. Check your network or try again."
fi

success "Latest version: $VERSION"

# ── Resolve install directory ─────────────────────────────────────────────────
INSTALL_CANDIDATES=("/usr/local/bin" "$HOME/.local/bin" "$HOME/bin")

for dir in "${INSTALL_CANDIDATES[@]}"; do
  if [[ -d "$dir" ]] && [[ -w "$dir" ]]; then
    INSTALL_DIR="$dir"
    break
  fi
  if [[ ! -d "$dir" ]] && mkdir -p "$dir" 2>/dev/null; then
    INSTALL_DIR="$dir"
    break
  fi
done

# If writable /usr/local/bin needs sudo
if [[ -z "$INSTALL_DIR" ]]; then
  if [[ -d "/usr/local/bin" ]]; then
    if sudo -n true 2>/dev/null; then
      INSTALL_DIR="/usr/local/bin"
      USE_SUDO=true
    else
      warn "Need sudo to write to /usr/local/bin. Enter password when prompted."
      INSTALL_DIR="/usr/local/bin"
      USE_SUDO=true
    fi
  else
    die "Cannot find a writable install directory. Add \$HOME/.local/bin to PATH and retry."
  fi
fi

USE_SUDO="${USE_SUDO:-false}"
info "Installing to: $INSTALL_DIR"

# ── Download the binary ───────────────────────────────────────────────────────
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${VERSION}/${ASSET}"
CHECKSUM_URL="${DOWNLOAD_URL}.sha256"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

info "Downloading $ASSET..."
$FETCH "$DOWNLOAD_URL" -o "$TMPDIR/$ASSET"

# ── Verify checksum (if sha256sum / shasum available) ────────────────────────
info "Verifying integrity..."
if command -v sha256sum &>/dev/null; then
  EXPECTED=$($FETCH "$CHECKSUM_URL" | awk '{print $1}')
  ACTUAL=$(sha256sum "$TMPDIR/$ASSET" | awk '{print $1}')
  if [[ "$EXPECTED" != "$ACTUAL" ]]; then
    die "Checksum mismatch! Expected: $EXPECTED  Got: $ACTUAL"
  fi
  success "Checksum verified."
elif command -v shasum &>/dev/null; then
  EXPECTED=$($FETCH "$CHECKSUM_URL" | awk '{print $1}')
  ACTUAL=$(shasum -a 256 "$TMPDIR/$ASSET" | awk '{print $1}')
  if [[ "$EXPECTED" != "$ACTUAL" ]]; then
    die "Checksum mismatch! Expected: $EXPECTED  Got: $ACTUAL"
  fi
  success "Checksum verified."
else
  warn "sha256sum/shasum not found — skipping checksum verification."
fi

# ── Extract and install ───────────────────────────────────────────────────────
info "Extracting..."
case "$ASSET" in
  *.tar.gz)
    tar -xzf "$TMPDIR/$ASSET" -C "$TMPDIR"
    EXTRACTED_BINARY="$TMPDIR/$(basename "$ASSET" .tar.gz)"
    ;;
  *.zip)
    if command -v unzip &>/dev/null; then
      unzip -q "$TMPDIR/$ASSET" -d "$TMPDIR"
    else
      die "unzip not found. Install it and retry."
    fi
    EXTRACTED_BINARY="$TMPDIR/$(basename "$ASSET" .zip).exe"
    ;;
esac

chmod +x "$EXTRACTED_BINARY"

DEST="$INSTALL_DIR/$BINARY_NAME"
if [[ "$USE_SUDO" == "true" ]]; then
  sudo mv "$EXTRACTED_BINARY" "$DEST"
  sudo chmod +x "$DEST"
else
  mv "$EXTRACTED_BINARY" "$DEST"
  chmod +x "$DEST"
fi

# ── Add to PATH if needed ─────────────────────────────────────────────────────
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
  warn "$INSTALL_DIR is not in your PATH."
  SHELL_RC=""
  if [[ -f "$HOME/.zshrc" ]]; then SHELL_RC="$HOME/.zshrc"
  elif [[ -f "$HOME/.bashrc" ]]; then SHELL_RC="$HOME/.bashrc"
  elif [[ -f "$HOME/.bash_profile" ]]; then SHELL_RC="$HOME/.bash_profile"; fi

  if [[ -n "$SHELL_RC" ]]; then
    echo "" >> "$SHELL_RC"
    echo "# TerraForge" >> "$SHELL_RC"
    echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_RC"
    warn "Added $INSTALL_DIR to PATH in $SHELL_RC"
    warn "Run: source $SHELL_RC  (or open a new terminal)"
    export PATH="$INSTALL_DIR:$PATH"
  fi
fi

# ── Confirm installation ──────────────────────────────────────────────────────
echo ""
if "$DEST" --version 2>/dev/null; then
  :
elif "$DEST" --help 2>/dev/null | head -1; then
  :
fi

echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
success "TerraForge ${VERSION} installed successfully!"
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${BOLD}Quick start:${RESET}"
echo -e "  ${CYAN}terraforge --detect${RESET}                     # scan for LLM providers"
echo -e "  ${CYAN}terraforge \"python fastapi workspace\"${RESET}   # generate a template"
echo -e "  ${CYAN}terraforge server${RESET}                       # launch the Web UI"
echo ""
echo -e "  ${BOLD}Docs:${RESET}  https://github.com/${REPO}#readme"
echo ""
