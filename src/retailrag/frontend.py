"""Streamlit data workspace backed by FastAPI."""

import json
import uuid
import httpx
import streamlit as st

from retailrag.config import get_settings
from retailrag.dashboard_ui import apply_theme, catalog_editor, omnichannel_page, overview_details, product_cards
from retailrag import context_cart_ui as cart


def api_get(path: str, **params):
    settings = get_settings()
    try:
        response = httpx.get(f"{str(settings.api_base_url).rstrip('/')}{path}", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        st.error("Backend is unavailable or the request failed. Start FastAPI and check the requested filters.")
        return None


def api_post(path: str, payload: dict, *, operation="Recommendation", method="POST"):
    settings = get_settings()
    try:
        transport = httpx.put if method == "PUT" else httpx.post
        response = transport(f"{str(settings.api_base_url).rstrip('/')}{path}", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        body = {}
        try:
            body = exc.response.json()
            detail = body.get("detail", body.get("error", "Request rejected"))
        except ValueError:
            detail = "Request rejected"
        st.error(f"{operation} request failed: {detail}")
        if operation == "Tool execution" and isinstance(body, dict) and body.get("call_id"):
            return body
    except (httpx.HTTPError, ValueError):
        if operation == "Recommendation":
            st.error("Could not confirm the recommendation response. Check Recommendation History before retrying; the request may have been saved.")
        elif operation == "Agent workflow":
            st.error("Could not confirm the workflow response. Check Agent Workflow status before retrying; the run may still be executing or may already be saved.")
        elif operation == "Tool execution":
            st.error("Could not confirm the tool response. Inspect invocation history before retrying; reuse the same idempotency key for a save retry.")
        elif operation == "Shopping simulation":
            st.error("Could not confirm the simulation response. Inspect simulation history before retrying; the same journey request retains its retry key.")
        elif operation.startswith("Catalog"):
            st.error("Could not confirm the catalog update. Reload the product details before retrying.")
        else:
            st.error("Could not confirm the RAG response. Check index status before retrying ingestion.")
    return None


def show_recommendations(result):
    st.info(result["message"])
    for warning in result.get("warnings", []):
        st.warning(warning)
    if result.get("engine") in {"deterministic_tfidf", "langgraph_workflow"} and result.get("id") is not None:
        st.caption(f"Saved recommendation #{result['id']} · {result['channel']} · scores are ranking signals, not probabilities")
        st.caption(f"Prices and availability reflect generation time: {result['created_at']}.")
        with st.expander("Effective filters, profile, and ranking weights"):
            st.json({key: result[key] for key in ["context", "profile", "active_weights", "preference_basis"]})
    if not result["items"]:
        return
    rows = []
    for item in result["items"]:
        product = item["product"]
        rows.append({"Rank": item["rank"], "Product ID": product["id"], "Product": product["name"], "Brand": product["brand"],
                     "Category": product["category"], "Price (INR)": item.get("price_snapshot", product["price"]),
                     "Available": product["available"], "Similarity": item.get("similarity_score"),
                     "Relevance": item["relevance_score"], "Explanation": item["explanation"], "Source": product["source"]})
    st.dataframe(rows, hide_index=True, width="stretch")
    if st.toggle("Show recommendation cards", value=True, key=f"rec_cards_{result.get('id')}_{result.get('run_id', '')}"):
        cart.cards([item["product"] for item in result["items"]], f"recommendation_{result.get('id')}_{result.get('run_id', '')}",
                   {item["product"]["id"]: item for item in result["items"]})
    with st.expander("Full saved evidence"):
        st.json(result)


def recommendations():
    st.caption("Local TF-IDF recommendations. No LLM, RAG, or agent workflow is called. Demo data is synthetic.")
    customers = api_get("/customers", limit=100)
    if customers is None:
        return
    names = {row["id"]: f"{row['name']} ({row['id']})" for row in customers["items"]}
    with st.form("recommendation_request"):
        mode = st.selectbox("Recommendation type", ["context_aware", "personalized", "similar", "budget", "category", "brand", "new_customer"])
        customer_id = st.selectbox("Customer (optional)", [None, *names], format_func=lambda value: names.get(value, "Anonymous / new customer"))
        override = st.text_input("Customer ID (optional override)", key="rec_customer_override")
        query = st.text_area("Shopping request", placeholder="Wireless headphones under INR 3000")
        product_id = st.text_input("Source product ID (similar mode)")
        category = st.text_input("Category (optional exact filter)", key="rec_category")
        brand = st.text_input("Brand (optional exact filter)", key="rec_brand")
        use_budget = st.checkbox("Use explicit budget")
        left, right = st.columns(2)
        minimum = left.number_input("Minimum price (INR)", min_value=0.0, value=0.0, step=100.0)
        maximum = right.number_input("Maximum price (INR)", min_value=0.0, value=3000.0, step=100.0)
        strict_budget = st.checkbox("Enforce budget strictly", value=True)
        available_only = st.checkbox("In stock only", value=True, key="rec_stock")
        exclude_purchased = st.checkbox("Exclude previously purchased products")
        channel = st.selectbox("Shopping channel", ["ecommerce", "mobile", "store"])
        limit = st.number_input("Number of recommendations", min_value=1, max_value=50, value=5, step=1)
        submitted = st.form_submit_button("Generate Recommendations")
    if submitted:
        st.session_state.pop("last_recommendation", None)
        payload = {"mode": mode, "query": query, "customer_id": override.strip() or customer_id, "channel": channel,
                   "strict_budget": strict_budget, "available_only": available_only, "exclude_purchased": exclude_purchased, "limit": limit}
        if product_id.strip():
            payload["product_id"] = product_id.strip()
        if category.strip():
            payload["category"] = category.strip()
        if brand.strip():
            payload["brand"] = brand.strip()
        if use_budget:
            payload.update(min_price=f"{minimum:.2f}", max_price=f"{maximum:.2f}")
        with st.spinner("Ranking products and saving the recommendation…"):
            result = api_post("/recommendations", payload)
        if result is not None:
            st.session_state["last_recommendation"] = result
    if "last_recommendation" in st.session_state:
        show_recommendations(st.session_state["last_recommendation"])


def recommendation_history():
    customer = st.text_input("Filter by customer ID (optional)")
    channel = st.selectbox("Channel", ["all", "ecommerce", "mobile", "store"])
    page = st.number_input("History page", min_value=1, value=1, step=1)
    params = {"limit": 20, "offset": (page - 1) * 20}
    if customer.strip():
        params["customer_id"] = customer.strip()
    if channel != "all":
        params["channel"] = channel
    records = api_get("/recommendations", **params)
    if records is None:
        return
    st.write(f"{records['total']} saved recommendations")
    if not records["items"]:
        st.info("No recommendation history matches these filters.")
        return
    st.dataframe(records["items"], hide_index=True, width="stretch")
    selected = st.selectbox("Open saved recommendation", [row["id"] for row in records["items"]])
    result = api_get(f"/recommendations/{selected}")
    if result is not None:
        show_recommendations(result)


def rag_search():
    st.caption("Persistent Chroma retrieval with local latent-semantic embeddings. Demo product facts are synthetic.")
    status = api_get("/rag/status")
    if status is not None:
        with st.expander("Vector index status", expanded=status["status"] != "ready"):
            st.json(status)
    if st.button("Synchronize catalog index"):
        with st.spinner("Building and publishing the product index…"):
            result = api_post("/rag/ingest", {}, operation="RAG ingestion")
        if result is not None:
            st.success(f"Indexed {result['products']} products in {result['chunks']} chunks.")
            st.json(result)
            st.session_state.pop("rag_result", None)
    with st.form("rag_query"):
        query = st.text_area("RAG shopping query", placeholder="Wireless headphones under INR 3000")
        category = st.text_input("Category (optional)", key="rag_category")
        brand = st.text_input("Brand (optional)", key="rag_brand")
        customer_id = st.text_input("Customer ID (optional)", key="rag_customer")
        channel = st.selectbox("Shopping channel", ["ecommerce", "mobile", "store"], key="rag_channel")
        use_budget = st.checkbox("Apply explicit maximum price", key="rag_use_budget")
        maximum = st.number_input("Maximum price (INR)", min_value=0.0, value=3000.0, step=100.0, key="rag_maximum")
        available = st.checkbox("In stock only", value=True, key="rag_stock")
        submitted = st.form_submit_button("Search retrieved evidence")
    if submitted:
        st.session_state.pop("rag_result", None)
        payload = {"query": query, "channel": channel, "available_only": available}
        for field, value in [("category", category), ("brand", brand), ("customer_id", customer_id)]:
            if value.strip():
                payload[field] = value.strip()
        if use_budget:
            payload["max_price"] = f"{maximum:.2f}"
        with st.spinner("Retrieving and validating catalog evidence…"):
            result = api_post("/rag/search", payload, operation="RAG search")
        if result is not None:
            st.session_state["rag_result"] = result
    result = st.session_state.get("rag_result")
    if result is not None:
        st.caption(f"Generation: {result['generation']} · LLM used: {result['llm_used']} · LLM status: {result['llm_status']}")
        for warning in result["warnings"]:
            st.warning(warning)
        st.text(result["answer"])
        if result["items"]:
            st.dataframe([{"Product ID": item["product"]["id"], "Product": item["product"]["name"],
                           "Price (INR)": item["product"]["price"], "Available": item["product"]["available"],
                           "Similarity": item["similarity_score"], "Relevance": item["relevance_score"],
                           "Document ID": item["document_id"]} for item in result["items"]], hide_index=True, width="stretch")
            cart.cards([item["product"] for item in result["items"]], "rag_search", {item["product"]["id"]: item for item in result["items"]})
        else:
            st.info("No grounded product documents matched this request.")
        with st.expander("Retrieved documents, metadata, and effective filters"):
            st.json(result)


def catalog():
    st.caption("Prices are INR. Demo products are synthetic; provenance is included in each row.")
    with st.form("catalog_filters"):
        q = st.text_input("Search products")
        left, right = st.columns(2)
        category = left.text_input("Category (exact match, optional)")
        brand = right.text_input("Brand (exact match, optional)")
        budget_enabled = st.checkbox("Apply maximum price")
        budget = st.number_input("Maximum price (INR)", min_value=0.0, value=5000.0, step=100.0)
        available = st.checkbox("In stock only")
        sort = st.selectbox("Sort", ["name", "price_asc", "price_desc", "rating"])
        page = st.number_input("Page", min_value=1, value=1, step=1)
        st.form_submit_button("Search")
    params = {"q": q, "sort": sort, "limit": 20, "offset": (page - 1) * 20}
    if category.strip():
        params["category"] = category.strip()
    if brand.strip():
        params["brand"] = brand.strip()
    if budget_enabled:
        params["max_price"] = f"{budget:.2f}"
    if available:
        params["available"] = "true"
    result = api_get("/products", **params)
    if result is None:
        return
    st.write(f"{result['total']} matching products")
    if not result["items"]:
        st.info("No products match these filters.")
    else:
        st.dataframe(result["items"], hide_index=True, width="stretch")
        if st.toggle("Show product cards", value=True, key="catalog_cards"):
            product_cards(result["items"][:6])
            if len(result["items"]) > 6:
                st.caption("Showing six product cards from this page; the table includes every loaded result.")
    catalog_editor(api_get, api_post)


def agent_workflow():
    st.caption("Deterministic role agents executed by LangGraph. The trace contains actual node and tool executions.")
    definition = api_get("/agents/definition")
    if definition is None:
        return
    tasks = {node["name"]: node["task"] for node in definition["nodes"]}
    with st.expander("Compiled workflow definition"):
        st.write(f"{definition['engine']} {definition['version']} · {len(definition['nodes'])} agent nodes")
        st.dataframe(definition["nodes"], hide_index=True, width="stretch")
        st.code(definition["mermaid"], language="mermaid")
    with st.form("agent_workflow_request"):
        mode = st.selectbox("Workflow mode", ["context_aware", "personalized", "similar", "budget", "category", "brand", "new_customer"])
        query = st.text_area("Agent shopping request", placeholder="Wireless headphones under INR 3000")
        customer_id = st.text_input("Customer ID (optional)", key="agent_customer")
        product_id = st.text_input("Source product ID (similar mode)", key="agent_source_product")
        category = st.text_input("Category (optional)", key="agent_category")
        brand = st.text_input("Brand (optional)", key="agent_brand")
        strategy = st.selectbox("Retrieval strategy", ["auto", "rag", "content"])
        channel = st.selectbox("Shopping channel", ["ecommerce", "mobile", "store"], key="agent_channel")
        budget_enabled = st.checkbox("Apply explicit maximum price", key="agent_budget")
        maximum = st.number_input("Maximum price (INR)", min_value=0.0, value=3000.0, step=100.0, key="agent_maximum")
        available = st.checkbox("In stock only", value=True, key="agent_stock")
        exclude_purchased = st.checkbox("Exclude purchased products", key="agent_exclude_purchased")
        submitted = st.form_submit_button("Run Agent Workflow")
    if submitted:
        payload = {"mode": mode, "query": query, "retrieval_strategy": strategy, "channel": channel,
                   "available_only": available, "exclude_purchased": exclude_purchased}
        for field, value in [("customer_id", customer_id), ("product_id", product_id), ("category", category), ("brand", brand)]:
            if value.strip():
                payload[field] = value.strip()
        if budget_enabled:
            payload["max_price"] = f"{maximum:.2f}"
        with st.spinner("Executing the workflow and recording actual node/tool results…"):
            result = api_post("/agents/run", payload, operation="Agent workflow")
        if result is not None:
            st.session_state["last_workflow_run_id"] = result["run_id"]
    st.button("Refresh workflow status")
    history = api_get("/agents/status", limit=20)
    if history is None:
        return
    if not history["items"]:
        st.info("No agent workflows have been executed.")
        return
    ids = [row["run_id"] for row in history["items"]]
    latest = st.session_state.get("last_workflow_run_id")
    selected = st.selectbox("Inspect workflow run", ids, index=ids.index(latest) if latest in ids else 0)
    result = api_get(f"/agents/runs/{selected}")
    if result is None:
        return
    st.write(f"Run {selected} · {result['status']}")
    if result["error"]:
        st.error(result["error"])
    rows = [{"Sequence": step["sequence"], "Agent": step["agent"], "Task": tasks.get(step["agent"], ""),
             "Status": step["status"], "Duration (ms)": step["duration_ms"],
             "Tools": ", ".join(f"{call['name']} ({call['status']})" for call in step["tool_calls"]),
             "Output summary": step["output_summary"], "Error": step["error"]} for step in result["steps"]]
    st.subheader("Actual execution trace")
    st.dataframe(rows, hide_index=True, width="stretch")
    unexecuted = [name for name in tasks if name not in {step["agent"] for step in result["steps"]}]
    if unexecuted:
        st.caption("Not executed on this route: " + ", ".join(unexecuted))
    if result["output"]:
        st.text(result["output"]["answer"])
        show_recommendations(result["output"])
    with st.expander("Persisted tool calls and state checkpoint"):
        st.json(result)


def tool_explorer():
    st.caption("Execute published retail tools using validated identifiers and requests. Results come from actual backend data.")
    st.caption("Inspected results are snapshots at invocation time. Execute a new read to obtain current catalog facts.")
    catalog = api_get("/tools")
    if catalog is None:
        return
    tools = {item["name"]: item for item in catalog["items"]}
    name = st.selectbox("Tool", list(tools))
    selected = tools[name]
    st.write(selected["description"])
    st.caption(f"Business-data effect: {selected['effect']}. Every execution records an invocation audit.")
    if selected["effect"] == "write":
        st.info("This tool saves a recommendation. Keep its idempotency key when retrying the same request; use a new key for a new request.")
    with st.expander("Published input and output schemas"):
        st.json({"input": selected["input_schema"], "output": selected["output_schema"]})
    example = dict(selected["example_arguments"])
    if name == "save_recommendation":
        example["idempotency_key"] = st.session_state.setdefault("tool_save_key", uuid.uuid4().hex)
    with st.form(f"tool_execute_{name}"):
        text = st.text_area("Arguments (JSON object)", value=json.dumps(example, indent=2), key=f"tool_args_{name}", height=200)
        submitted = st.form_submit_button("Execute Tool")
    if submitted:
        try:
            arguments = json.loads(text)
            if not isinstance(arguments, dict):
                raise ValueError("Arguments must be an object")
            json.dumps(arguments, allow_nan=False)
        except (ValueError, TypeError):
            st.error("Enter a valid JSON object with finite values before executing the tool.")
        else:
            with st.spinner("Executing the tool and validating its result…"):
                result = api_post(f"/tools/{name}/execute", {"arguments": arguments}, operation="Tool execution")
            if result is not None and result.get("call_id"):
                st.session_state["last_tool_call_id"] = result["call_id"]
                st.session_state["last_tool_response"] = result
    if st.session_state.get("last_tool_response"):
        with st.expander("Last execution response", expanded=True):
            st.json(st.session_state["last_tool_response"])
    st.button("Refresh tool invocation history")
    history = api_get("/tools/invocations", limit=20)
    if history is None:
        return
    if not history["items"]:
        st.info("No public tools have been executed.")
        return
    st.dataframe(history["items"], hide_index=True, width="stretch")
    ids = [item["call_id"] for item in history["items"]]
    last = st.session_state.get("last_tool_call_id")
    call_id = st.selectbox("Inspect tool invocation", ids, index=ids.index(last) if last in ids else 0)
    detail = api_get(f"/tools/invocations/{call_id}")
    if detail is not None:
        st.json(detail)


def customer_context():
    customers = api_get("/customers", limit=100)
    if customers is None:
        return
    if not customers["items"]:
        st.info("No customers loaded. Import a dataset first.")
        return
    names = {row["id"]: f"{row['name']} ({row['id']})" for row in customers["items"]}
    if customers["total"] > 100:
        st.caption("Showing the first 100 customers. Enter another customer ID below to inspect its profile.")
    selected = st.selectbox("Customer", list(names), format_func=names.get)
    override = st.text_input("Customer ID (optional override)")
    customer_id = override.strip() or selected
    profile = api_get(f"/customers/{customer_id}")
    if profile is None:
        return
    st.json(profile)
    left, right = st.columns(2)
    left.metric("Preferred budget (INR)", f"{float(profile['budget_min']):,.0f} – {float(profile['budget_max']):,.0f}")
    right.caption("Declared categories: " + (", ".join(profile["preferred_categories"]) or "Not declared"))
    right.caption("Declared brands: " + (", ".join(profile["preferred_brands"]) or "Not declared"))
    channel = st.selectbox("History channel", ["all", "ecommerce", "mobile", "store"])
    page = st.number_input("History page", min_value=1, value=1, step=1)
    params = {"limit": 20, "offset": (page - 1) * 20}
    if channel != "all":
        params["channel"] = channel
    history = api_get(f"/customers/{customer_id}/history", **params)
    if history is not None:
        st.write(f"{history['total']} interactions")
        if history["items"]:
            st.dataframe(history["items"], hide_index=True, width="stretch")
        else:
            st.info("No interaction history for this customer and channel.")
    preferences = api_get(f"/customers/{customer_id}/preferences", **({"channel": channel} if channel != "all" else {}))
    if preferences is not None:
        with st.expander("Inferred shopping preferences"):
            st.json(preferences)
        st.caption("Observed purchase price statistics use current catalog prices; historical transaction prices were not recorded.")
    previous = api_get("/recommendations", customer_id=customer_id, limit=5)
    if previous and previous["items"]:
        with st.expander("Previous recommendations"):
            st.dataframe(previous["items"], hide_index=True, width="stretch")


def main() -> None:
    settings = get_settings()
    st.set_page_config(page_title="Context Cart · Intelligent Shopping", page_icon=":material/shopping_bag:", layout="wide", initial_sidebar_state="auto")
    if "cc_pending_discovery" in st.session_state:
        cart.go("Product Discovery", st.session_state.pop("cc_pending_discovery"))
    page = cart.shell()
    apply_theme(st.session_state.get("dark_mode", False))
    if page == "Overview":
        cart.dashboard(api_get)
        return
    st.caption("CONTEXT CART  /  " + ("RESEARCH WORKSPACE" if page in cart.RESEARCH else "SHOPPING WORKSPACE"))
    st.title(cart.PRIMARY.get(page, page))
    if page == "Document Workspace":
        document_workspace()
        return
    if page == "Product Discovery":
        cart.discovery(api_get, api_post)
        return
    if page == "AI Shopping Assistant":
        cart.assistant(api_get, api_post)
        return
    if page == "Product Comparison":
        cart.comparison(api_get)
        return
    if page == "Inventory & Store Availability":
        cart.inventory(api_get)
        return
    if page == "Evaluation Dashboard":
        cart.evaluation(api_get)
        return
    if page == "About":
        cart.about()
        return

    if page == "Settings":
        st.subheader("Runtime configuration")
        st.write("Environment:", settings.environment)
        st.write("Backend URL:", str(settings.api_base_url))
        st.caption("Edit .env and restart the services to apply configuration changes.")
        st.info("Recommendations use local TF-IDF. RAG answers work locally without keys. Auto mode uses OpenAI when configured; DEMO_MODE=true keeps all AI local.")
        backend = api_get("/settings")
        if backend is not None:
            st.subheader("Backend capabilities")
            st.json(backend)
        ready = api_get("/ready")
        if ready is not None and ready["status"] == "ready":
            st.success("Database connected")
        st.subheader("Index maintenance")
        if st.button("Synchronize catalog documents"):
            result = api_post("/rag/ingest", {}, operation="RAG ingestion")
            if result is not None:
                st.success(f"Synchronized {result['products']} products and {result['chunks']} chunks.")
        st.caption("Configuration is read-only in this local application. Update .env and restart the backend to change generation mode or credentials. Secrets are never displayed.")
        return

    if page == "Product Catalog":
        catalog()
        return
    if page == "Customer Context":
        customer_context()
        return
    if page == "AI Recommendations":
        recommendations()
        return
    if page == "Recommendation History":
        recommendation_history()
        return
    if page == "RAG Search":
        rag_search()
        return
    if page == "Agent Workflow":
        agent_workflow()
        return
    if page == "Tool Explorer":
        tool_explorer()
        return
    if page == "Omnichannel Analytics":
        omnichannel_page(api_get, api_post)
        return


def document_workspace():
    st.caption("Local document search and extractive chat. No API keys. Supports UTF-8 TXT, Markdown, CSV and JSON; PDF/OCR is not supported.")
    if st.button("Process sample document"):
        if api_post("/documents/sample", {}, operation="Document processing"):
            st.success("Sample store policy processed")
    uploaded = st.file_uploader("Upload a document", type=["txt", "md", "csv", "json"])
    if st.button("Process uploaded document", disabled=uploaded is None):
        try:
            if uploaded.size > 2_000_000:
                st.error("Maximum document size is 2 MB")
            elif api_post("/documents/upload", {"filename": uploaded.name, "content": uploaded.getvalue().decode("utf-8-sig")}, operation="Document processing"):
                st.success("Document processed locally")
        except UnicodeDecodeError:
            st.error("Please upload a UTF-8 text document")
    documents = api_get("/documents")
    if documents and documents["items"]:
        st.dataframe(documents["items"], hide_index=True, width="stretch")
    messages = st.session_state.setdefault("document_messages", [])
    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    question = st.chat_input("Ask about your uploaded documents", key="document_question")
    if question:
        result = api_post("/documents/search", {"query": question}, operation="Document search")
        if result:
            messages.extend([{"role": "user", "content": question}, {"role": "assistant", "content": result["answer"]}])
            st.rerun()


if __name__ == "__main__":
    main()
