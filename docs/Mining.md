# Running a RaiRai Miner

A miner serves a `YieldPredictionSynapse` axon and answers validators with an
expected crop yield + confidence. The shipped baseline scales mean NDVI into a
plausible yield — replace `Miner.predict()` in
[`neurons/miner.py`](../neurons/miner.py) with your own model to compete.

For a local-chain test setup, see **[localnet.md](localnet.md)**.

## 1. Prerequisites

- A registered miner hotkey on the target subnet.
- A reachable **subtensor** RPC endpoint.
- A **public, reachable axon port** — the chain rejects `127.0.0.1`, so advertise
  your real external IP and open the port in your firewall/security group.
- See **[../min_compute.yml](../min_compute.yml)** for hardware baselines.

## 2. Install

```bash
git clone <repo> && cd rairai_subnet
./setup.sh
cp .env.example .env            # optional: RAIRAI_* observability vars
```

## 3. Preflight (validate before launch)

Confirm wallet, axon IP/port, and creds are sane before you register/start:

```bash
uv run python scripts/preflight.py --role miner
```

It **errors** if `AXON_EXTERNAL_IP` is unset or a loopback address — the #1
reason miners get no queries.

## 4. Start under PM2

Set the launch keys in `.env` (`NETUID`, `WALLET_*`, `AXON_PORT`,
`AXON_EXTERNAL_IP`, `UPDATER_PM2_NAME=rairai-miner`), then bring up the miner and
its auto-updater together:

```bash
pm2 start ecosystem.config.js --only rairai-miner,rairai-updater
```

Or use the script directly:

```bash
NETUID=1 SUBTENSOR_NETWORK=finney WALLET_NAME=miner WALLET_HOTKEY=default \
  AXON_PORT=8091 AXON_EXTERNAL_IP=<your.public.ip> \
  ./scripts/start_miner.sh
```

Persist for reboot:

```bash
pm2 startup    # run the command it prints
pm2 save
```

## 5. Keep it up to date

The ecosystem bring-up already runs `rairai-updater` (set
`UPDATER_PM2_NAME=rairai-miner` in `.env`). Standalone equivalent:

```bash
pm2 start scripts/run_neuron.py --name rairai-updater --interpreter python3 \
  -- --pm2-name rairai-miner --branch main --interval 300
pm2 save
```

## 6. Observe

```bash
pm2 status
pm2 logs rairai-miner            # look for "Predicted <yield> for <crop>"
cat "$RAIRAI_HEARTBEAT_FILE"      # {role, uid, step, ts}

# auto-alert if the miner heartbeat goes stale (cron, every minute):
* * * * * cd /opt/rairai_subnet && RAIRAI_HEARTBEAT_FILE=/var/run/rairai/miner.json \
  RAIRAI_ALERT_WEBHOOK=https://... python3 scripts/healthcheck.py --max-age 90
```

## 6. Verify you're being served

After starting, confirm the axon is serving on chain (validators only query
serving axons):

```bash
# from a python shell with your wallet/endpoint configured
# mg = subtensor.metagraph(netuid); mg.axons[your_uid].is_serving  -> True
```

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Chain rejects axon / `127.0.0.1` | set `AXON_EXTERNAL_IP` to your public IP; open the port |
| No queries arriving | not registered, axon not serving, or port unreachable (check firewall) |
| `pm2 not found` | run `./setup.sh` |
| Blacklisted callers | expected — unrecognized/low-stake hotkeys are rejected by design |
| Frequent restarts | `pm2 logs rairai-miner` for the traceback |
