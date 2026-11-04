"""Public tool discovery/execution and persisted invocation inspection."""

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from retailrag.catalog_api import get_session
from retailrag.models import ToolInvocation
from retailrag.tool_schemas import ExecuteInput
from retailrag.tool_service import ToolService, invocation_payload

router = APIRouter(prefix="/tools", tags=["Tools"])


def service(request: Request):
    return ToolService(request.app.state.engine, request.app.state.rag_store)


@router.get("")
def list_tools(tools=Depends(service)):
    return tools.discovery()


@router.get("/invocations")
def invocations(
    tool: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, pattern=r"^(running|completed|failed)$"),
    limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session=Depends(get_session),
):
    statement = select(ToolInvocation)
    if tool is not None:
        statement = statement.where(ToolInvocation.tool_name == tool)
    if status is not None:
        statement = statement.where(ToolInvocation.status == status)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(statement.order_by(ToolInvocation.started_at.desc(), ToolInvocation.id).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset,
            "items": [{"call_id": row.id, "tool": row.tool_name, "effect": row.effect, "status": row.status,
                       "started_at": row.started_at, "finished_at": row.finished_at,
                       "recommendation_id": row.recommendation_id, "error_code": row.error_code} for row in rows]}


@router.get("/invocations/{call_id}")
def invocation(call_id: str, tools=Depends(service)):
    try:
        return tools.read(call_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/{tool_name}")
def tool_details(tool_name: str, tools=Depends(service)):
    for item in tools.discovery()["items"]:
        if item["name"] == tool_name:
            return item
    raise HTTPException(404, "Tool is not in the public allowlist")


@router.post("/{tool_name}/execute")
def execute(values: ExecuteInput, tool_name: str = Path(pattern=r"^[a-z][a-z0-9_]{0,99}$"), tools=Depends(service)):
    result, status_code = tools.execute(tool_name, values.arguments)
    return JSONResponse(status_code=status_code, content=result)
