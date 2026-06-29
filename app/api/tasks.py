"""Prediction task endpoints (validator side)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.validator import run_validation
from app.models.response import GroundTruth, MinerResponse
from app.models.task import PredictionTask, TaskStatus
from app.schemas.task import TaskAccepted, TaskCreate, TaskOut, ValidationResult

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _generate_task_id() -> str:
    """Generate a unique, human-readable task id (spec MVP step 3)."""
    return f"task_{uuid.uuid4().hex[:12]}"


async def _get_task_or_404(db: AsyncSession, task_id: str) -> PredictionTask:
    task = await db.scalar(
        select(PredictionTask).where(PredictionTask.task_id == task_id)
    )
    if not task:
        raise HTTPException(404, "task not found")
    return task


@router.post("", response_model=TaskAccepted, status_code=201)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Receive farm/crop data, generate a task id, store it, confirm acceptance."""
    task = PredictionTask(task_id=_generate_task_id(), **payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return TaskAccepted(task_id=task.task_id, status=task.status)


@router.post("/{task_id}/validate", response_model=ValidationResult)
async def validate_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """Run the validator workflow: query mock miners, average, complete the task."""
    task = await _get_task_or_404(db, task_id)
    if task.status == TaskStatus.completed:
        raise HTTPException(409, "task already completed")
    try:
        return await run_validation(db, task)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    status: TaskStatus | None = None,
    farm_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PredictionTask).order_by(PredictionTask.created_at.desc())
    if status is not None:
        stmt = stmt.where(PredictionTask.status == status)
    if farm_id is not None:
        stmt = stmt.where(PredictionTask.farm_id == farm_id)
    return list(await db.scalars(stmt))


@router.get("/predictions", response_model=None)
async def farm_predictions(
    farm_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Return top-miner yield predictions for the most recent scored task for a farm.

    Intended to be called by the farmer portal proxy — no auth required because
    the portal enforces LINE auth before forwarding the request.

    Security: predictions are only returned for SCORED tasks. A task is only
    scored after the farmer submits their actual harvest yield. This means a
    farmer cannot see what miners predicted before submitting — preventing them
    from picking a yield value that artificially favours a specific miner.
    """
    task = await db.scalar(
        select(PredictionTask)
        .where(
            PredictionTask.farm_id == farm_id,
            PredictionTask.status.in_([TaskStatus.completed, TaskStatus.scored]),
        )
        .order_by(PredictionTask.scored_at.desc(), PredictionTask.completed_at.desc())
    )
    if not task:
        raise HTTPException(404, "no predictions found for this farm yet")

    responses = list(
        await db.scalars(
            select(MinerResponse)
            .where(
                MinerResponse.task_id == task.id,
                MinerResponse.revealed.is_(True),
                MinerResponse.hash_valid.is_(True),
            )
            .order_by(MinerResponse.expected_yield.desc())
            .limit(limit)
        )
    )

    gt = await db.scalar(
        select(GroundTruth).where(GroundTruth.task_id == task.id)
    )

    return {
        "task_id": task.task_id,
        "farm_id": farm_id,
        "crop": task.crop,
        "scored_at": task.scored_at.isoformat() if task.scored_at else None,
        "actual_yield": gt.actual_yield if gt else None,
        "predictions": [
            {
                "rank": idx + 1,
                "miner_uid": r.miner_uid,
                "miner_hotkey": r.miner_hotkey,
                "predicted_yield": r.expected_yield,
                "confidence": r.confidence,
                "mae": r.mae,
                "weight": r.weight,
            }
            for idx, r in enumerate(responses)
        ],
    }


@router.post("/farm/{farm_id}/cancel")
async def cancel_farm_tasks(farm_id: int, db: AsyncSession = Depends(get_db)):
    """Cancel all open/completed tasks for a farm.

    Called by the backend when a farmer starts a new season (new planting date +
    crop type). Stale tasks from the previous season must not be scored against
    the new season's actual yield.
    """
    tasks = list(
        await db.scalars(
            select(PredictionTask).where(
                PredictionTask.farm_id == farm_id,
                PredictionTask.status.in_(
                    [TaskStatus.open, TaskStatus.completed]
                ),
            )
        )
    )
    for task in tasks:
        task.status = TaskStatus.cancelled
    await db.commit()
    return {"farm_id": farm_id, "cancelled_tasks": len(tasks)}


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_task_or_404(db, task_id)
