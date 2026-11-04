"""Atomic workflow recommendation save, plus read-only persisted run inspection."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from retailrag.models import AgentExecution, Recommendation, RecommendationItem, RecommendationSnapshot, WorkflowRun, WorkflowStep
from retailrag.workflow_validation import validate_workflow_items


def save_workflow_recommendation(engine, store, run_id, request, output):
    output = output.model_copy(deep=True)
    with Session(engine) as session, session.begin():
        run = session.get(WorkflowRun, run_id)
        if run is None or run.status != "running" or run.recommendation_id is not None:
            raise ValueError("Run is missing, already saved, or not running")
        if run.request != request.model_dump(mode="json") or output.run_id != run_id:
            raise ValueError("Request/run identity mismatch")
        if not output.validation.get("valid") or output.context is None:
            raise ValueError("Cannot save unvalidated workflow output")
        if output.references != [item.product.id for item in output.items]:
            raise ValueError("Response references differ from validated products")
        validate_workflow_items(session, store, request, output.context, output.profile, output.items,
                                output.active_weights, output.preference_basis)
        recommendation = Recommendation(customer_id=request.customer_id, query=request.query,
                                        channel=request.channel, mode=request.mode)
        recommendation.items = [RecommendationItem(product_id=item.product.id, rank=item.rank, score=item.relevance_score,
                                                   price_snapshot=item.product.price, explanation=item.explanation) for item in output.items]
        session.add(recommendation)
        session.flush()
        output.id, output.created_at = recommendation.id, recommendation.created_at
        payload = output.model_dump(mode="json")
        session.add(RecommendationSnapshot(recommendation_id=recommendation.id, request=request.model_dump(mode="json"), payload=payload))
        run.recommendation_id, run.output = recommendation.id, payload
        execution_ids = select(WorkflowStep.execution_id).where(WorkflowStep.run_id == run_id)
        for execution in session.scalars(select(AgentExecution).where(AgentExecution.id.in_(execution_ids))):
            execution.recommendation_id = recommendation.id
    return output


def read_workflow_run(session, run_id):
    run = session.get(WorkflowRun, run_id)
    if run is None:
        raise LookupError("Workflow run not found")
    rows = session.execute(select(WorkflowStep, AgentExecution).join(AgentExecution, AgentExecution.id == WorkflowStep.execution_id)
                           .where(WorkflowStep.run_id == run_id).order_by(WorkflowStep.sequence)).all()
    steps = [{"sequence": step.sequence, "execution_id": execution.id, "agent": execution.agent_name,
              "status": execution.status, "started_at": execution.started_at.isoformat(),
              "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
              "duration_ms": round((execution.finished_at - execution.started_at).total_seconds() * 1000, 3) if execution.finished_at else None,
              "tool_calls": execution.tool_calls, "output_summary": execution.output_summary, "error": execution.error}
             for step, execution in rows]
    return {"run_id": run.id, "status": run.status, "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None, "request": run.request,
            "recommendation_id": run.recommendation_id, "output": run.output, "error": run.error,
            "steps": steps, "checkpoint": run.state}
