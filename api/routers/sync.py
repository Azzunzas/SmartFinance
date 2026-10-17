from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_session
from api.schemas.sync import SyncAcceptedOut, SyncRunOut, SyncStatusOut
from core.repository.sync_runs import list_recent_sync_runs
from jobs.sync.manual import claim_manual_sync, manual_sync_running, run_claimed_manual_sync

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusOut)
def sync_status() -> SyncStatusOut:
    return SyncStatusOut(running=manual_sync_running())


@router.post("/run", response_model=SyncAcceptedOut, status_code=status.HTTP_202_ACCEPTED)
def run_sync(background_tasks: BackgroundTasks) -> SyncAcceptedOut:
    if not claim_manual_sync():
        raise HTTPException(status_code=409, detail="já existe uma sincronização em andamento")
    background_tasks.add_task(run_claimed_manual_sync)
    return SyncAcceptedOut()


@router.get("/runs", response_model=list[SyncRunOut])
def list_runs(
    limit: int = Query(20, ge=1, le=100),
    kind: Literal["FULL", "INCREMENTAL", "MANUAL"] | None = Query(None),
    session: Session = Depends(get_session),
) -> list[SyncRunOut]:
    return [
        SyncRunOut.model_validate(run)
        for run in list_recent_sync_runs(session, limit, kind=kind)
    ]
