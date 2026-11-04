"""JSON-safe LangGraph state and validated workflow/tool contracts."""

from datetime import datetime
from typing import Annotated, Literal, TypedDict
import operator

from pydantic import BaseModel, ConfigDict, Field, model_validator

from retailrag.recommendation_schemas import CustomerProfile, RecommendationRequest, RecommendationResultItem, ResolvedContext


class WorkflowRequest(RecommendationRequest):
    retrieval_strategy: Literal["auto", "rag", "content"] = "auto"
    limit: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def supported_strategy(self):
        if self.retrieval_strategy == "rag" and (self.mode != "context_aware" or not self.strict_budget):
            raise ValueError("Explicit rag strategy requires context_aware mode and strict_budget=true")
        return self

    def recommendation_request(self):
        return RecommendationRequest.model_validate(self.model_dump(exclude={"retrieval_strategy"}))


class WorkflowItem(RecommendationResultItem):
    retrieval_source: Literal["chroma", "content"]
    document_id: str
    document: str
    metadata: dict


class WorkflowOutput(BaseModel):
    id: int | None = None
    created_at: datetime | None = None
    run_id: str
    engine: Literal["langgraph_workflow"] = "langgraph_workflow"
    llm_used: Literal[False] = False
    generation: Literal["deterministic_agents"] = "deterministic_agents"
    mode: str
    query: str
    customer_id: str | None
    channel: str
    message: str
    answer: str
    warnings: list[str]
    context: ResolvedContext | None
    profile: CustomerProfile | None
    active_weights: dict[str, float]
    preference_basis: str
    retrieval_source: str
    index_generation: str | None
    validation: dict
    references: list[str]
    items: list[WorkflowItem]


class WorkflowState(TypedDict, total=False):
    run_id: str
    request: dict
    plan: dict
    context: dict
    profile: dict | None
    customer_history: dict
    retrieval: dict
    candidates: list[dict]
    ranked: list[dict]
    items: list[dict]
    active_weights: dict[str, float]
    preference_basis: str
    validation: dict
    output: dict
    error: str | None
    warnings: Annotated[list[str], operator.add]
    executed_agents: Annotated[list[str], operator.add]


class ToolCall(BaseModel):
    name: str
    status: Literal["completed", "failed"]
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    arguments: dict
    output_summary: dict | None = None
    output_sha256: str | None = None
    error: str | None = None


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
