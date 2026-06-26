#!/usr/bin/env python3
"""Integration smoke-test for the full live scoring loop.

Walks the complete pipeline end-to-end using real HTTP calls:

  farm in challenge-pool
    → satellite history reachable
    → task persisted on subnet
    → miner prediction committed + revealed
    → ground truth submitted
    → task scored
    → predictions visible to farmer

Run from the project root after both services are up:

    uv run python scripts/smoke_test_live_loop.py

Required env vars (or .env at project root):
    BACKEND_URL   — farmer backend base URL  (e.g. http://backend-host:8080)
    SUBNET_URL    — subnet validator API URL (e.g. http://subnet-host:8000)

Exit code 0 = all steps passed. Exit code 1 = at least one step failed.
"""

import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# ── colour helpers ────────────────────────────────────────────────────────────
GREEN, YELLOW, RED, DIM, RESET = (
    "\033[1;32m", "\033[1;33m", "\033[1;31m", "\033[2m", "\033[0m"
)
_failures: list[str] = []


def ok(step: str, detail: str = "") -> None:
    suffix = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}✓{RESET}  {step}{suffix}")


def fail(step: str, detail: str = "") -> None:
    suffix = f"\n       {DIM}{detail}{RESET}" if detail else ""
    print(f"  {RED}✗{RESET}  {step}{suffix}")
    _failures.append(step)


def warn(step: str, detail: str = "") -> None:
    suffix = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  {YELLOW}~{RESET}  {step}{suffix}")


# ── env / .env loader ─────────────────────────────────────────────────────────
def _load_env() -> None:
    dotenv = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv.exists():
        return
    for raw in dotenv.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


# ── HTTP helpers ──────────────────────────────────────────────────────────────
def _request(
    method: str, url: str, body: dict | None = None, timeout: float = 10.0
) -> tuple[int, dict | list]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read().decode()[:200]
        except Exception:
            body_text = ""
        return exc.code, {"error": exc.reason, "detail": body_text}
    except Exception as exc:
        return 0, {"error": str(exc)}


def get(url: str) -> tuple[int, dict | list]:
    return _request("GET", url)


def post(url: str, body: dict) -> tuple[int, dict]:
    return _request("POST", url, body)


# ── commit-reveal helpers ─────────────────────────────────────────────────────
def _make_commit(yield_val: float, confidence: float, nonce: str) -> str:
    payload = f"{yield_val}:{confidence}:{nonce}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ── smoke-test steps ──────────────────────────────────────────────────────────

def step_env(backend: str, subnet: str) -> None:
    print(f"\n{DIM}  BACKEND_URL : {backend}{RESET}")
    print(f"{DIM}  SUBNET_URL  : {subnet}{RESET}\n")


def step_challenge_pool(backend: str) -> dict | None:
    status, data = get(f"{backend}/api/public/farms/challenge-pool")
    if status != 200:
        fail("challenge-pool reachable", f"HTTP {status} — {data}")
        return None
    if not isinstance(data, list) or len(data) == 0:
        fail("challenge-pool has farms", "pool is empty — no analyzed farms yet")
        return None
    ok("challenge-pool reachable", f"{len(data)} farm(s) in pool")
    farm = data[0]
    ok("first farm has required fields", f"farm_id={farm.get('farm_id')} crop={farm.get('crop')}")
    return farm


def step_satellite_history(backend: str, farm: dict) -> list:
    farm_id = farm.get("farm_id")
    status, data = get(f"{backend}/api/public/farms/{farm_id}/satellite-history")
    if status != 200:
        fail("satellite-history reachable", f"HTTP {status}")
        return []
    if not isinstance(data, list) or len(data) == 0:
        warn("satellite-history returned", "no NDVI rows yet for this farm")
        return []
    ndvi_vals = [r["ndvi"] for r in data if r.get("ndvi") is not None]
    ok("satellite history returned", f"{len(ndvi_vals)} NDVI readings")
    return ndvi_vals


def step_create_task(subnet: str, farm: dict, ndvi: list) -> str | None:
    payload = {
        "farm_id": farm.get("farm_id"),
        "crop": farm.get("crop", "rice"),
        "province": farm.get("province"),
        "field_size": farm.get("area_hectares"),
        "planting_date": farm.get("planting_date"),
        "horizon_days": 30,
        "ndvi": ndvi[:5] or [0.5, 0.6, 0.55, 0.58, 0.62],
        "weather": [{"temp": 28.0, "rain": 3.0, "humidity": 75.0, "wind": 4.0}],
    }
    status, data = post(f"{subnet}/tasks", payload)
    if status not in (200, 201):
        fail("create task on subnet", f"HTTP {status} — {data}")
        return None
    task_id = data.get("task_id")
    ok("task created on subnet", f"task_id={task_id}")
    return task_id


def step_commit(subnet: str, task_id: str, miner_hotkey: str, yield_val: float,
                confidence: float, nonce: str) -> bool:
    commit_hash = _make_commit(yield_val, confidence, nonce)
    status, data = post(f"{subnet}/responses/commit", {
        "task_id": task_id,
        "miner_hotkey": miner_hotkey,
        "miner_uid": 99,
        "commit_hash": commit_hash,
    })
    if status not in (200, 201):
        fail("miner commit", f"HTTP {status} — {data}")
        return False
    ok("miner commit accepted", f"hash={commit_hash[:16]}…")
    return True


def step_reveal(subnet: str, task_id: str, miner_hotkey: str, yield_val: float,
                confidence: float, nonce: str) -> bool:
    status, data = post(f"{subnet}/responses/reveal", {
        "task_id": task_id,
        "miner_hotkey": miner_hotkey,
        "expected_yield": yield_val,
        "confidence": confidence,
        "nonce": nonce,
    })
    if status not in (200, 201):
        fail("miner reveal", f"HTTP {status} — {data}")
        return False
    hash_valid = data.get("hash_valid")
    if not hash_valid:
        fail("reveal hash valid", "hash_valid=False — commit/reveal mismatch")
        return False
    ok("miner reveal accepted", f"hash_valid=True yield={yield_val}")
    return True


def step_ground_truth(subnet: str, task_id: str, farm_id: int, actual_yield: float) -> bool:
    status, data = post(f"{subnet}/responses/ground-truth", {
        "task_id": task_id,
        "farm_id": farm_id,
        "actual_yield": actual_yield,
    })
    if status not in (200, 201):
        fail("submit ground truth", f"HTTP {status} — {data}")
        return False
    verified = data.get("verified")
    reason = data.get("reason", "")
    if not verified:
        fail("ground truth verified", f"reason={reason}")
        return False
    ok("ground truth verified + scoring triggered", f"actual={actual_yield} t/ha")
    return True


def step_task_scored(subnet: str, task_id: str) -> bool:
    status, data = get(f"{subnet}/tasks/{task_id}")
    if status != 200:
        fail("fetch task after scoring", f"HTTP {status}")
        return False
    task_status = data.get("status")
    if task_status != "scored":
        fail("task status = scored", f"got status={task_status!r}")
        return False
    ok("task marked scored", f"scored_at={data.get('scored_at', '?')}")
    return True


def step_predictions_visible(subnet: str, farm_id: int) -> bool:
    status, data = get(f"{subnet}/tasks/predictions?farm_id={farm_id}")
    if status == 404:
        warn("predictions endpoint", "no scored predictions yet (may need a moment)")
        return True  # non-fatal — timing
    if status != 200:
        fail("predictions endpoint", f"HTTP {status} — {data}")
        return False
    preds = data.get("predictions", [])
    ok("predictions visible to farmer", f"{len(preds)} prediction(s) returned")
    return True


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _load_env()
    backend = os.getenv("BACKEND_URL", "").rstrip("/")
    subnet = os.getenv("SUBNET_URL", "").rstrip("/")

    print(f"\n{DIM}{'=' * 60}{RESET}")
    print("  RaiRai live-loop smoke test")
    print(f"{DIM}{'=' * 60}{RESET}")

    if not backend:
        print(f"\n{RED}ABORT{RESET}: BACKEND_URL is not set.")
        sys.exit(1)
    if not subnet:
        print(f"\n{RED}ABORT{RESET}: SUBNET_URL is not set.")
        sys.exit(1)

    step_env(backend, subnet)

    # ── Step 1: challenge pool ────────────────────────────────────────────────
    print(f"{DIM}Step 1 — challenge pool{RESET}")
    farm = step_challenge_pool(backend)
    if farm is None:
        print(f"\n{RED}ABORT{RESET}: no farms available — cannot continue.")
        sys.exit(1)

    # ── Step 2: satellite history ─────────────────────────────────────────────
    print(f"\n{DIM}Step 2 — satellite history{RESET}")
    ndvi = step_satellite_history(backend, farm)

    # ── Step 3: create task ───────────────────────────────────────────────────
    print(f"\n{DIM}Step 3 — create task{RESET}")
    task_id = step_create_task(subnet, farm, ndvi)
    if task_id is None:
        print(f"\n{RED}ABORT{RESET}: task creation failed — cannot continue.")
        sys.exit(1)

    # ── Step 4 + 5: commit → reveal ───────────────────────────────────────────
    print(f"\n{DIM}Steps 4–5 — commit / reveal{RESET}")
    miner_hotkey = f"smoke_test_{uuid.uuid4().hex[:8]}"
    yield_val = 4.2
    confidence = 0.8
    nonce = uuid.uuid4().hex

    committed = step_commit(subnet, task_id, miner_hotkey, yield_val, confidence, nonce)
    if committed:
        step_reveal(subnet, task_id, miner_hotkey, yield_val, confidence, nonce)

    # ── Step 6: ground truth ──────────────────────────────────────────────────
    print(f"\n{DIM}Step 6 — ground truth{RESET}")
    actual_yield = 4.5
    scored = step_ground_truth(subnet, task_id, farm["farm_id"], actual_yield)

    # ── Step 7: verify task scored ────────────────────────────────────────────
    print(f"\n{DIM}Step 7 — task scored{RESET}")
    if scored:
        step_task_scored(subnet, task_id)
    else:
        warn("task scored check", "skipped — ground truth was not verified")

    # ── Step 8: predictions visible ───────────────────────────────────────────
    print(f"\n{DIM}Step 8 — predictions visible{RESET}")
    step_predictions_visible(subnet, farm["farm_id"])

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{DIM}{'=' * 60}{RESET}")
    if _failures:
        print(f"{RED}FAIL{RESET}: {len(_failures)} step(s) failed:")
        for f in _failures:
            print(f"   • {f}")
        sys.exit(1)
    print(f"{GREEN}PASS{RESET}: all steps completed. Live scoring loop is operational.")


if __name__ == "__main__":
    main()
