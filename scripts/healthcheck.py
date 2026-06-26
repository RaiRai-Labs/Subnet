#!/usr/bin/env python3
"""Heartbeat staleness monitor (Phase 5 ops).

The neuron writes a JSON heartbeat (``RAIRAI_HEARTBEAT_FILE``) every loop. This
checks that file is fresh; when the timestamp goes stale — or the file is missing
— the neuron has hung or died even though PM2 still shows it "online". Posts a
one-line alert to the webhook and exits non-zero so a cron/monitor can react.

Cron example (every minute):

    * * * * * cd /opt/rairai_subnet && \\
      RAIRAI_HEARTBEAT_FILE=/var/run/rairai/validator.json \\
      RAIRAI_ALERT_WEBHOOK=https://discord.com/api/webhooks/... \\
      python3 scripts/healthcheck.py --max-age 90 >> /var/log/rairai-health.log 2>&1

Standalone stdlib (no bittensor import) so it starts fast and stays cheap.
Exit code: 0 = fresh, 1 = stale/missing, 2 = usage error.
"""

import argparse
import json
import os
import socket
import sys
import time
import urllib.request


def post_alert(webhook: str, message: str, timeout: float = 10.0) -> bool:
    """Best-effort webhook post (Discord + Slack compatible). Never raises."""
    if not webhook:
        return False
    payload = json.dumps({"content": message, "text": message}).encode()
    try:
        req = urllib.request.Request(
            webhook,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception as exc:  # noqa: BLE001 - alerting must never crash the monitor
        print(f"[healthcheck] webhook post failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description="Alert if a neuron heartbeat is stale.")
    p.add_argument(
        "--file",
        default=os.getenv("RAIRAI_HEARTBEAT_FILE"),
        help="Heartbeat JSON path (default: $RAIRAI_HEARTBEAT_FILE).",
    )
    p.add_argument(
        "--max-age",
        type=float,
        default=90.0,
        help="Max heartbeat age in seconds before it's stale (default: 90).",
    )
    p.add_argument(
        "--webhook",
        default=os.getenv("RAIRAI_ALERT_WEBHOOK"),
        help="Alert webhook (default: $RAIRAI_ALERT_WEBHOOK).",
    )
    args = p.parse_args()

    if not args.file:
        print("[healthcheck] no heartbeat file given (--file or $RAIRAI_HEARTBEAT_FILE)", file=sys.stderr)
        return 2

    host = socket.gethostname()
    tag = f"[{host}] heartbeat {args.file}"

    if not os.path.exists(args.file):
        msg = f"{tag}: MISSING — neuron never started or crashed before first write."
        print(msg, file=sys.stderr)
        post_alert(args.webhook, f"🔴 {msg}")
        return 1

    try:
        data = json.loads(open(args.file).read())
        ts = float(data.get("ts", 0))
    except Exception as exc:  # noqa: BLE001 - treat unreadable as stale
        msg = f"{tag}: UNREADABLE ({exc})."
        print(msg, file=sys.stderr)
        post_alert(args.webhook, f"🔴 {msg}")
        return 1

    age = time.time() - ts
    role = data.get("role", "neuron")
    uid = data.get("uid", "?")
    if age > args.max_age:
        msg = (
            f"{tag}: STALE — {role} uid={uid} last beat {age:.0f}s ago "
            f"(> {args.max_age:.0f}s). Likely hung/dead."
        )
        print(msg, file=sys.stderr)
        post_alert(args.webhook, f"🔴 {msg}")
        return 1

    print(f"{tag}: ok — {role} uid={uid} age={age:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
