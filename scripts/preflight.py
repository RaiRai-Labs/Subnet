#!/usr/bin/env python3
"""Preflight config doctor (Phase 5 ops).

Validates a box's configuration *before* you start a neuron, so the common
deploy-killers surface in seconds instead of after a botched registration or a
silent no-op run. Reads ``.env`` (if present) plus the real environment.

    uv run python scripts/preflight.py --role validator
    uv run python scripts/preflight.py --role miner

Exit code: 0 if no errors (warnings are fine), 1 if any hard error is found.
Stdlib only — safe to run before ``uv sync`` finishes.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

GREEN, YELLOW, RED, DIM, RESET = (
    "\033[1;32m", "\033[1;33m", "\033[1;31m", "\033[2m", "\033[0m"
)

_errors = 0
_warnings = 0


def ok(msg: str) -> None:
    print(f"{GREEN}  ok {RESET} {msg}")


def warn(msg: str) -> None:
    global _warnings
    _warnings += 1
    print(f"{YELLOW} warn{RESET} {msg}")


def err(msg: str) -> None:
    global _errors
    _errors += 1
    print(f"{RED} err {RESET} {msg}")


def load_env() -> dict:
    """Merge .env (if present) with the process environment (env wins)."""
    env = {}
    dotenv = ROOT / ".env"
    if dotenv.exists():
        for raw in dotenv.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            env[key.strip()] = val
    else:
        warn(".env not found — relying on the process environment only.")
    env.update(os.environ)
    return env


def check_tooling() -> None:
    from shutil import which

    for tool in ("uv", "pm2"):
        if which(tool):
            ok(f"{tool} on PATH")
        else:
            err(f"{tool} not found on PATH — run ./setup.sh")
    if which("git"):
        ok("git on PATH")
    else:
        warn("git not found — the auto-updater (run_neuron.py) needs it")


def check_wallet(env: dict) -> None:
    name = env.get("WALLET_NAME")
    hotkey = env.get("WALLET_HOTKEY")
    if not name or not hotkey:
        err("WALLET_NAME / WALLET_HOTKEY unset — required for a live (non-mock) run")
        return
    base = Path(env.get("BT_WALLET_PATH", Path.home() / ".bittensor" / "wallets"))
    hk = base / name / "hotkeys" / hotkey
    ck = base / name / "coldkeypub.txt"
    if hk.exists():
        ok(f"hotkey present: {hk}")
    else:
        err(f"hotkey not found: {hk} (create/regen the wallet on this box)")
    if not ck.exists():
        warn(f"coldkeypub not found: {ck}")


def check_chain(env: dict) -> None:
    if not env.get("NETUID"):
        err("NETUID unset — the neuron will not know which subnet to join")
    else:
        ok(f"NETUID={env['NETUID']}")
    net = env.get("SUBTENSOR_NETWORK")
    if net:
        ok(f"SUBTENSOR_NETWORK={net}")
    else:
        warn("SUBTENSOR_NETWORK unset — defaults to the bittensor library default")


def check_axon(env: dict) -> None:
    ip = env.get("AXON_EXTERNAL_IP", "")
    port = env.get("AXON_PORT", "")
    if not ip:
        err("AXON_EXTERNAL_IP unset — the chain rejects a miner that can't be reached")
    elif ip.startswith("127.") or ip in ("localhost", "0.0.0.0"):
        err(f"AXON_EXTERNAL_IP={ip} is not publicly reachable — advertise your VPS IP")
    else:
        ok(f"AXON_EXTERNAL_IP={ip}")
    if not port:
        warn("AXON_PORT unset — defaults to 8091; make sure the firewall allows it")
    else:
        ok(f"AXON_PORT={port} (confirm it's open: sudo ufw status)")


def check_database(env: dict) -> None:
    url = env.get("DATABASE_URL")
    if not url:
        warn("DATABASE_URL unset — rolling-rank persistence is off (in-memory only)")
        return
    if "+asyncpg" not in url:
        err(f"DATABASE_URL must use the async driver (postgresql+asyncpg://...): {url[:40]}...")
    else:
        host = urlparse(url.replace("postgresql+asyncpg", "postgresql")).hostname
        ok(f"DATABASE_URL set (async driver, host={host})")


def check_backend_url(env: dict) -> None:
    url = env.get("BACKEND_URL", "").strip()
    if not url:
        err(
            "BACKEND_URL unset — the validator will fall back to SYNTHETIC challenges "
            "(no real Thai farm data). Set BACKEND_URL to the farmer backend URL."
        )
        return
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        err(f"BACKEND_URL does not look like a valid URL: {url[:50]}")
        return
    ok(f"BACKEND_URL={url}")


def check_satellite(env: dict) -> None:
    cid, secret = env.get("SH_CLIENT_ID"), env.get("SH_CLIENT_SECRET")
    if not cid and not secret:
        ok("satellite: using the offline stub (no SH_* creds) — fine for launch")
        return
    if bool(cid) != bool(secret):
        err("SH_CLIENT_ID / SH_CLIENT_SECRET: set both or neither")
        return
    dep = env.get("SH_DEPLOYMENT", "cdse")
    if dep not in ("cdse", "commercial"):
        warn(f"SH_DEPLOYMENT={dep} unrecognized (expected cdse|commercial)")
    else:
        ok(f"satellite: live Sentinel Hub creds present (deployment={dep})")


def check_observability(env: dict) -> None:
    hb = env.get("RAIRAI_HEARTBEAT_FILE")
    if hb:
        parent = Path(hb).parent
        if parent.exists() and os.access(parent, os.W_OK):
            ok(f"heartbeat dir writable: {parent}")
        else:
            warn(f"heartbeat dir not writable yet: {parent} (mkdir/chown before launch)")
    wh = env.get("RAIRAI_ALERT_WEBHOOK")
    if wh:
        if urlparse(wh).scheme in ("http", "https"):
            ok("alert webhook configured")
        else:
            err(f"RAIRAI_ALERT_WEBHOOK is not a valid URL: {wh[:30]}...")
    else:
        warn("RAIRAI_ALERT_WEBHOOK unset — no start/crash alerts")


def main() -> None:
    p = argparse.ArgumentParser(description="Validate a box before launching a neuron.")
    p.add_argument("--role", choices=("validator", "miner"), default="validator")
    p.add_argument(
        "--skip-wallet",
        action="store_true",
        help="Skip wallet + backend-URL checks (use for --mock / offline smoke tests).",
    )
    args = p.parse_args()

    print(f"{DIM}RaiRai preflight — role={args.role}, root={ROOT}{RESET}\n")
    env = load_env()

    check_tooling()
    check_chain(env)
    if not args.skip_wallet:
        check_wallet(env)
    if args.role == "miner":
        check_axon(env)
    else:
        check_database(env)
        check_satellite(env)
        if not args.skip_wallet:
            check_backend_url(env)
    check_observability(env)

    print()
    if _errors:
        print(f"{RED}FAIL{RESET}: {_errors} error(s), {_warnings} warning(s). Fix errors before launch.")
        sys.exit(1)
    print(f"{GREEN}PASS{RESET}: 0 errors, {_warnings} warning(s). Safe to start.")


if __name__ == "__main__":
    main()
