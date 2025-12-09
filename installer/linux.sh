#!/usr/bin/env bash
set -euo pipefail

# TKAutoRipper Ubuntu installer (beta)
# -----------------------------------
# - Checks for HandBrake Flatpak, MakeMKV and LACT
# - Tries to auto-install LACT (Ubuntu headless build) from GitHub if missing
# - Installs Ubuntu packages (python, abcde, zstd, etc.)
# - Creates a virtualenv and installs Python deps
#
# Run from the repo root:
#   bash installer/linux.sh

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

info()  { echo -e "${GREEN}[*]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*" >&2; }

# --- sanity: must be in repo root ---
if [ ! -f "main.py" ] || [ ! -d "app" ]; then
  error "Please run this script from the TKAutoRipper repository root."
  exit 1
fi

# --- OS check (soft) ---
if [ -r /etc/os-release ]; then
  . /etc/os-release
  if [ "${ID:-}" != "ubuntu" ]; then
    warn "This installer is only tested on Ubuntu. Detected: ${ID:-unknown}"
    warn "Continuing anyway in 5 seconds... (Ctrl+C to cancel)"
    sleep 5
  else
    info "Ubuntu detected (${PRETTY_NAME:-$ID})."
  fi
else
  warn "Could not read /etc/os-release; proceeding as if Ubuntu."
fi

# --- helper: ensure curl exists (for LACT install) ---
ensure_curl() {
  if command -v curl >/dev/null 2>&1; then
    return 0
  fi
  info "curl not found; installing curl..."
  sudo apt update
  sudo apt install -y curl
}

# --- helper: auto-install LACT headless ubuntu build from GitHub ---
install_lact() {
  info "Attempting to auto-install LACT (Ubuntu headless build) from GitHub releases..."
  ensure_curl

  local api_url="https://api.github.com/repos/ilya-zlobintsev/LACT/releases/latest"
  local asset_url

  asset_url="$(curl -s "$api_url" \
    | grep browser_download_url \
    | grep -i ubuntu \
    | grep -i headless \
    | head -n1 \
    | cut -d '"' -f 4 || true)"

  if [ -z "$asset_url" ]; then
    warn "Could not find an 'ubuntu' + 'headless' asset in latest LACT release."
    return 1
  fi

  info "Found LACT asset: $asset_url"
  local tmpdeb
  tmpdeb="$(mktemp /tmp/lact-XXXXXX.deb)"

  info "Downloading LACT .deb..."
  if ! curl -L "$asset_url" -o "$tmpdeb"; then
    warn "Download failed."
    rm -f "$tmpdeb"
    return 1
  fi

  info "Installing LACT via dpkg..."
  if ! sudo dpkg -i "$tmpdeb"; then
    warn "dpkg reported issues; attempting 'sudo apt -f install' to fix dependencies..."
    sudo apt -f install -y || true
    sudo systemctl enable --now lactd.service
  fi

  rm -f "$tmpdeb"

  # Re-check: is lactd running or socket present?
  if systemctl is-active --quiet lactd 2>/dev/null || [ -S /run/lactd.sock ]; then
    info "LACT appears installed and available."
    return 0
  else
    warn "LACT still not detected after install attempt."
    return 1
  fi
}

# --- Check third-party tools ---------------------------------

HB_OK=false
MM_OK=false
LACT_OK=false

info "Checking third-party tools (HandBrake Flatpak, MakeMKV, LACT)..."

# HandBrake Flatpak (fr.handbrake.ghb)
if command -v flatpak >/dev/null 2>&1; then
  if flatpak list 2>/dev/null | awk '{print $2}' | grep -qx "fr.handbrake.ghb"; then
    info "HandBrake Flatpak (fr.handbrake.ghb) detected."
    HB_OK=true
  else
    error "HandBrake Flatpak (fr.handbrake.ghb) NOT detected."
    echo "  Install from Flathub / HandBrake docs:"
    echo "  - https://flathub.org/apps/fr.handbrake.ghb"
    echo "  - https://handbrake.fr/docs/"
  fi
else
  error "flatpak command not found; cannot detect HandBrake Flatpak."
  echo "  Install Flatpak + HandBrake from:"
  echo "  - https://flathub.org/apps/fr.handbrake.ghb"
  echo "  - https://handbrake.fr/docs/"
fi

# MakeMKV
if command -v makemkvcon >/dev/null 2>&1; then
  info "MakeMKV (makemkvcon) detected."
  MM_OK=true
else
  error "MakeMKV (makemkvcon) NOT detected."
  echo "  Download / install instructions:"
  echo "  - https://makemkv.com/download/"
fi

# LACT (optional: try auto-install if missing)
if systemctl is-active --quiet lactd 2>/dev/null || [ -S /run/lactd.sock ]; then
  info "LACT daemon/socket detected (GPU telemetry enabled)."
  LACT_OK=true
else
  warn "LACT daemon/socket not detected (GPU telemetry will be disabled)."
  echo "  Trying automatic install of LACT (Ubuntu headless build) from GitHub..."
  if install_lact; then
    LACT_OK=true
  else
    warn "Automatic LACT install failed or LACT not detected afterwards."
    echo "  You can install LACT manually from:"
    echo "  - https://github.com/ilya-zlobintsev/LACT"
  fi
fi

# Gate on HandBrake + MakeMKV; LACT is optional
if [ "$HB_OK" != true ] || [ "$MM_OK" != true ]; then
  error "Required tools missing. Please install HandBrake Flatpak and MakeMKV first."
  exit 1
fi

# --- Install Ubuntu packages --------------------------------
info "Installing required Ubuntu packages (python, abcde, zstd, etc.)..."

sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  abcde \
  zstd bzip2 \
  coreutils util-linux udev eject

info "System packages installed / already present."

# --- Create virtualenv --------------------------------------
VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python virtual environment in $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
else
  info "Virtualenv $VENV_DIR already exists; reusing."
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

info "Upgrading pip..."
pip install --upgrade pip

# --- Install Python requirements -----------------------------
REQ_FILE="installer/requirements_linux.txt"
if [ ! -f "$REQ_FILE" ]; then
  error "Requirements file not found: $REQ_FILE"
  exit 1
fi

info "Installing Python dependencies from $REQ_FILE..."
pip install -r "$REQ_FILE"

info "Python dependencies installed."

# --- Final message ------------------------------------------
cat <<EOF

${GREEN}Installation complete.${NC}

To start TKAutoRipper:

  cd "$(pwd)"
  source $VENV_DIR/bin/activate
  python3 main.py

Then open:

  https://[::1]:8000

Default auth (change this in config!):

  username: admin
  password: admin

Remember to keep this repo under Git and commit your config changes periodically.

EOF
