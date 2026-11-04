"""Ten functioning deterministic role agents, executed by a real LangGraph graph."""

import json
import uuid
from importlib.metadata import version

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retailrag.models import AgentExecution, WorkflowRun, WorkflowStep, utc_now
from retailrag.workflow_persistence import read_workflow_run
from retailrag.workflow_schemas import WorkflowOutput, WorkflowState
from retailrag.workflow_tools import WorkflowTools, safe_error

AGENTS = {
    "supervisor": "Select a retrieval strategy from request capabilities and actual index readiness",
    "query_understanding": "Extract and validate query budget, category, brand, and source-product constraints",
    "customer_context": "Analyze real cross-channel shopping history or read the anonymous catalog baseline",
    "product_retrieval": "Execute Chroma retrieval or content fallback with attributable product evidence",
    "recommendation": "Compute text, preference, category, brand, budget, and availability components",
    "product_ranking": "Sort candidates by the actual weighted scores with deterministic tie breakers",
    "availability": "Recheck current database stock/facts before selecting the requested number of products",
    "explanation": "Render product-specific explanations from actual component scores and evidence IDs",
    "validation": "Verify live facts, customer constraints, ranking arithmetic, references, and grounding",
    "response": "Render the final answer and atomically save validated recommendations, or report a real failure",
}


def after_node(name, state):
    if state.get("error"):
        return "response"
    if name == "product_retrieval" and not state.get("retrieval", {}).get("items"):
        return "validation"
    if name == "availability" and not state.get("items"):
        return "validation"
    keys = list(AGENTS)
    return keys[keys.index(name) + 1]


def build_workflow(runtime):
    graph = StateGraph(WorkflowState)
    def node_for(name):
        def node(state: WorkflowState):
            return runtime.execute(name, state)
        return node
    names = list(AGENTS)
    for name in names:
        graph.add_node(name, node_for(name))
    graph.add_edge(START, "supervisor")
    for index, name in enumerate(names[:-1]):
        targets = {names[index + 1], "response"}
        if name in {"product_retrieval", "availability"}:
            targets.add("validation")
        def route(state, name=name):
            return after_node(name, state)
        graph.add_conditional_edges(name, route, {target: target for target in sorted(targets)})
    graph.add_edge("response", END)
    return graph.compile()


def workflow_definition():
    graph = build_workflow(None).get_graph()
    return {"engine": "LangGraph", "version": version("langgraph"), "agent_mode": "deterministic_role_agents", "llm_used": False,
            "nodes": [{"name": key, "task": task} for key, task in AGENTS.items()],
            "edges": [{"source": edge.source, "target": edge.target, "conditional": edge.conditional} for edge in graph.edges],
            "mermaid": graph.draw_mermaid()}


class WorkflowRuntime:
    def __init__(self, engine, store, run_id):
        self.engine, self.store, self.run_id = engine, store, run_id
        self.tools = WorkflowTools(engine, store)

    def arguments(self, state, *, scored=False):
        result = {"request": state["request"], "profile": state.get("profile"), "context": state["context"]}
        if scored:
            result.update(items=state.get("items", []), active_weights=state.get("active_weights", {}),
                          preference_basis=state.get("preference_basis", "not_scored"))
        return result

    def execute(self, name, state):
        with Session(self.engine) as session, session.begin():
            sequence = (session.scalar(select(func.max(WorkflowStep.sequence)).where(WorkflowStep.run_id == self.run_id)) or 0) + 1
            execution = AgentExecution(agent_name=name, status="running", tool_calls=[])
            session.add(execution)
            session.flush()
            execution_id = execution.id
            session.add(WorkflowStep(run_id=self.run_id, execution_id=execution_id, sequence=sequence))
        self.tools.calls = []
        failure = None
        try:
            update = getattr(self, name)(state)
            if not isinstance(update, dict):
                raise ValueError("A graph node must return a state-update dictionary")
            # Fail immediately if a node tries to put non-JSON or nonfinite values in state.
            json.dumps(update, allow_nan=False)
        except Exception as exc:
            failure = safe_error(exc)
            update = {"error": f"{name}: {failure}"}
            if name == "response":
                update["output"] = self.failure_output({**state, "error": update["error"]})
        update["executed_agents"] = [name]
        checkpoint = {**state, **update,
                      "warnings": state.get("warnings", []) + update.get("warnings", []),
                      "executed_agents": state.get("executed_agents", []) + [name]}
        with Session(self.engine) as session, session.begin():
            execution = session.get(AgentExecution, execution_id)
            execution.status, execution.finished_at = ("failed" if failure else "completed"), utc_now()
            execution.tool_calls, execution.error = list(self.tools.calls), failure
            counts = {key: len(update[key]) for key in ("candidates", "ranked", "items") if key in update}
            execution.output_summary = json.dumps({"updated_state_fields": sorted(update), "counts": counts}, sort_keys=True)
            run = session.get(WorkflowRun, self.run_id)
            run.state = checkpoint
            if name == "response":
                run.status, run.finished_at = ("failed" if checkpoint.get("error") else "completed"), utc_now()
                run.output, run.error = checkpoint.get("output"), checkpoint.get("error")
        return update

    def supervisor(self, state):
        from retailrag.workflow_schemas import WorkflowRequest
        request = WorkflowRequest.model_validate(state["request"])
        warnings = []
        if not request.strict_budget:
            warnings.append("Budget is a soft ranking preference; products outside its bounds may be returned.")
        if not request.available_only:
            warnings.append("Availability filtering is disabled; out-of-stock products may be returned.")
        if request.retrieval_strategy == "content" or request.mode != "context_aware" or not request.strict_budget:
            selected, reason = "content", "Request uses content retrieval for its selected mode/budget policy"
        else:
            try:
                status = self.tools.call("get_rag_status", {})
                ready = status["status"] in {"ready", "stale"} and status["indexed_products"] > 0
            except Exception:
                ready = False
                if request.retrieval_strategy == "rag":
                    raise
            if ready:
                selected, reason = "rag", "A persisted vector index is available for the contextual query"
            elif request.retrieval_strategy == "rag":
                raise ValueError("Explicit RAG retrieval requires an ingested usable index")
            else:
                selected, reason = "content", "The vector index is unavailable or not ingested"
                warnings.append("Vector retrieval is not ready; the supervisor selected deterministic content fallback.")
        return {"plan": {"requested_strategy": request.retrieval_strategy, "selected_strategy": selected, "reason": reason}, "warnings": warnings}

    def query_understanding(self, state):
        result = self.tools.call("understand_query", {"request": state["request"], "profile": None})
        return result

    def customer_context(self, state):
        request = state["request"]
        if request.get("customer_id"):
            profile = self.tools.call("get_customer_profile", {"customer_id": request["customer_id"], "channel": request["channel"]})
            history = self.tools.call("get_customer_history", {"customer_id": request["customer_id"], "limit": 5})
            resolved = self.tools.call("understand_query", {"request": request, "profile": profile})
            return {"profile": profile, "customer_history": history, "context": resolved["context"], "warnings": resolved["warnings"]}
        baseline = self.tools.call("get_catalog_context", {})
        return {"profile": None, "plan": {**state["plan"], "anonymous_catalog_baseline": baseline}}

    def product_retrieval(self, state):
        warnings = []
        source = state["plan"]["selected_strategy"]
        if source == "rag":
            try:
                result = self.tools.call("retrieve_product_documents", self.arguments(state))
            except Exception:
                if state["request"]["retrieval_strategy"] != "auto":
                    raise
                warnings.append("Chroma retrieval failed; deterministic content fallback was used without relaxing filters.")
                source = "content"
                result = self.tools.call("search_products", self.arguments(state))
        else:
            result = self.tools.call("search_products", self.arguments(state))
        return {"retrieval": {**result, "source": source}, "warnings": warnings + result["warnings"]}

    def recommendation(self, state):
        arguments = self.arguments(state)
        arguments["items"] = state["retrieval"]["items"]
        result = self.tools.call("score_recommendation_candidates", arguments)
        return {"candidates": result["items"], "active_weights": result["active_weights"], "preference_basis": result["preference_basis"]}

    def product_ranking(self, state):
        result = self.tools.call("rank_recommendations", {"items": state["candidates"]})
        return {"ranked": result["items"]}

    def availability(self, state):
        arguments = self.arguments(state)
        arguments["items"] = state["ranked"]
        result = self.tools.call("check_product_availability", arguments)
        items = result["items"][:state["request"]["limit"]]
        for rank, item in enumerate(items, start=1):
            item["rank"] = rank
        warnings = [f"Live availability/fact recheck excluded {len(result['rejected_product_ids'])} changed or unavailable products."] if result["rejected_product_ids"] else []
        return {"items": items, "warnings": warnings}

    def explanation(self, state):
        return {"items": self.tools.call("explain_recommendations", self.arguments(state, scored=True))["items"]}

    def validation(self, state):
        result = self.tools.call("validate_recommendations", self.arguments(state, scored=True))
        return {"validation": result}

    def failure_output(self, state):
        request = state["request"]
        return WorkflowOutput(run_id=self.run_id, mode=request["mode"], query=request["query"], customer_id=request.get("customer_id"),
                              channel=request["channel"], message="Workflow failed; no unverified recommendation was saved.",
                              answer="Workflow failed. Inspect the actual execution trace and correct the request or unavailable service.",
                              warnings=list(dict.fromkeys(state.get("warnings", []))), context=state.get("context"), profile=state.get("profile"),
                              active_weights={}, preference_basis="not_returned", retrieval_source=state.get("retrieval", {}).get("source", "not_executed"),
                              index_generation=state.get("retrieval", {}).get("index_generation"), validation={"valid": False}, references=[], items=[]).model_dump(mode="json")

    def response(self, state):
        if state.get("error"):
            return {"output": self.failure_output(state)}
        request, items = state["request"], state.get("items", [])
        if not state.get("validation", {}).get("valid"):
            raise ValueError("Final response requires successful validation")
        lines = ["Deterministic LangGraph agent workflow; no LLM was called."]
        for item in items:
            product = item["product"]
            lines.append(f"{item['rank']}. [{product['id']}] {product['name']} — {product['currency']} {product['price']} — " +
                         ("in stock" if product["available"] else "out of stock") + ". " + item["explanation"])
        if not items:
            lines.append("No products match the current evidence and requested constraints. No filters were relaxed.")
        output = WorkflowOutput(run_id=self.run_id, mode=request["mode"], query=request["query"], customer_id=request.get("customer_id"),
                                channel=request["channel"], message=lines[0] if items else lines[-1], answer="\n".join(lines),
                                warnings=list(dict.fromkeys(state.get("warnings", []))), context=state["context"], profile=state.get("profile"),
                                active_weights=state.get("active_weights", {}), preference_basis=state.get("preference_basis", "not_scored"),
                                retrieval_source=state["retrieval"]["source"], index_generation=state["retrieval"].get("index_generation"),
                                validation=state["validation"], references=[item["product"]["id"] for item in items], items=items)
        saved = self.tools.call("save_recommendation", {"run_id": self.run_id, "request": request, "output": output.model_dump(mode="json")})
        return {"output": saved["output"]}


def run_workflow(engine, store, request):
    run_id = uuid.uuid4().hex
    initial = {"run_id": run_id, "request": request.model_dump(mode="json"), "warnings": [], "executed_agents": [], "error": None}
    with Session(engine) as session, session.begin():
        session.add(WorkflowRun(id=run_id, status="running", request=initial["request"], state=initial))
    runtime = WorkflowRuntime(engine, store, run_id)
    try:
        build_workflow(runtime).invoke(initial, config={"recursion_limit": 20})
    except Exception as exc:
        # Infrastructure/graph failures are persisted too, without pretending that
        # unexecuted nodes ran or fabricating a recommendation result.
        with Session(engine) as session, session.begin():
            run = session.get(WorkflowRun, run_id)
            run.status, run.finished_at, run.error = "failed", utc_now(), safe_error(exc)
            execution_ids = select(WorkflowStep.execution_id).where(WorkflowStep.run_id == run_id)
            for execution in session.scalars(select(AgentExecution).where(AgentExecution.id.in_(execution_ids), AgentExecution.status == "running")):
                execution.status, execution.finished_at, execution.error = "failed", utc_now(), run.error
            if run.output is None:
                run.output = runtime.failure_output({**initial, **run.state, "error": run.error})
    with Session(engine) as session:
        return read_workflow_run(session, run_id)
