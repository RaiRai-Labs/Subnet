#!/usr/bin/env bash
# Launch the RaiRai miner neuron under PM2 (auto-restart on crash).
#
# Config via env (or pass extra flags straight through):
#   NETUID, SUBTENSOR_NETWORK, WALLET_NAME, WALLET_HOTKEY,
#   AXON_PORT, AXON_EXTERNAL_IP, PM2_NAME
#
# NOTE: the chain rejects 127.0.0.1 — advertise a publicly reachable external IP
# and open the axon port in your firewall.
#
# Example:
#   NETUID=1 SUBTENSOR_NETWORK=finney WALLET_NAME=miner WALLET_HOTKEY=default \
#     AXON_PORT=8091 AXON_EXTERNAL_IP=203.0.113.10 ./scripts/start_miner.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env (if present) so the neuron inherits DATABASE_URL, SH_*, RAIRAI_* etc.
if [[ -f .env ]]; then set -a; source .env; set +a; fi

NAME="${PM2_NAME:-rairai-miner}"

ARGS=()
[[ -n "${NETUID:-}" ]]            && ARGS+=(--netuid "$NETUID")
[[ -n "${SUBTENSOR_NETWORK:-}" ]] && ARGS+=(--subtensor.network "$SUBTENSOR_NETWORK")
[[ -n "${WALLET_NAME:-}" ]]       && ARGS+=(--wallet.name "$WALLET_NAME")
[[ -n "${WALLET_HOTKEY:-}" ]]     && ARGS+=(--wallet.hotkey "$WALLET_HOTKEY")
[[ -n "${AXON_PORT:-}" ]]         && ARGS+=(--axon.port "$AXON_PORT")
[[ -n "${AXON_EXTERNAL_IP:-}" ]]  && ARGS+=(--axon.external_ip "$AXON_EXTERNAL_IP")
ARGS+=("$@")  # passthrough / overrides

command -v pm2 >/dev/null 2>&1 || { echo "pm2 not found — run ./setup.sh first" >&2; exit 1; }
command -v uv  >/dev/null 2>&1 || { echo "uv not found — run ./setup.sh first" >&2; exit 1; }

echo "Starting miner under PM2 as '$NAME' with: ${ARGS[*]:-<defaults>}"
pm2 start uv --name "$NAME" --time --restart-delay 5000 -- \
  run python -m neurons.miner "${ARGS[@]}"
pm2 save
echo "Logs: pm2 logs $NAME   |   Status: pm2 status"
