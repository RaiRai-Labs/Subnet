"""Validator workflow (spec MVP step 5).

Sends a prediction task to all mock miners, collects and stores their
predictions, averages them, and marks the task completed.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.miners.mock import MOCK_MINERS
from app.models.response import MinerResponse
from app.models.task import PredictionTask, TaskStatus


async def run_validation(db: AsyncSession, task: PredictionTask) -> dict:
    """Query all mock miners for a task, store responses, average, complete.

    Idempotency: raises ValueError if the task already has stored responses.
    """
    existing = await db.scalar(
        select(MinerResponse).where(MinerResponse.task_id == task.id)
    )
    if existing is not None:
        raise ValueError("task already has miner responses")

    predictions: list[dict] = []
    for miner in MOCK_MINERS:
        # 1. Send the task to the miner and collect its prediction.
        value = miner.predict(task)

        # 2. Store each miner prediction.
        db.add(
            MinerResponse(
                task_id=task.id,
                miner_hotkey=miner.hotkey,
                miner_uid=miner.uid,
                revealed=True,
                expected_yield=value,
            )
        )
        predictions.append({"miner_hotkey": miner.hotkey, "expected_yield": value})

    # 3. Calculate the average prediction.
    average = sum(p["expected_yield"] for p in predictions) / len(predictions)

    # 4. Mark the task completed.
    task.average_prediction = average
    task.status = TaskStatus.completed
    task.completed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(task)

    return {
        "task_id": task.task_id,
        "status": task.status,
        "predictions": predictions,
        "average_prediction": average,
    }
