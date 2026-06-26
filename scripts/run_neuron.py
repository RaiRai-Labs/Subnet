#!/usr/bin/env python3
"""Auto-update / self-heal runner for a PM2-managed neuron (Phase 5).

Polls the git remote on a fixed interval; when the tracked branch has advanced,
it hard-resets to the remote, reinstalls dependencies (``uv sync``), and restarts
the PM2 process. PM2 already restarts the neuron on crash — this layer adds code
self-update plus an optional periodic safety restart.

Run it under PM2 too so it survives reboots:

    pm2 start scripts/run_neuron.py --name rairai-updater --interpreter python3 \\
      -- --pm2-name rairai-validator --branch main

WARNING: uses ``git reset --hard`` on update, discarding local working-tree
changes on the deploy box. Keep local edits elsewhere.
"""

import argparse
import subprocess
import sys
import time


def _run(cmd: list[str]) -> str:
    return subprocess.run(
        cmd, check=True, text=True, capture_output=True
    ).stdout.strip()


def _rev(ref: str) -> str:
    return _run(["git", "rev-parse", ref])


def update_once(branch: str, pm2_name: str, reinstall: bool) -> bool:
    """Fetch the branch; if it advanced, reset + reinstall + restart. Returns True if updated."""
    _run(["git", "fetch", "origin", branch])
    local = _rev("HEAD")
    remote = _rev(f"origin/{branch}")
    if local == remote:
        return False

    print(
        f"[updater] {branch} advanced {local[:8]} -> {remote[:8]}; updating...",
        flush=True,
    )
    _run(["git", "reset", "--hard", f"origin/{branch}"])
    if reinstall:
        _run(["uv", "sync"])
    _run(["pm2", "restart", pm2_name])
    print(f"[updater] restarted '{pm2_name}' at {remote[:8]}", flush=True)
    return True


def main() -> None:
    p = argparse.ArgumentParser(description="Auto-update / self-heal runner.")
    p.add_argument("--pm2-name", required=True, help="PM2 process name to restart on update.")
    p.add_argument("--branch", default="main", help="Git branch to track (default: main).")
    p.add_argument("--interval", type=int, default=300, help="Seconds between checks (default: 300).")
    p.add_argument("--no-reinstall", action="store_true", help="Skip 'uv sync' on update.")
    p.add_argument(
        "--restart-every",
        type=int,
        default=0,
        help="Also restart the neuron every N seconds even without updates (0 = never).",
    )
    args = p.parse_args()

    print(
        f"[updater] watching origin/{args.branch} every {args.interval}s "
        f"for '{args.pm2_name}'",
        flush=True,
    )
    last_restart = time.monotonic()
    while True:
        try:
            update_once(args.branch, args.pm2_name, not args.no_reinstall)
            if args.restart_every and (time.monotonic() - last_restart) >= args.restart_every:
                subprocess.run(["pm2", "restart", args.pm2_name], check=False)
                last_restart = time.monotonic()
        except subprocess.CalledProcessError as exc:
            print(
                f"[updater] command failed: {' '.join(exc.cmd)}\n{exc.stderr}",
                file=sys.stderr,
                flush=True,
            )
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
