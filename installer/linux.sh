#!/usr/bin/env bash
set -euo pipefail

# TKAutoRipper Linux installer
# ----------------------------
# - Detects common Linux package managers and installs distro-specific packages
# - Installs HandBrake Flatpak from Flathub, falling back to native HandBrakeCLI
# - Installs the HandBrake Intel Media SDK Flatpak plugin when available
# - Downloads, verifies, builds, and installs the latest MakeMKV Linux release
# - Tries to install LACT from the latest GitHub release when supported
# - Creates ~/TKAutoRipper directories/config and a Python virtualenv
#
# Run from the repo root:
#   bash installer/linux.sh
#
# Useful flags:
#   --accept-makemkv-eula  Non-interactive MakeMKV EULA acceptance
#   --force-makemkv        Rebuild/reinstall MakeMKV even if makemkvcon exists
#   --makemkv-version X    Install a specific MakeMKV version instead of latest
#   --skip-handbrake       Do not install/check HandBrake
#   --skip-intel-qsv       Do not install/check HandBrake Intel Media SDK plugin
#   --skip-lact            Do not install/check LACT
#   --skip-makemkv         Do not install/check MakeMKV

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[*]${NC} $*"; }
note()  { echo -e "${BLUE}[i]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[x]${NC} $*" >&2; }

INSTALL_HANDBRAKE=true
INSTALL_INTEL_QSV=true
INSTALL_LACT=true
INSTALL_MAKEMKV=true
FORCE_MAKEMKV=false
ACCEPT_MAKEMKV_EULA=false
MAKEMKV_VERSION=""

usage() {
  cat <<EOF
Usage: bash installer/linux.sh [options]

Options:
  --accept-makemkv-eula  Non-interactive MakeMKV EULA acceptance
  --force-makemkv        Rebuild/reinstall MakeMKV even if makemkvcon exists
  --makemkv-version X    Install a specific MakeMKV version instead of latest
  --skip-handbrake       Do not install/check HandBrake
  --skip-intel-qsv       Do not install/check HandBrake Intel Media SDK plugin
  --skip-lact            Do not install/check LACT
  --skip-makemkv         Do not install/check MakeMKV
  -h, --help             Show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --accept-makemkv-eula)
      ACCEPT_MAKEMKV_EULA=true
      ;;
    --force-makemkv)
      FORCE_MAKEMKV=true
      ;;
    --makemkv-version)
      shift
      MAKEMKV_VERSION="${1:-}"
      if [ -z "$MAKEMKV_VERSION" ]; then
        error "--makemkv-version requires a value."
        exit 1
      fi
      ;;
    --skip-handbrake)
      INSTALL_HANDBRAKE=false
      INSTALL_INTEL_QSV=false
      ;;
    --skip-intel-qsv)
      INSTALL_INTEL_QSV=false
      ;;
    --skip-lact)
      INSTALL_LACT=false
      ;;
    --skip-makemkv)
      INSTALL_MAKEMKV=false
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if [ ! -f "main.py" ] || [ ! -d "app" ] || [ ! -d "installer" ]; then
  error "Please run this script from the TKAutoRipper repository root."
  exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
else
  if ! command -v sudo >/dev/null 2>&1; then
    error "sudo is required when running as a non-root user."
    exit 1
  fi
  SUDO=(sudo)
fi

OS_ID="unknown"
OS_LIKE=""
OS_PRETTY="unknown Linux"
if [ -r /etc/os-release ]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_LIKE="${ID_LIKE:-}"
  OS_PRETTY="${PRETTY_NAME:-$OS_ID}"
fi

PKG_MANAGER=""
if command -v apt-get >/dev/null 2>&1; then
  PKG_MANAGER="apt"
elif command -v dnf >/dev/null 2>&1; then
  PKG_MANAGER="dnf"
elif command -v pacman >/dev/null 2>&1; then
  PKG_MANAGER="pacman"
elif command -v zypper >/dev/null 2>&1; then
  PKG_MANAGER="zypper"
elif command -v apk >/dev/null 2>&1; then
  PKG_MANAGER="apk"
fi

if [ -z "$PKG_MANAGER" ]; then
  error "Unsupported Linux distribution: no apt-get, dnf, pacman, zypper, or apk found."
  exit 1
fi

if [ "$PKG_MANAGER" = "apk" ]; then
  error "Alpine/apk is not supported for MakeMKV builds. MakeMKV targets glibc Linux, while Alpine uses musl."
  exit 1
fi

info "Detected $OS_PRETTY using package manager: $PKG_MANAGER"

APT_UPDATED=false

install_packages() {
  case "$PKG_MANAGER" in
    apt)
      if [ "$APT_UPDATED" = false ]; then
        "${SUDO[@]}" apt-get update
        APT_UPDATED=true
      fi
      "${SUDO[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
      ;;
    dnf)
      "${SUDO[@]}" dnf install -y "$@"
      ;;
    pacman)
      "${SUDO[@]}" pacman -Sy --needed --noconfirm "$@"
      ;;
    zypper)
      "${SUDO[@]}" zypper --non-interactive install --no-recommends "$@"
      ;;
    *)
      error "No installer implementation for package manager: $PKG_MANAGER"
      exit 1
      ;;
  esac
}

install_distro_dependencies() {
  info "Installing TKAutoRipper and MakeMKV build dependencies for $PKG_MANAGER..."

  case "$PKG_MANAGER" in
    apt)
      install_packages \
        python3 python3-venv python3-pip python3-dev \
        abcde zstd bzip2 coreutils util-linux udev eject \
        curl ca-certificates openssl \
        build-essential pkg-config libc6-dev libssl-dev libexpat1-dev \
        libavcodec-dev libgl1-mesa-dev qtbase5-dev zlib1g-dev
      ;;
    dnf)
      install_packages \
        python3 python3-pip python3-devel \
        abcde zstd bzip2 coreutils util-linux udev eject \
        curl ca-certificates openssl \
        gcc gcc-c++ make pkgconf-pkg-config glibc-devel openssl-devel \
        expat-devel ffmpeg-free-devel mesa-libGL-devel qt5-qtbase-devel zlib-devel
      ;;
    pacman)
      install_packages \
        python python-pip python-virtualenv \
        abcde zstd bzip2 coreutils util-linux systemd eject \
        curl ca-certificates openssl \
        base-devel pkgconf glibc expat ffmpeg mesa qt5-base zlib
      ;;
    zypper)
      install_packages \
        python3 python3-pip python3-virtualenv \
        abcde zstd bzip2 coreutils util-linux systemd udev eject \
        curl ca-certificates openssl \
        gcc gcc-c++ make pkg-config glibc-devel libopenssl-devel \
        libexpat-devel libavcodec-devel Mesa-libGL-devel libqt5-qtbase-devel zlib-devel
      ;;
  esac

  info "Distro packages installed or already present."
}

ensure_command() {
  local cmd="$1"
  local package="${2:-$cmd}"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    info "$cmd not found; installing $package..."
    install_packages "$package"
  fi
}

install_native_handbrake_cli() {
  if command -v HandBrakeCLI >/dev/null 2>&1; then
    info "Native HandBrakeCLI detected."
    return 0
  fi

  info "Installing native HandBrakeCLI via $PKG_MANAGER..."

  local candidates=()
  case "$PKG_MANAGER" in
    apt)
      candidates=(handbrake-cli)
      ;;
    dnf)
      candidates=(HandBrake-cli handbrake-cli HandBrakeCLI)
      ;;
    pacman)
      candidates=(handbrake-cli)
      ;;
    zypper)
      candidates=(handbrake-cli HandBrakeCLI)
      ;;
  esac

  local package
  for package in "${candidates[@]}"; do
    if install_packages "$package"; then
      if command -v HandBrakeCLI >/dev/null 2>&1; then
        info "Native HandBrakeCLI installed from package: $package"
        return 0
      fi
    fi
  done

  error "Could not install native HandBrakeCLI from the package manager."
  case "$PKG_MANAGER" in
    dnf)
      warn "On Fedora/Asahi, HandBrake packages may require enabling RPM Fusion or another media repository."
      ;;
  esac
  return 1
}

install_handbrake() {
  if [ "$INSTALL_HANDBRAKE" != true ]; then
    note "Skipping HandBrake by request."
    return 0
  fi

  if command -v flatpak >/dev/null 2>&1 && flatpak info fr.handbrake.ghb >/dev/null 2>&1; then
    info "HandBrake Flatpak (fr.handbrake.ghb) detected."
    return 0
  fi

  if command -v HandBrakeCLI >/dev/null 2>&1; then
    info "Native HandBrakeCLI detected."
    return 0
  fi

  local flatpak_ok=false
  if ! command -v flatpak >/dev/null 2>&1; then
    info "flatpak not found; installing flatpak before trying Flathub..."
    if ! install_packages flatpak; then
      warn "Could not install flatpak; will try native HandBrakeCLI instead."
    fi
  fi

  if command -v flatpak >/dev/null 2>&1; then
    info "Adding Flathub system remote if needed..."
    if ! "${SUDO[@]}" flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo; then
      warn "Could not add Flathub system remote; will try native HandBrakeCLI instead."
    else

      info "Installing HandBrake Flatpak system-wide (fr.handbrake.ghb)..."
      if "${SUDO[@]}" flatpak install --system -y flathub fr.handbrake.ghb; then
        if flatpak info fr.handbrake.ghb >/dev/null 2>&1; then
          info "HandBrake Flatpak installed."
          flatpak_ok=true
        fi
      else
        warn "HandBrake Flatpak is not available or failed to install on this system."
      fi
    fi
  fi

  if [ "$flatpak_ok" = true ]; then
    return 0
  fi

  warn "Falling back to native HandBrakeCLI package."
  install_native_handbrake_cli
}

install_intel_qsv_support() {
  if [ "$INSTALL_INTEL_QSV" != true ]; then
    note "Skipping HandBrake Intel Media SDK plugin by request."
    return 0
  fi

  if command -v flatpak >/dev/null 2>&1 && flatpak info fr.handbrake.ghb >/dev/null 2>&1; then
    if flatpak info fr.handbrake.ghb.Plugin.IntelMediaSDK >/dev/null 2>&1; then
      info "HandBrake Intel Media SDK Flatpak plugin detected."
    else
      info "Installing HandBrake Intel Media SDK Flatpak plugin..."
      "${SUDO[@]}" flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
      if "${SUDO[@]}" flatpak install --system -y flathub fr.handbrake.ghb.Plugin.IntelMediaSDK; then
        info "HandBrake Intel Media SDK Flatpak plugin installed."
      else
        warn "Could not install fr.handbrake.ghb.Plugin.IntelMediaSDK. Intel QSV support may be unavailable in HandBrake."
      fi
    fi

  else
    note "HandBrake Flatpak not detected yet; skipping Intel Media SDK plugin."
  fi

  if command -v flatpak >/dev/null 2>&1 && flatpak info fr.handbrake.ghb >/dev/null 2>&1; then
    note "HandBrake QSV check: run 'flatpak run --command=HandBrakeCLI fr.handbrake.ghb -h | grep qsv_'."
  fi
}

latest_makemkv_version() {
  local page version forum

  page="$(curl -fsSL "https://www.makemkv.com/download/" || true)"
  version="$(printf '%s\n' "$page" \
    | grep -Eo 'MakeMKV v?[0-9]+\.[0-9]+\.[0-9]+' \
    | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' \
    | head -n1 || true)"

  if [ -n "$version" ]; then
    printf '%s\n' "$version"
    return 0
  fi

  forum="$(curl -fsSL "https://forum.makemkv.com/forum/viewtopic.php?f=3&t=224" || true)"
  version="$(printf '%s\n' "$forum" \
    | grep -Eo 'makemkv-(bin|oss)-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz' \
    | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' \
    | head -n1 || true)"

  if [ -n "$version" ]; then
    printf '%s\n' "$version"
    return 0
  fi

  return 1
}

accept_makemkv_eula() {
  if [ "$ACCEPT_MAKEMKV_EULA" = true ]; then
    return 0
  fi

  cat <<EOF

MakeMKV's binary package has its own license/EULA prompt during build.
This installer can continue only if you accept that MakeMKV license.

EOF

  read -r -p "Do you accept the MakeMKV license/EULA? [y/N] " answer
  case "$answer" in
    y|Y|yes|YES)
      ACCEPT_MAKEMKV_EULA=true
      ;;
    *)
      error "MakeMKV install skipped because the license was not accepted."
      return 1
      ;;
  esac
}

install_makemkv() {
  if [ "$INSTALL_MAKEMKV" != true ]; then
    note "Skipping MakeMKV by request."
    return 0
  fi

  if command -v makemkvcon >/dev/null 2>&1 && [ "$FORCE_MAKEMKV" != true ]; then
    info "MakeMKV (makemkvcon) already exists. Use --force-makemkv to rebuild the latest release."
    return 0
  fi

  ensure_command curl curl

  local version="$MAKEMKV_VERSION"
  if [ -z "$version" ]; then
    info "Resolving latest MakeMKV version from makemkv.com..."
    if ! version="$(latest_makemkv_version)"; then
      error "Could not determine the latest MakeMKV version from makemkv.com."
      exit 1
    fi
  fi

  info "Installing MakeMKV $version from official Linux tarballs..."

  if ! accept_makemkv_eula; then
    return 1
  fi

  local work base_url bin_tar oss_tar sha_file selected_sums jobs
  work="$(mktemp -d /tmp/tkar-makemkv-XXXXXX)"
  base_url="https://www.makemkv.com/download"
  bin_tar="makemkv-bin-${version}.tar.gz"
  oss_tar="makemkv-oss-${version}.tar.gz"
  sha_file="makemkv-sha-${version}.txt"
  selected_sums="makemkv-sha-selected-${version}.txt"
  jobs="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"

  (
    cd "$work"

    curl -fL "${base_url}/${oss_tar}" -o "$oss_tar"
    curl -fL "${base_url}/${bin_tar}" -o "$bin_tar"

    if curl -fL "${base_url}/${sha_file}" -o "$sha_file"; then
      grep -Eo "[a-fA-F0-9]{64}[[:space:]]+makemkv-(bin|oss)-${version}\\.tar\\.gz" "$sha_file" > "$selected_sums" || true
      if [ "$(wc -l < "$selected_sums" | tr -d ' ')" = "2" ]; then
        info "Verifying MakeMKV tarball SHA256 checksums..."
        sha256sum -c "$selected_sums"
      else
        warn "Could not parse both Linux checksums from $sha_file; continuing without checksum verification."
      fi
    else
      warn "Could not download $sha_file; continuing without checksum verification."
    fi

    tar -xzf "$oss_tar"
    tar -xzf "$bin_tar"

    info "Building makemkv-oss..."
    (
      cd "makemkv-oss-${version}"
      ./configure
      make -j"$jobs"
      "${SUDO[@]}" make install
    )

    info "Building makemkv-bin..."
    (
      cd "makemkv-bin-${version}"
      if [ "$ACCEPT_MAKEMKV_EULA" = true ]; then
        set +o pipefail
        yes yes | make -j"$jobs"
        make_status="${PIPESTATUS[1]}"
        set -o pipefail
        if [ "$make_status" -ne 0 ]; then
          exit "$make_status"
        fi
      else
        make -j"$jobs"
      fi
      "${SUDO[@]}" make install
    )
  )

  if command -v makemkvcon >/dev/null 2>&1; then
    info "MakeMKV installed: $(command -v makemkvcon)"
  else
    error "MakeMKV build completed, but makemkvcon was not found in PATH."
    exit 1
  fi

  rm -rf "$work"
}

install_lact() {
  if [ "$INSTALL_LACT" != true ]; then
    note "Skipping LACT by request."
    return 0
  fi

  if systemctl is-active --quiet lactd 2>/dev/null || [ -S /run/lactd.sock ]; then
    info "LACT daemon/socket detected."
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    install_packages curl
  fi

  info "Trying to install LACT from the latest GitHub release..."

  local api_url asset_url tmp_pkg
  api_url="https://api.github.com/repos/ilya-zlobintsev/LACT/releases/latest"

  case "$PKG_MANAGER" in
    apt)
      asset_url="$(curl -fsSL "$api_url" \
        | grep browser_download_url \
        | grep -Ei 'ubuntu|debian' \
        | grep -Ei 'headless|\.deb' \
        | head -n1 \
        | cut -d '"' -f 4 || true)"
      ;;
    dnf|zypper)
      asset_url="$(curl -fsSL "$api_url" \
        | grep browser_download_url \
        | grep -Ei 'fedora|rhel|suse|rpm' \
        | grep -Ei 'headless|\.rpm' \
        | head -n1 \
        | cut -d '"' -f 4 || true)"
      ;;
    pacman)
      warn "Automatic LACT install is not implemented for pacman/Arch."
      return 0
      ;;
  esac

  if [ -z "${asset_url:-}" ]; then
    warn "Could not find a compatible LACT package in the latest release."
    warn "Install LACT manually from https://github.com/ilya-zlobintsev/LACT if you want GPU telemetry."
    return 0
  fi

  info "Found LACT package: $asset_url"
  tmp_pkg="$(mktemp "/tmp/lact.XXXXXX")"
  curl -fL "$asset_url" -o "$tmp_pkg"

  case "$PKG_MANAGER" in
    apt)
      if ! "${SUDO[@]}" dpkg -i "$tmp_pkg"; then
        "${SUDO[@]}" apt-get -f install -y
      fi
      ;;
    dnf)
      "${SUDO[@]}" dnf install -y "$tmp_pkg"
      ;;
    zypper)
      "${SUDO[@]}" zypper --non-interactive install "$tmp_pkg"
      ;;
  esac

  rm -f "$tmp_pkg"

  if command -v systemctl >/dev/null 2>&1; then
    "${SUDO[@]}" systemctl enable --now lactd.service 2>/dev/null || true
  fi

  if systemctl is-active --quiet lactd 2>/dev/null || [ -S /run/lactd.sock ]; then
    info "LACT appears installed and running."
  else
    warn "LACT was installed or attempted, but lactd is not active. GPU telemetry may be disabled."
  fi
}

setup_app_directories() {
  local home_root config_root output_root temp_root log_root
  home_root="$HOME/TKAutoRipper"
  config_root="$home_root/config"
  output_root="$home_root/output"
  temp_root="$home_root/temp"
  log_root="/var/log/TKAutoRipper"

  info "Creating TKAutoRipper directories..."
  mkdir -p "$config_root" "$output_root" "$temp_root"
  "${SUDO[@]}" mkdir -p "$log_root"
  "${SUDO[@]}" chown "$USER":"$(id -gn)" "$log_root" 2>/dev/null || true

  info "Installing default config files into $config_root..."
  for file in config/*; do
    [ -f "$file" ] || continue
    if [ "$(basename "$file")" = "credentials.conf" ]; then
      continue
    fi
    local target="$config_root/$(basename "$file")"
    if [ -e "$target" ]; then
      note "Keeping existing config: $target"
    else
      cp "$file" "$target"
    fi
  done

  if [ ! -e "$config_root/credentials.conf" ] && [ -e "config/credentials.example.conf" ]; then
    info "Creating credentials file: $config_root/credentials.conf"
    cp "config/credentials.example.conf" "$config_root/credentials.conf"
    chmod 600 "$config_root/credentials.conf" 2>/dev/null || true
  fi
}

setup_python_venv() {
  local venv_dir req_file py_cmd
  venv_dir=".venv"
  req_file="installer/requirements_linux.txt"

  if command -v python3 >/dev/null 2>&1; then
    py_cmd="python3"
  elif command -v python >/dev/null 2>&1; then
    py_cmd="python"
  else
    error "Python was not found after dependency installation."
    exit 1
  fi

  if [ -d "$venv_dir" ]; then
    if [ ! -x "$venv_dir/bin/python" ] || ! "$venv_dir/bin/python" -m pip --version >/dev/null 2>&1; then
      warn "Existing virtualenv is broken or from a missing Python version; recreating $venv_dir."
      rm -rf "$venv_dir"
    fi
  fi

  if [ ! -d "$venv_dir" ]; then
    info "Creating Python virtual environment in $venv_dir..."
    "$py_cmd" -m venv "$venv_dir"
  else
    info "Virtualenv $venv_dir already exists; reusing."
  fi

  # shellcheck source=/dev/null
  source "$venv_dir/bin/activate"

  info "Upgrading pip..."
  python -m pip install --upgrade pip

  if [ ! -f "$req_file" ]; then
    error "Requirements file not found: $req_file"
    exit 1
  fi

  info "Installing Python dependencies from $req_file..."
  python -m pip install -r "$req_file"
}

main() {
  install_distro_dependencies
  install_handbrake
  install_intel_qsv_support
  install_makemkv
  install_lact
  setup_app_directories
  setup_python_venv

  cat <<EOF

${GREEN}Installation complete.${NC}

To start TKAutoRipper:

  cd "$(pwd)"
  source .venv/bin/activate
  python3 main.py

Then open:

  https://[::1]:8000

Default auth (change this in ~/TKAutoRipper/config/TKAutoRipper.conf):

  username: admin
  password: admin

EOF
}

main "$@"
