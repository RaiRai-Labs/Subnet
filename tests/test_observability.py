"""Unit tests for Phase 5 observability helpers."""

import json

from subnet.observability import Alerter, write_heartbeat


def test_heartbeat_roundtrip_adds_timestamp(tmp_path):
    path = tmp_path / "hb.json"
    write_heartbeat(str(path), role="validator", uid=0, step=7)
    data = json.loads(path.read_text())
    assert data["role"] == "validator"
    assert data["uid"] == 0
    assert data["step"] == 7
    assert isinstance(data["ts"], (int, float))  # auto-added


def test_heartbeat_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "deeper" / "hb.json"
    write_heartbeat(str(path), role="miner")
    assert path.exists()


def test_heartbeat_explicit_ts_preserved(tmp_path):
    path = tmp_path / "hb.json"
    write_heartbeat(str(path), ts=123.0)
    assert json.loads(path.read_text())["ts"] == 123.0


def test_alerter_disabled_without_webhook():
    a = Alerter(webhook_url=None)
    assert a.enabled is False
    # send() must be a safe no-op (no network) and report non-delivery.
    assert a.send("hello") is False


def test_alerter_enabled_with_webhook():
    a = Alerter(webhook_url="https://example.com/webhook")
    assert a.enabled is True
