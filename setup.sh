#!/usr/bin/env bash
# RaiRai Subnet — operator setup: install everything needed to run a neuron.
#
# Installs build tools, Node.js + PM2 (process manager), uv (Python runtime),
# applies light TCP tuning, and syncs Python dependencies.
#
# Usage:   ./setup.sh
# Target:  Ubuntu 22.04 / 24.04. Re-runnable (skips what is already present).
set -euo pipefail
cd "$(dirname "$0")"

log() { printf '\033[1;32m[setup]\033[0m %s\n' "$*"; }

# --- System packages ---
if command -v apt-get >/dev/null 2>&1; then
  log "Installing system packages (build-essential, curl, git, jq)..."
  sudo apt-get update -y
  sudo apt-get install -y build-essential curl git jq ca-certificates
else
  log "apt-get not found — install build tools / curl / git manually for your OS."
fi

# --- Node.js + PM2 ---
if ! command -v node >/dev/null 2>&1; then
  log "Installing Node.js LTS (NodeSource)..."
  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
if ! command -v pm2 >/dev/null 2>&1; then
  log "Installing PM2..."
  sudo npm install -g pm2
fi

# --- uv (Python package/runtime manager) ---
if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# --- Python dependencies ---
log "Syncing Python dependencies (uv sync)..."
uv sync

# --- Light TCP tuning (helps axon/dendrite throughput); opt out with RAIRAI_TCP_TUNE=0 ---
if [[ "${RAIRAI_TCP_TUNE:-1}" == "1" ]] && command -v sudo >/dev/null 2>&1; then
  log "Applying TCP tuning (/etc/sysctl.d/99-rairai.conf)..."
  sudo tee /etc/sysctl.d/99-rairai.conf >/dev/null <<'SYSCTL'
net.core.somaxconn = 4096
net.core.netdev_max_backlog = 16384
net.ipv4.tcp_tw_reuse = 1
SYSCTL
  sudo sysctl --load=/etc/sysctl.d/99-rairai.conf || log "sysctl reload skipped (non-fatal)."
fi

log "Done. Next:"
log "  1) cp .env.example .env   # then edit (DATABASE_URL, SH_* if using satellite)"
log "  2) ./scripts/start_validator.sh   OR   ./scripts/start_miner.sh"
log "  3) pm2 startup && pm2 save   # to resurrect neurons on reboot"
