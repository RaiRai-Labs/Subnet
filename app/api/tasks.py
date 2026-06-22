"""Prediction task endpoints (validator side)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.validator import run_validation
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
    status: TaskStatus | None = None, db: AsyncSession = Depends(get_db)
):
    stmt = select(PredictionTask).order_by(PredictionTask.created_at.desc())
    if status is not None:
        stmt = stmt.where(PredictionTask.status == status)
    return list(await db.scalars(stmt))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)):
    return await _get_task_or_404(db, task_id)
