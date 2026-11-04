"""Workflow creation and persisted actual execution status."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.catalog_api import get_session
from retailrag.models import WorkflowRun, WorkflowStep
from retailrag.workflow import run_workflow, workflow_definition
from retailrag.workflow_persistence import read_workflow_run
from retailrag.workflow_schemas import WorkflowRequest

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("/definition")
def definition():
    return workflow_definition()


@router.post("/run", status_code=201)
def run(values: WorkflowRequest, request: Request):
    return run_workflow(request.app.state.engine, request.app.state.rag_store, values)


@router.get("/status")
def status(
    status: str | None = Query(default=None, pattern=r"^(running|completed|failed)$"),
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    statement = select(WorkflowRun)
    if status is not None:
        statement = statement.where(WorkflowRun.status == status)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(statement.order_by(WorkflowRun.started_at.desc(), WorkflowRun.id).offset(offset).limit(limit)).all()
    counts = dict(session.execute(select(WorkflowRun.status, func.count()).group_by(WorkflowRun.status)).all())
    return {"total": total, "limit": limit, "offset": offset, "counts": counts,
            "items": [{"run_id": row.id, "status": row.status, "started_at": row.started_at,
                       "finished_at": row.finished_at, "query": row.request.get("query", ""), "mode": row.request.get("mode"),
                       "channel": row.request.get("channel"), "customer_id": row.request.get("customer_id"),
                       "recommendation_id": row.recommendation_id, "error": row.error,
                       "executed_steps": session.scalar(select(func.count()).select_from(WorkflowStep).where(WorkflowStep.run_id == row.id))}
                      for row in rows]}


@router.get("/runs/{run_id}")
def details(run_id: str, session: Session = Depends(get_session)):
    try:
        return read_workflow_run(session, run_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
