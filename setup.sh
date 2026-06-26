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

# pm2-logrotate keeps neuron logs from filling a small VPS disk (caps + rotates).
if ! pm2 list >/dev/null 2>&1 || ! pm2 describe pm2-logrotate >/dev/null 2>&1; then
  log "Installing pm2-logrotate (10MB cap, keep 7, daily rotate)..."
  pm2 install pm2-logrotate >/dev/null 2>&1 || log "pm2-logrotate install skipped (non-fatal)."
  pm2 set pm2-logrotate:max_size 10M >/dev/null 2>&1 || true
  pm2 set pm2-logrotate:retain 7 >/dev/null 2>&1 || true
  pm2 set pm2-logrotate:rotateInterval '0 0 * * *' >/dev/null 2>&1 || true
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

# --- Firewall: open the miner axon port (opt in with RAIRAI_OPEN_FIREWALL=1) ---
# Miners must be reachable from the chain; a UFW-default VPS blocks the axon port.
if [[ "${RAIRAI_OPEN_FIREWALL:-0}" == "1" ]] && command -v ufw >/dev/null 2>&1; then
  PORT="${AXON_PORT:-8091}"
  log "Opening axon port ${PORT}/tcp in UFW..."
  sudo ufw allow "${PORT}/tcp" || log "ufw rule skipped (non-fatal)."
fi

log "Done. Next:"
log "  1) cp .env.example .env   # then edit (NETUID, WALLET_*, DATABASE_URL, SH_*)"
log "  2) uv run python scripts/preflight.py --role validator   # validate config"
log "  3) pm2 start ecosystem.config.js --only rairai-validator,rairai-updater"
log "     (or ./scripts/start_validator.sh / start_miner.sh)"
log "  4) pm2 startup && pm2 save   # resurrect neurons on reboot"
