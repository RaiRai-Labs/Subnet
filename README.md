# RaiRai Subnet

Validator backend for the **RaiRai-Labs Bittensor subnet** — agricultural yield
prediction (spec: *RaiRai-Labs Subnet MVP Specification v0.1*).

Validators create yield-prediction tasks from farm + satellite + weather data,
distribute them to miners, collect commit-reveal predictions, and score miners
against real harvest outcomes (MAE → rank score → normalized consensus weights).

Built with **FastAPI**, **Pydantic v2**, **SQLAlchemy (async)** and **PostgreSQL**,
managed with **uv**.

## Validator neuron

The Bittensor validator neuron lives in `neurons/validator.py` (library code in
`subnet/`). It runs a loop that poses a yield-prediction task, queries miners,
scores them (MAE → rank score), keeps an EMA of per-miner scores, and sets
normalized weights every `epoch_length` steps.

Run it offline (mock metagraph + in-process mock miners — no wallet or chain):

```bash
uv run python -m neurons.validator --mock
# faster demo:
uv run python -m neurons.validator --mock --neuron.forward_interval 1 --neuron.epoch_length 3
```

Live run (later — requires a registered wallet/hotkey on a subnet):

```bash
uv run python -m neurons.validator \
  --netuid <id> --subtensor.network <net> \
  --wallet.name <wallet> --wallet.hotkey <hotkey>
```

Layout:

```
neurons/validator.py          # entry point: Validator(BaseValidatorNeuron)
subnet/
├── protocol.py               # YieldPredictionSynapse (bt.Synapse)
├── mock.py                   # MockMetagraph (offline)
├── base/
│   ├── neuron.py             # BaseNeuron: wallet/subtensor/metagraph (or mock)
│   └── validator.py          # BaseValidatorNeuron: EMA scores, run loop, set_weights
└── validator/
    ├── config.py             # bittensor config + custom args
    ├── challenge.py          # generates a task + hidden ground truth (mock)
    └── forward.py            # query miners, score, update scores
```

Scoring reuses `app/core/scoring.py` (`mean_absolute_error`, `rank_score`,
`normalize_weights`); miners reuse `app/miners/mock.py`.

## Project structure

```
rairai_subnet/
├── pyproject.toml          # project + dependencies (uv)
├── .env.example            # copy to .env and fill in DATABASE_URL
└── app/
    ├── main.py             # FastAPI app + lifespan (auto-creates schema)
    ├── core/
    │   ├── config.py       # pydantic-settings (env / .env)
    │   ├── database.py     # async engine + session (imported from RaiRaiApp)
    │   ├── migrations.py   # create_all bootstrap (no Alembic for MVP)
    │   ├── validator.py    # validator workflow: query miners, average, complete
    │   └── scoring.py      # MAE, rank score, weight normalization, commit hash
    ├── miners/
    │   └── mock.py         # 3 mock miners with fixed predictions (4.1 / 4.3 / 4.2)
    ├── models/             # SQLAlchemy ORM
    │   ├── farm.py             # Farm, FarmUserLink   (imported from RaiRaiApp)
    │   ├── farm_analysis.py    # FarmAnalysis         (imported from RaiRaiApp)
    │   ├── task.py            # PredictionTask
    │   └── response.py        # MinerResponse, GroundTruth
    ├── schemas/            # Pydantic request/response models
    └── api/                # routers: tasks, responses
```

## Database schema

| Table | Purpose |
|-------|---------|
| `farms`, `farm_user_links` | Farm registry (imported from RaiRaiApp) |
| `farm_analysis` | Satellite-derived indices per farm/date (imported) |
| `prediction_tasks` | Validator-created tasks sent to miners |
| `miner_responses` | Commit-reveal predictions + per-task scores/weights |
| `ground_truth` | Farmer-reported actual harvest yields |

Tables are created automatically on startup via `Base.metadata.create_all`.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and PostgreSQL.

```bash
# 1. Install dependencies into a managed virtualenv
uv sync

# 2. Configure environment
cp .env.example .env
#    edit .env — set DATABASE_URL (URL-encode @ -> %40, $ -> %24 in the password)

# 3. Create the database (example, local Postgres)
createdb rairai_subnet     # or: psql -c "CREATE DATABASE rairai_subnet;"
```

`DATABASE_URL` must use the async driver, e.g.:

```
postgresql+asyncpg://rairai:rairai@localhost:5432/rairai_subnet
```

## Run

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

## API

| Method & path | Description |
|---------------|-------------|
| `POST /tasks` | Submit farm/crop data → generates a task id, stores it, confirms acceptance |
| `POST /tasks/{task_id}/validate` | Run the validator workflow: query mock miners, average, complete the task |
| `GET /tasks` | List tasks (optional `?status=open\|completed\|closed\|scored`) |
| `GET /tasks/{task_id}` | Get a task (incl. `average_prediction`) |
| `POST /responses/commit` | Miner commit phase (submit hash) — advanced commit-reveal path |
| `POST /responses/reveal` | Miner reveal phase (verifies hash) |
| `POST /responses/ground-truth` | Farmer reports actual yield |
| `POST /responses/score/{task_id}` | Score revealed miners → MAE, score, weights |

### Mock miners

The MVP validator workflow queries three in-process mock miners with fixed
predictions (`app/miners/mock.py`): `miner_a → 4.1`, `miner_b → 4.3`,
`miner_c → 4.2`. `POST /tasks/{task_id}/validate` sends the task to all three,
stores each response, averages them, and marks the task `completed`.

### Commit hash convention

```
commit_hash = sha256("{expected_yield}:{confidence}:{nonce}")
```

### Scoring (spec §8–9)

```
MAE    = |expected_yield - actual_yield|
score  = 1 / (1 + MAE)
weight = score / sum(scores)        # normalized for Yuma Consensus
```

## Example flow (MVP: mock miners + averaging)

```bash
B=http://127.0.0.1:8000

# 1. Submit farm/crop data — the service generates and returns a task id
curl -X POST $B/tasks -H 'Content-Type: application/json' \
  -d '{"crop":"rice","province":"Chiang Mai","field_size":15,"ndvi":[0.3,0.5,0.7],"weather":[{"temp":28,"rain":4}]}'
# -> {"task_id":"task_<hex>","status":"open","message":"Prediction task accepted"}

# 2. Run the validator workflow against the 3 mock miners
curl -X POST $B/tasks/task_<hex>/validate
# -> averages 4.1, 4.3, 4.2 = 4.2, marks the task "completed"

curl $B/tasks/task_<hex>   # average_prediction = 4.2, status = completed
```

## Advanced flow (commit-reveal + scoring, spec §8–10)

```bash
B=http://127.0.0.1:8000
# miner commits sha256("4.1:0.82:salt"), then reveals
curl -X POST $B/responses/reveal -H 'Content-Type: application/json' \
  -d '{"task_id":"task_001","miner_hotkey":"miner_A","expected_yield":4.1,"confidence":0.82,"nonce":"salt"}'

curl -X POST $B/responses/ground-truth -H 'Content-Type: application/json' \
  -d '{"task_id":"task_001","actual_yield":4.5}'

curl -X POST $B/responses/score/task_001
```
