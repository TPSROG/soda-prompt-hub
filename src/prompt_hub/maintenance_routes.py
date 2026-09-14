from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from prompt_hub.background_jobs import (
        BackgroundJobRunner,
        BackgroundJobStore,
        JobContext,
        JobResult,
    )
    from prompt_hub.maintenance import BackupManager


class BackupInput(BaseModel):
    destination: str = Field(default="", max_length=4096)


def create_maintenance_router(
    manager: BackupManager,
    job_store: BackgroundJobStore,
    job_runner: BackgroundJobRunner,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/maintenance/backup-status")
    def backup_status() -> dict[str, Any]:
        status_value = manager.status()
        jobs = job_store.list_jobs(job_type="personal_backup", limit=1)
        return {**status_value, "latest_job": jobs[0] if jobs else None}

    @router.post("/api/maintenance/backups", status_code=status.HTTP_202_ACCEPTED)
    def create_backup(payload: BackupInput) -> dict[str, Any]:
        destination = payload.destination.strip()
        if destination:
            try:
                resolved = Path(destination).expanduser().resolve()
            except (OSError, RuntimeError) as error:
                raise HTTPException(status_code=422, detail="备份目标路径无效") from error
            if resolved == Path.home().resolve():
                raise HTTPException(status_code=422, detail="请不要直接使用个人主目录作为备份目标")
        return job_runner.submit(
            "personal_backup",
            {"destination": destination},
            exclusive=True,
        )

    return router


def backup_job(manager: BackupManager) -> Callable[[Mapping[str, Any], JobContext], JobResult]:
    def run(payload: Mapping[str, Any], context: JobContext) -> dict[str, Any]:
        destination = str(payload.get("destination", "")).strip()
        return manager.create(Path(destination) if destination else None, context=context)

    return run
