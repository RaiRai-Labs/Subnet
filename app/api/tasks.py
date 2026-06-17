"""Prediction task endpoints (validator side)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import PredictionTask, TaskStatus
from app.schemas.task import TaskCreate, TaskOut

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(
        select(PredictionTask).where(PredictionTask.task_id == payload.task_id)
    )
    if exists:
        raise HTTPException(409, f"task_id '{payload.task_id}' already exists")

    task = PredictionTask(**payload.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


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
    task = await db.scalar(
        select(PredictionTask).where(PredictionTask.task_id == task_id)
    )
    if not task:
        raise HTTPException(404, "task not found")
    return task
