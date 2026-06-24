"""Miner response endpoints: commit, reveal, ground truth, scoring."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.scoring import (
    build_commit_hash,
    competition_rank,
    dual_metric_error,
    mean_absolute_error,
    normalize_weights,
    winner_take_most,
)
from app.models.response import GroundTruth, MinerResponse
from app.models.task import PredictionTask, TaskStatus
from app.schemas.response import (
    CommitRequest,
    GroundTruthRequest,
    MinerResponseOut,
    RevealRequest,
)

router = APIRouter(prefix="/responses", tags=["responses"])


async def _get_task(db: AsyncSession, task_id: str) -> PredictionTask:
    task = await db.scalar(
        select(PredictionTask).where(PredictionTask.task_id == task_id)
    )
    if not task:
        raise HTTPException(404, "task not found")
    return task


@router.post("/commit", response_model=MinerResponseOut, status_code=201)
async def commit(payload: CommitRequest, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, payload.task_id)
    if task.status != TaskStatus.open:
        raise HTTPException(409, "task is not open for commits")

    existing = await db.scalar(
        select(MinerResponse).where(
            MinerResponse.task_id == task.id,
            MinerResponse.miner_hotkey == payload.miner_hotkey,
        )
    )
    if existing:
        raise HTTPException(409, "miner already committed to this task")

    resp = MinerResponse(
        task_id=task.id,
        miner_hotkey=payload.miner_hotkey,
        miner_uid=payload.miner_uid,
        commit_hash=payload.commit_hash,
    )
    db.add(resp)
    await db.commit()
    await db.refresh(resp)
    return resp


@router.post("/reveal", response_model=MinerResponseOut)
async def reveal(payload: RevealRequest, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, payload.task_id)

    resp = await db.scalar(
        select(MinerResponse).where(
            MinerResponse.task_id == task.id,
            MinerResponse.miner_hotkey == payload.miner_hotkey,
        )
    )
    if not resp:
        raise HTTPException(404, "no commit found for this miner/task")
    if resp.revealed:
        raise HTTPException(409, "already revealed")

    expected = build_commit_hash(
        payload.expected_yield, payload.confidence, payload.nonce
    )
    resp.hash_valid = expected == resp.commit_hash
    resp.revealed = True
    resp.expected_yield = payload.expected_yield
    resp.confidence = payload.confidence
    resp.nonce = payload.nonce
    resp.revealed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(resp)
    return resp


@router.post("/ground-truth", status_code=201)
async def submit_ground_truth(
    payload: GroundTruthRequest, db: AsyncSession = Depends(get_db)
):
    task = await _get_task(db, payload.task_id)
    gt = GroundTruth(
        task_id=task.id,
        farm_id=payload.farm_id or task.farm_id,
        actual_yield=payload.actual_yield,
    )
    db.add(gt)
    await db.commit()
    await db.refresh(gt)
    return {"id": gt.id, "task_id": task.task_id, "actual_yield": gt.actual_yield}


@router.post("/score/{task_id}")
async def score_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Score all valid reveals for a task against its ground truth (spec §8–9)."""
    task = await _get_task(db, task_id)

    gt = await db.scalar(
        select(GroundTruth)
        .where(GroundTruth.task_id == task.id)
        .order_by(GroundTruth.created_at.desc())
    )
    if not gt:
        raise HTTPException(409, "no ground truth submitted for this task")

    responses = list(
        await db.scalars(
            select(MinerResponse).where(
                MinerResponse.task_id == task.id,
                MinerResponse.revealed.is_(True),
                MinerResponse.hash_valid.is_(True),
            )
        )
    )
    if not responses:
        raise HTTPException(409, "no valid revealed responses to score")

    for r in responses:
        r.mae = mean_absolute_error(r.expected_yield, gt.actual_yield)
        r.score = dual_metric_error(r.expected_yield, gt.actual_yield)

    ranks = competition_rank([r.score for r in responses])
    weights = winner_take_most(ranks)
    for r, w in zip(responses, weights):
        r.weight = w

    task.status = TaskStatus.scored
    task.scored_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "task_id": task.task_id,
        "actual_yield": gt.actual_yield,
        "scored": [
            {
                "miner_hotkey": r.miner_hotkey,
                "expected_yield": r.expected_yield,
                "mae": r.mae,
                "score": r.score,
                "weight": r.weight,
            }
            for r in responses
        ],
    }
