# RaiRai Subnet

Validator backend for the **RaiRai-Labs Bittensor subnet** — agricultural yield
prediction (spec: *RaiRai-Labs Subnet MVP Specification v0.1*).

Validators create yield-prediction tasks from farm + satellite + weather data,
distribute them to miners, collect commit-reveal predictions, and score miners
against real harvest outcomes (MAE → rank score → normalized consensus weights).

Built with **FastAPI**, **Pydantic v2**, **SQLAlchemy (async)** and **PostgreSQL**,
managed with **uv**.

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
    │   └── scoring.py      # MAE, rank score, weight normalization, commit hash
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
| `POST /tasks` | Create a prediction task |
| `GET /tasks` | List tasks (optional `?status=open\|closed\|scored`) |
| `GET /tasks/{task_id}` | Get a task |
| `POST /responses/commit` | Miner commit phase (submit hash) |
| `POST /responses/reveal` | Miner reveal phase (verifies hash) |
| `POST /responses/ground-truth` | Farmer reports actual yield |
| `POST /responses/score/{task_id}` | Score revealed miners → MAE, score, weights |

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

## Example flow

```bash
B=http://127.0.0.1:8000
curl -X POST $B/tasks -H 'Content-Type: application/json' \
  -d '{"task_id":"task_001","crop":"rice","province":"Chiang Mai","field_size":15,"ndvi":[0.3,0.5,0.7],"weather":[{"temp":28,"rain":4}]}'

# miner commits sha256("4.1:0.82:salt"), then reveals
curl -X POST $B/responses/reveal -H 'Content-Type: application/json' \
  -d '{"task_id":"task_001","miner_hotkey":"miner_A","expected_yield":4.1,"confidence":0.82,"nonce":"salt"}'

curl -X POST $B/responses/ground-truth -H 'Content-Type: application/json' \
  -d '{"task_id":"task_001","actual_yield":4.5}'

curl -X POST $B/responses/score/task_001
```
