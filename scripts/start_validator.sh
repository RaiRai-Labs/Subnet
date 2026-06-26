#!/usr/bin/env bash
# Launch the RaiRai validator neuron under PM2 (auto-restart on crash).
#
# Config via env (or pass extra flags straight through to the neuron):
#   NETUID, SUBTENSOR_NETWORK, WALLET_NAME, WALLET_HOTKEY, PM2_NAME
#
# Examples:
#   NETUID=1 SUBTENSOR_NETWORK=finney WALLET_NAME=validator WALLET_HOTKEY=default \
#     ./scripts/start_validator.sh
#   ./scripts/start_validator.sh --netuid 1 --subtensor.network finney \
#     --wallet.name validator --wallet.hotkey default
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env (if present) so the neuron inherits DATABASE_URL, SH_*, RAIRAI_* etc.
if [[ -f .env ]]; then set -a; source .env; set +a; fi

NAME="${PM2_NAME:-rairai-validator}"

ARGS=()
[[ -n "${NETUID:-}" ]]            && ARGS+=(--netuid "$NETUID")
[[ -n "${SUBTENSOR_NETWORK:-}" ]] && ARGS+=(--subtensor.network "$SUBTENSOR_NETWORK")
[[ -n "${WALLET_NAME:-}" ]]       && ARGS+=(--wallet.name "$WALLET_NAME")
[[ -n "${WALLET_HOTKEY:-}" ]]     && ARGS+=(--wallet.hotkey "$WALLET_HOTKEY")
ARGS+=("$@")  # passthrough / overrides win (argparse takes the last value)

command -v pm2 >/dev/null 2>&1 || { echo "pm2 not found — run ./setup.sh first" >&2; exit 1; }
command -v uv  >/dev/null 2>&1 || { echo "uv not found — run ./setup.sh first" >&2; exit 1; }

echo "Starting validator under PM2 as '$NAME' with: ${ARGS[*]:-<defaults>}"
# --time stamps each log line; --restart-delay backs off 5s between crash restarts.
pm2 start uv --name "$NAME" --time --restart-delay 5000 -- \
  run python -m neurons.validator "${ARGS[@]}"
pm2 save
echo "Logs: pm2 logs $NAME   |   Status: pm2 status"
