"""Observability helpers: logging, alerts, metrics (Phase 5).

Three lightweight, dependency-free pieces operators wire into the neurons:

- `configure_logging()` — set bittensor log verbosity from arg/env.
- `Alerter`             — post alerts to a webhook (Discord/Slack-compatible);
                          a no-op when no webhook is configured.
- `write_heartbeat()`   — atomically write a JSON status file a monitor can scrape
                          (lightweight metrics export).

All transport is stdlib (`urllib`). Alerting and heartbeat failures are logged,
never raised, so observability can never crash the run loop.
"""

import json
import os
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

import bittensor as bt


def configure_logging(level: Optional[str] = None) -> None:
    """Set bittensor log verbosity from ``level`` or ``RAIRAI_LOG_LEVEL`` env.

    Accepts ``info`` (default), ``debug``, or ``trace``. For persistent log
    files, pass bittensor's own flags to the neuron, e.g.
    ``--logging.logging_dir /var/log/rairai --logging.record_log``.
    """
    level = (level or os.getenv("RAIRAI_LOG_LEVEL") or "info").lower()
    if level == "trace":
        bt.logging.enable_trace()
    elif level == "debug":
        bt.logging.enable_debug()
    else:
        bt.logging.enable_info()


class Alerter:
    """Posts alerts to a webhook (Discord/Slack-compatible). No-op if unset."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        prefix: str = "RaiRai",
        timeout: float = 10.0,
    ) -> None:
        self.webhook_url = webhook_url or os.getenv("RAIRAI_ALERT_WEBHOOK")
        self.prefix = prefix
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    def send(self, message: str, level: str = "info") -> bool:
        """Best-effort alert. Returns True if delivered; never raises."""
        text = f"[{self.prefix}] {level.upper()}: {message}"
        if not self.webhook_url:
            bt.logging.debug(f"(alert suppressed, no webhook) {text}")
            return False
        # Discord expects {"content": ...}; Slack expects {"text": ...}.
        payload = json.dumps({"content": text, "text": text}).encode()
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout):
                return True
        except Exception as exc:  # noqa: BLE001 - alerting must never crash the caller
            bt.logging.warning(f"alert webhook failed: {exc}")
            return False


def write_heartbeat(path: str, **fields) -> None:
    """Atomically write a JSON status file for external monitoring.

    A monotonically-updated ``ts`` (epoch seconds) is added automatically, so a
    monitor can alert when the file goes stale (neuron hung / died).
    """
    fields.setdefault("ts", time.time())
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            json.dump(fields, handle)
        os.replace(tmp, target)  # atomic on POSIX
    except Exception as exc:  # noqa: BLE001 - metrics must never crash the run loop
        bt.logging.warning(f"heartbeat write failed: {exc}")
