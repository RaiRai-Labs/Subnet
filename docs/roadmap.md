# RaiRai Subnet — 5-Phase Implementation Roadmap

Derived from the gap analysis against [Orpheus-AI/Zeus](https://github.com/Orpheus-AI/Zeus)
(SN18, a live Bittensor subnet) and the *RaiRai-Labs Subnet MVP Specification v0.1*.

**Guiding decision:** `rairai_subnet`'s current FastAPI app is *not* a Bittensor
subnet — it simulates the flow over HTTP. The roadmap turns it into a real
subnet: build Bittensor neurons (`neurons/validator.py`, `neurons/miner.py`),
and demote the existing FastAPI app to the **off-chain farmer/data backend**
(spec §12) that feeds the validator.

Legend: ⬜ todo · ✅ done · 🟡 partial · 🎯 deliverable · 📎 reference

---

## Current status (2026-06-29)

| Phase | State | Notes |
|-------|-------|-------|
| 1 — Bittensor foundation | ✅ done | neurons, base classes, protocol, config all merged |
| 2 — Commit-reveal & weights | ✅ done | `set_weights()` auto-detects commit-reveal and routes; *prediction* anti-copying replaced by collusion detection + deferred scoring (see Phase 2 note) |
| 3 — Scoring & incentive | ✅ done | dual-metric, competition rank, winner-take-most, aggregate all live in `app/core/scoring.py`; rolling history in `subnet/validator/rank_history.py` |
| 4 — Anti-gaming & data | ✅ done (1 gap) | code complete; **live Sentinel Hub unverified** — needs valid CDSE `SH_CLIENT_*` creds to exercise end-to-end |
| 5 — Ops & farmer backend | 🟡 partial | ops half ✅ (PM2, auto-update, setup, observability, **tests + CI**, guides); **farmer portal + validator proxy API still TODO** (owned separately) |

**Remaining work:** validator proxy API · farmer portal flow · live satellite
verification (blocked on creds) · first live on-chain deploy (only proven in
`--mock` so far).

---

## Phase 1 — Bittensor Foundation

Stand up the neuron layer so we have wallets, hotkeys, UIDs, metagraph, and
axon/dendrite messaging. Nothing else works without this.

- ✅ Add `bittensor` SDK to dependencies; pin a version (using `>=10.4.1`).
- ✅ Create `zeus/base`-equivalent base classes: `BaseNeuron`, `BaseValidatorNeuron`, `BaseMinerNeuron` (run-loop, registration check, metagraph resync, background thread, context-manager lifecycle).
- ✅ Define the protocol/synapse: a `YieldPredictionSynapse` (request: farm/crop/NDVI/weather features; response: `expected_yield`, `confidence`). 📎 `subnet/protocol.py`
- ✅ Implement `neurons/miner.py`: serve axon, attach `forward`/`blacklist`/`priority`, return a (stub) prediction.
- ✅ Implement `neurons/validator.py`: dendrite query of miners, metagraph sync, skeleton `forward()`.
- ✅ Config plumbing: wallet name/hotkey, netuid, subtensor endpoint, axon port (env-driven).
- 🟡 Stand up / connect to a local subtensor (or testnet netuid) for integration testing — `docs/localnet.md` exists; first real on-chain run is tonight's deploy.
- 🎯 A validator can register, query a miner over axon/dendrite on testnet, and get a yield prediction back.
- 📎 `zeus/base/{neuron,validator,miner}.py`, `neurons/{validator,miner}.py`

---

## Phase 2 — On-Chain Commit-Reveal & Weight Setting

Make the anti-copying scheme trustless and actually pay miners on chain (Yuma).
Replaces our current "POST a hash, we recompute and trust it" flow.

- ✅ On-chain **weight** commit-reveal: `set_weights()` detects `subtensor.commit_reveal_enabled(netuid)` and routes accordingly. 📎 `subnet/base/validator.py`
- 🔀 *Prediction* commit-reveal (per-task hash committed to chain, revealed later) was **descoped** — predictions arrive directly over dendrite and anti-copying is handled by collusion detection + deferred scoring instead. *(Confirm team is OK with this vs. the original spec.)*
- ✅ Epoch timing: set-weights window + chain rate-limit handling (`weights_rate_limit`). 📎 `subnet/base/validator.py::set_weights`
- ✅ Weight setting: normalize → uint16 → `subtensor.set_weights(...)` once per window. 📎 `subnet/base/validator.py`
- 🎯 Weights land on chain once per epoch (verified in `--mock`; live confirmation = tonight's deploy).
- 📎 `zeus/validator/{hash_phase,prediction_phase,weight_setter,time_till_next_epoch}.py`

---

## Phase 3 — Incentive & Scoring Upgrade

Replace the toy `score = 1/(1+MAE)` with a real, gameable-resistant incentive
curve and rolling performance history.

- ✅ Challenge taxonomy: model multiple challenges (e.g. crop × forecast-horizon) each with its own weight, instead of one undifferentiated task. 📎 `subnet/validator/challenge_spec.py`
- ✅ Dual-metric scoring: `(RMSE + MAE)/2`. 📎 `app/core/scoring.py::dual_metric_error`
- ✅ Competition ranking with tie handling (ties share the averaged rank). 📎 `app/core/scoring.py::competition_rank`
- ✅ Rolling rank history: persist per-challenge ranks (use our **Postgres**, not SQLite), average last N rounds with recency tie-breaker. 📎 `subnet/validator/rank_history.py`, `app/core/rank_history.py`
- ✅ Winner-take-most distribution (90% to best + remainder by inverse rank). 📎 `app/core/scoring.py::winner_take_most`
- ✅ Aggregate weights across challenges by effective weight. 📎 `app/core/scoring.py::aggregate_challenge_weights`
- ✅ New tables: `challenge`, `challenge_rank_history`, `best_miners` (extend existing `prediction_tasks`/`miner_responses`). 📎 `app/models/challenge.py`
- 🎯 Weights reflect sustained, multi-round, multi-challenge performance — not a single lucky prediction.
- 📎 `zeus/validator/{reward,metrics,challenge_spec}.py`, `zeus/utils/results_state.py`

---

## Phase 4 — Anti-Gaming & Real Data Pipeline

Close the copying loophole that commit-reveal alone doesn't (Tier 3), and ingest
real ground truth instead of trusting POSTed numbers (spec §4, §7).

Anti-gaming:
- ✅ Collusion detection: pairwise prediction-similarity below threshold ⇒ penalize the newer-registered hotkey. 📎 `subnet/validator/anti_gaming.py::CollusionDetector`
- ✅ Shape/sanity penalties: malformed or out-of-range predictions → worst rank. 📎 `subnet/validator/anti_gaming.py::is_valid_prediction`
- ✅ Miner axon `blacklist` (registered? validator permit? min stake?) and `priority` (by stake). 📎 `subnet/base/miner.py`
- ✅ Liveness: N-strike absence handling (drop history after K consecutive no-shows). 📎 `subnet/validator/rank_history.py::RankTracker.mark_absent`

Data pipeline:
- ✅ Satellite loader: `SatelliteLoader` interface + offline stub + live **Sentinel Hub** provider (Statistical API → NDVI/EVI/NDWI); auto-selected when `SH_CLIENT_ID`/`SH_CLIENT_SECRET` are set, stub otherwise. 📎 `subnet/data/sentinelhub.py`, `subnet/data/satellite.py`
- ✅ Weather loader: Open-Meteo daily history (temperature/rainfall/wind), keyless. 📎 `subnet/data/weather.py`
- ✅ Feature builder: assemble challenge features (`YieldPredictionSynapse`) from farm metadata + satellite + weather. 📎 `subnet/data/features.py`
- ✅ Ground-truth verification (spec §7): range check + NDVI-consistency before a reported harvest counts as truth (wired into `POST /responses/ground-truth`). 📎 `subnet/data/ground_truth.py`
- 🎯 Validators score against verified real-world yield data; copying is detected and penalized. *(Live Sentinel Hub provider implemented; supply `SH_CLIENT_*` creds to exercise it end-to-end.)*
- 📎 `zeus/validator/collusion.py`, `zeus/data/loaders/*`, `zeus/data/{sample,converter}.py`

---

## Phase 5 — Operations & Farmer Backend

Make it runnable unattended in production, and repurpose the existing FastAPI app
as the off-chain farmer portal/backend (spec §12) rather than a fake neuron.

- ✅ Process management: PM2 launch scripts + one-command ecosystem bring-up. 📎 `scripts/start_validator.sh`, `scripts/start_miner.sh`, `ecosystem.config.js`
- ✅ Auto-update + self-heal runner (git fetch/reset + reinstall + periodic restart). 📎 `scripts/run_neuron.py`
- ✅ `setup.sh` (system deps, TCP tuning, pm2-logrotate, opt-in firewall) and `min_compute.yml` (hardware baselines).
- ✅ Pre-launch config doctor + heartbeat staleness monitor. 📎 `scripts/preflight.py`, `scripts/healthcheck.py`
- ✅ Observability: structured logging, optional Discord/webhook alerts, JSON heartbeat metrics. 📎 `subnet/observability.py`
- ✅ Test suite + CI (pytest, GitHub Actions). 📎 `tests/`, `.github/workflows/ci.yml`
- ✅ Validator & miner operator guides. 📎 `docs/Validating.md`, `docs/Mining.md`
- ⬜ Repurpose current FastAPI app: farm registration, yield-forecast display, yield reporting → writes to Postgres, feeds the validator *(owned separately)*.
- ⬜ Optional validator proxy API (serve top-miner predictions to the farmer app) *(owned separately)*. 📎 Zeus `--proxy.port`
- 🎯 A third party can stand up a validator or miner from the docs and it stays running; farmers interact via the web backend.
- 📎 Zeus: `run_neuron.py`, `start_*.sh`, `setup.sh`, `min_compute.yml`, `docs/`

---

## Phase → Gap-Analysis mapping

| Phase | Closes gaps (from analysis) |
|-------|-----------------------------|
| 1 | Tier 1 #1 (no neuron layer) |
| 2 | Tier 1 #2, #3 (on-chain commit-reveal, Yuma weights) |
| 3 | Tier 2 #4–#7 (scoring, rolling ranks, reward curve, taxonomy) |
| 4 | Tier 3 #8–#10 + Tier 4 #11, #12 (anti-gaming, data, serialization) |
| 5 | Tier 5 #13 (ops) + repurpose FastAPI backend |

**Keep (don't over-correct):** Postgres + async SQLAlchemy state store, the
FastAPI layer (as farmer backend / proxy), and the existing commit-reveal data
model shape — all noted as strengths in the gap analysis.
