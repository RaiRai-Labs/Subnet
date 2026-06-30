"""Unit tests for the Phase 5 heartbeat staleness monitor."""

import importlib.util
import json
import time
from pathlib import Path

import pytest

_HC_PATH = Path(__file__).resolve().parent.parent / "scripts" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("healthcheck", _HC_PATH)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)


def _write_hb(path, age_seconds):
    path.write_text(json.dumps({"role": "validator", "uid": 0, "ts": time.time() - age_seconds}))


def _run(monkeypatch, *argv):
    # No webhook in env → post_alert is a no-op, so main() never hits the network.
    monkeypatch.delenv("RAIRAI_ALERT_WEBHOOK", raising=False)
    monkeypatch.delenv("RAIRAI_HEARTBEAT_FILE", raising=False)
    monkeypatch.setattr(healthcheck.sys, "argv", ["healthcheck.py", *argv])
    return healthcheck.main()


def test_post_alert_noop_without_webhook():
    assert healthcheck.post_alert("", "msg") is False
    assert healthcheck.post_alert(None, "msg") is False


def test_fresh_heartbeat_passes(monkeypatch, tmp_path):
    hb = tmp_path / "hb.json"
    _write_hb(hb, age_seconds=5)
    assert _run(monkeypatch, "--file", str(hb), "--max-age", "90") == 0


def test_stale_heartbeat_fails(monkeypatch, tmp_path):
    hb = tmp_path / "hb.json"
    _write_hb(hb, age_seconds=300)
    assert _run(monkeypatch, "--file", str(hb), "--max-age", "90") == 1


def test_missing_heartbeat_fails(monkeypatch, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    assert _run(monkeypatch, "--file", str(missing), "--max-age", "90") == 1


def test_no_file_argument_is_usage_error(monkeypatch):
    assert _run(monkeypatch, "--max-age", "90") == 2
