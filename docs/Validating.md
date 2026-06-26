# Running a RaiRai Validator

A validator poses yield-prediction tasks, scores miners' answers, and sets
consensus weights on chain. This guide covers a production run managed by PM2.

For a local-chain test setup (start subtensor, create + activate the subnet,
register), see **[localnet.md](localnet.md)**. For offline development with no
chain or wallet, just run `uv run python -m neurons.validator --mock`.

## 1. Prerequisites

- A registered validator hotkey on the target subnet (with enough stake to set
  weights — i.e. holding a validator permit).
- A reachable **subtensor** RPC endpoint (`finney`, a custom network, or local).
- See **[../min_compute.yml](../min_compute.yml)** for hardware baselines.

## 2. Install

```bash
git clone <repo> && cd rairai_subnet
./setup.sh                      # build tools, Node/PM2, uv, deps, TCP tuning
cp .env.example .env            # then edit (see below)
```

## 3. Configure `.env`

The start scripts load `.env` into the neuron's environment. Set:

- `DATABASE_URL` — async Postgres URL (rolling rank/challenge history).
- `RAIRAI_LOG_LEVEL` — `info` (default), `debug`, or `trace`.
- `RAIRAI_ALERT_WEBHOOK` — optional Discord/Slack webhook for start/crash alerts.
- `RAIRAI_HEARTBEAT_FILE` — optional JSON status file for monitoring.
- `SH_DEPLOYMENT` / `SH_CLIENT_ID` / `SH_CLIENT_SECRET` — optional, to pull live
  Sentinel-2 satellite indices instead of the offline stub.

## 4. Preflight (validate before launch)

Catch missing wallet, bad `DATABASE_URL`, mis-set creds, etc. *before* starting:

```bash
uv run python scripts/preflight.py --role validator
```

It exits non-zero on any hard error. Fix those, then start.

## 5. Start under PM2

Single-command bring-up via the ecosystem file (reads `.env`) — starts the
validator **and** the auto-updater together:

```bash
pm2 start ecosystem.config.js --only rairai-validator,rairai-updater
```

Or use the script (env- or flag-driven):

```bash
NETUID=1 SUBTENSOR_NETWORK=finney WALLET_NAME=validator WALLET_HOTKEY=default \
  ./scripts/start_validator.sh
# or pass flags straight through:
./scripts/start_validator.sh --netuid 1 --subtensor.network finney \
  --wallet.name validator --wallet.hotkey default
```

PM2 keeps the neuron alive across crashes (5s restart backoff). Persist the
process list so it resurrects on reboot:

```bash
pm2 startup    # run the command it prints
pm2 save
```

Useful knobs (passed through to the neuron):
`--neuron.forward_interval`, `--neuron.epoch_length`, `--neuron.rank_window`,
`--neuron.persist_ranks`, `--logging.logging_dir <dir> --logging.record_log`.

## 6. Keep it up to date (auto-update / self-heal)

If you started with the ecosystem file above, the `rairai-updater` app is
already running. To run it standalone (e.g. with the start script):

```bash
pm2 start scripts/run_neuron.py --name rairai-updater --interpreter python3 \
  -- --pm2-name rairai-validator --branch main --interval 300
pm2 save
```

> It hard-resets to `origin/<branch>` on update — keep local edits elsewhere.

## 7. Observe

```bash
pm2 status                       # process health
pm2 logs rairai-validator        # live logs
cat "$RAIRAI_HEARTBEAT_FILE"      # {role, uid, step, scores, ts}
```

A stale `ts` in the heartbeat file means the neuron hung or died. Wire the
heartbeat monitor into cron to get alerted automatically:

```bash
# every minute; alerts RAIRAI_ALERT_WEBHOOK if the last beat is > 90s old
* * * * * cd /opt/rairai_subnet && RAIRAI_HEARTBEAT_FILE=/var/run/rairai/validator.json \
  RAIRAI_ALERT_WEBHOOK=https://... python3 scripts/healthcheck.py --max-age 90
```

Start/crash events are also pushed to `RAIRAI_ALERT_WEBHOOK` when set.

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pm2 not found` | run `./setup.sh` |
| Not registered / no permit | register the hotkey; ensure enough stake to set weights |
| `set_weights` skipped | within the chain's `weights_rate_limit` window — expected |
| No DB / `DATABASE_URL` errors | set `DATABASE_URL`; start Postgres (`./run.sh` brings one up) |
| Frequent restarts | `pm2 logs` for the traceback; check wallet/endpoint/firewall |
