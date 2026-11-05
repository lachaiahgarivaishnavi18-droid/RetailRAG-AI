"""Context Cart shopping views. Uses existing HTTP contracts; no backend writes on render."""

from datetime import datetime
from time import perf_counter

import pandas as pd
import streamlit as st

from retailrag.dashboard_ui import chart
from retailrag.product_photos import render_product_photo


PRIMARY = {"Overview": "Dashboard", "Product Discovery": "Product Discovery",
           "AI Shopping Assistant": "AI Shopping Assistant", "AI Recommendations": "Recommendations",
           "Product Comparison": "Product Comparison", "Inventory & Store Availability": "Inventory & Store Availability",
           "Evaluation Dashboard": "Evaluation Dashboard", "Settings": "Settings", "About": "About"}
RESEARCH = ["Product Catalog", "Customer Context", "RAG Search", "Agent Workflow", "Omnichannel Analytics", "Tool Explorer", "Recommendation History", "Document Workspace"]
SUGGESTIONS = ["Wireless headphones under INR 3000", "Running shoes under INR 3500", "A backpack for everyday travel"]


def go(page, query=None):
    st.session_state["cc_navigation"] = page
    st.session_state["cc_research"] = None
    if query is not None:
        st.session_state["discovery_query"] = query
        natural = any(token in query.casefold() for token in ("under", "for ", "₹", "inr"))
        st.session_state["cc_discovery_natural"] = natural
        st.session_state["cc_auto_discover"] = natural


def shell():
    st.sidebar.markdown('<div class="cc-brand"><span class="cc-logo">C<span>c</span></span><div>Context Cart<small>INTELLIGENT SHOPPING</small></div></div>', unsafe_allow_html=True)
    st.sidebar.caption("WORKSPACE")
    st.sidebar.radio("Main navigation", list(PRIMARY), format_func=PRIMARY.get, key="cc_navigation",
                     label_visibility="collapsed", on_change=lambda: st.session_state.update(cc_research=None))
    with st.sidebar.expander("Research workspace", icon=":material/science:"):
        st.radio("Research tools", RESEARCH, index=None, key="cc_research",
                 on_change=lambda: st.session_state.update(cc_navigation=None))
    st.sidebar.toggle("Dark mode", key="dark_mode")
    st.sidebar.markdown('<div class="cc-sidebar-note"><b>Built on evidence.</b><br>Discover. Compare. Decide.<br><small>Synthetic retail demonstration</small></div>', unsafe_allow_html=True)
    return st.session_state.get("cc_research") or st.session_state.get("cc_navigation") or "Overview"


def all_products(get):
    """Fetch all pages so client-side rating/category facets do not hide matches."""
    rows, offset = [], 0
    while True:
        page = get("/products", limit=100, offset=offset)
        if page is None:
            return None
        rows.extend(page["items"])
        offset += len(page["items"])
        if offset >= page["total"] or not page["items"]:
            return rows


def cards(products, prefix, evidence=None):
    evidence = evidence or {}
    for offset in range(0, len(products), 3):
        for column, product in zip(st.columns(3), products[offset:offset + 3]):
            with column.container(border=True):
                render_product_photo(product)
                st.caption(f"{product['category'].upper()}  /  {product['brand']}")
                st.subheader(product["name"])
                st.markdown(f"**₹{float(product['price']):,.0f}**　 ·　★ {product['rating']:.1f}")
                st.caption(f"{product['stock_quantity']} in stock" if product["available"] else "Out of stock")
                st.write(product["description"])
                item = evidence.get(product["id"])
                if item:
                    score = item.get("relevance_score", item.get("score"))
                    if score is not None:
                        st.caption(f"Match score {score:.3f} · ranking signal")
                        st.session_state.setdefault("cc_scores", {})[product["id"]] = score
                    st.write(item.get("explanation", ""))
                left, right = st.columns(2)
                selected = product["id"] in st.session_state.get("cc_compare", [])
                if left.button("Added" if selected else "Compare", icon=":material/compare_arrows:", key=f"{prefix}_compare_{product['id']}", disabled=selected, width="stretch"):
                    ids = st.session_state.setdefault("cc_compare", [])
                    if len(ids) >= 4:
                        st.warning("Compare up to four products. Remove one on Product Comparison first.")
                    else:
                        ids.append(product["id"])
                        st.rerun()
                if right.button("Details", icon=":material/arrow_outward:", key=f"{prefix}_details_{product['id']}", width="stretch"):
                    st.session_state[f"{prefix}_detail"] = product["id"]
                if st.session_state.get(f"{prefix}_detail") == product["id"]:
                    with st.expander("Specifications & provenance", expanded=True):
                        render_product_photo(product, detail=True)
                        st.write("Features: " + (", ".join(product["features"]) or "Not specified"))
                        st.json(product["attributes"])
                        st.caption(f"{product['id']} · {product['source']}")


def dashboard(get):
    st.markdown('<div class="cc-eyebrow">YOUR PERSONAL SHOPPING WORKSPACE</div>', unsafe_allow_html=True)
    st.title("Discover Products Smarter with AI")
    st.write("Find your next great match with context-aware recommendations, grounded in product evidence.")
    overview, products = get("/analytics/overview"), all_products(get)
    if overview is None or products is None:
        return
    totals = overview["totals"]
    st.caption("Agentic RAG-powered discovery · Local synthetic catalog · INR pricing")
    for column, label, value in zip(st.columns(4), ["Total Products", "Product Categories", "Total Recommendations", "Active Sessions"],
                                    [len(products), len({p["category"] for p in products}), totals["recommendations"], "Not tracked"]):
        column.metric(label, value)
    st.caption("Session analytics are not instrumented. Shopping activity below comes from stored application records.")
    with st.container(border=True):
        st.subheader("What are you looking for today?")
        with st.form("home_discovery"):
            query = st.text_input("Discover products", placeholder="Try ‘wireless headphones for travel under ₹3,000’", label_visibility="collapsed")
            if st.form_submit_button("Explore products", icon=":material/search:", type="primary"):
                st.session_state["cc_pending_discovery"] = query
                st.rerun()
        st.caption("A LITTLE INSPIRATION")
        for col, suggestion in zip(st.columns(3), SUGGESTIONS):
            col.button(suggestion, key=f"home_{suggestion}", on_click=go, args=("Product Discovery", suggestion), width="stretch")
    left, right = st.columns([3, 1])
    left.subheader("Trending in your catalog")
    right.button("View all products", on_click=go, args=("Product Discovery",), icon=":material/arrow_forward:", width="stretch")
    st.caption("Most recorded interactions · Synthetic shopping activity")
    by_id = {product["id"]: product for product in products}
    trending = [by_id[row["product_id"]] for row in overview["popular_products"][:3] if row["product_id"] in by_id]
    if trending:
        cards(trending, "trending")
    else:
        st.info("Trending products appear after shopping interactions are recorded.")
    left, right = st.columns([1.5, 1])
    with left.container(border=True):
        st.subheader("Recent recommendation activity")
        if overview["recent_recommendations"]:
            st.dataframe(overview["recent_recommendations"], hide_index=True, width="stretch")
        else:
            st.info("Your recommendation history starts with your first shopping request.")
    with right.container(border=True):
        st.subheader("Your catalog, at a glance", anchor=False)
        st.caption("AI-POWERED INSIGHTS · EVIDENCE SUMMARY")
        popular = overview["popular_categories"]
        st.write(f"{popular[0]['category']} leads recorded category activity." if popular else "No category activity recorded yet.")
        st.write(f"{overview['inventory']['available']} products are currently available.")
        st.write("Use the AI Shopping Assistant to explore product evidence and understand each match.")
        st.caption("These summaries are calculated from records; no LLM call is made on this page.")


def discovery(get, post):
    st.caption("A better match starts with a little context. Search the catalog or describe what you need.")
    products = all_products(get)
    if products is None:
        return
    if not products:
        st.info("Your catalog is empty. Import products to start discovering.")
        return
    with st.form("discovery_filters"):
        query = st.text_input("What can we help you find?", key="discovery_query", placeholder="Lightweight wireless headphones for travel under ₹5,000")
        natural = st.toggle("Use natural language discovery", value=False, key="cc_discovery_natural")
        cols = st.columns(3)
        category = cols[0].selectbox("Category", ["All categories", *sorted({p["category"] for p in products})])
        brand = cols[1].selectbox("Brand", ["All brands", *sorted({p["brand"] for p in products})])
        rating = cols[2].selectbox("Minimum rating", [0.0, 3.0, 4.0, 4.5], format_func=lambda v: "Any rating" if not v else f"{v}+ stars")
        cols = st.columns(3)
        minimum = cols[0].number_input("Minimum price (INR)", min_value=0.0, value=0.0, step=100.0)
        maximum = cols[1].number_input("Maximum price (INR)", min_value=0.0, value=max(float(p["price"]) for p in products), step=100.0)
        availability = cols[2].selectbox("Availability", ["All products", "In stock", "Out of stock"])
        sort = st.selectbox("Sort products", ["Recommended order", "Price: low to high", "Price: high to low", "Highest rated"])
        submitted = st.form_submit_button("Discover products", icon=":material/search:", type="primary")
    if minimum > maximum:
        st.error("Minimum price must not exceed maximum price.")
        return
    evidence = {}
    auto_search = st.session_state.pop("cc_auto_discover", False)
    if natural and (submitted or auto_search):
        if not query.strip():
            st.warning("Describe what you need before searching with natural language.")
            return
        payload = {"query": query.strip(), "available_only": availability == "In stock", "limit": 20}
        # Untouched catalog-wide controls must not override a budget in the query.
        if minimum > 0:
            payload["min_price"] = f"{minimum:.2f}"
        if maximum < max(float(p["price"]) for p in products):
            payload["max_price"] = f"{maximum:.2f}"
        if category != "All categories":
            payload["category"] = category
        if brand != "All brands":
            payload["brand"] = brand
        with st.spinner("Finding grounded product matches…"):
            result = post("/rag/search", payload, operation="RAG search")
        st.session_state["cc_discovery_result"] = {"filters": (query, category, brand, minimum, maximum, availability), "result": result}
    if natural:
        saved = st.session_state.get("cc_discovery_result", {})
        if saved.get("filters") != (query, category, brand, minimum, maximum, availability):
            st.info("Submit your shopping request to retrieve matching product evidence.")
            return
        result = saved.get("result")
        if result is None:
            return
        for warning in result["warnings"]:
            st.warning(warning)
        st.caption(f"Grounded retrieval · {result['generation']} · LLM used: {result['llm_used']}")
        evidence = {item["product"]["id"]: item for item in result["items"]}
        products = [item["product"] for item in result["items"]]
        st.caption("Retrieval returns up to 20 candidates; rating and out-of-stock selection are applied to those candidates.")
    else:
        words = query.casefold().split()
        products = [p for p in products if all(word in " ".join([p["name"], p["description"], p["brand"], p["category"], *p["features"]]).casefold() for word in words)]
    products = [p for p in products if minimum <= float(p["price"]) <= maximum and float(p["rating"]) >= rating
                and (category == "All categories" or p["category"] == category) and (brand == "All brands" or p["brand"] == brand)
                and (availability == "All products" or p["available"] == (availability == "In stock"))]
    if sort != "Recommended order":
        products.sort(key=lambda p: float(p["rating"] if sort == "Highest rated" else p["price"]), reverse=sort != "Price: low to high")
    st.subheader(f"{len(products)} products to explore")
    if not products:
        st.info("No products match these filters. Try a wider budget or another category.")
        return
    page = st.number_input("Results page", min_value=1, max_value=max(1, (len(products) + 8) // 9), value=1, step=1, key="discovery_page")
    cards(products[(page-1)*9:page*9], "discovery", evidence)


def assistant(get, post):
    st.caption("Your product research companion. Every match links back to catalog evidence.")
    st.info("Uses the existing RAG search API. Conversation is stored in this browser session; each query is retrieved independently. No dedicated chat API is available.")
    cols = st.columns(3)
    for col, query in zip(cols, SUGGESTIONS):
        col.button(query, key=f"ask_{query}", on_click=lambda q=query: st.session_state.update(cc_chat_draft=q), width="stretch")
    controls = st.columns([1, 2])
    channel = controls[0].selectbox("Shopping channel", ["ecommerce", "mobile", "store"], key="cc_chat_channel")
    customers = get("/customers", limit=100)
    names = {p["id"]: p["name"] for p in customers["items"]} if customers else {}
    customer = controls[1].selectbox("Personalize for", [None, *names], format_func=lambda v: names.get(v, "Guest shopper"))
    if st.button("Clear conversation", icon=":material/delete_sweep:"):
        st.session_state["cc_messages"] = []
    with st.form("cc_chat", clear_on_submit=False):
        query = st.text_input("Your shopping question", key="cc_chat_draft", placeholder="What wireless headphones fit a ₹3,000 budget?", max_chars=2000)
        send = st.form_submit_button("Send message", icon=":material/arrow_upward:", type="primary")
    messages = st.session_state.setdefault("cc_messages", [])
    if send:
        if not query.strip():
            st.warning("Enter a shopping question to continue.")
        else:
            started = perf_counter()
            with st.spinner("Searching product knowledge and checking your preferences…"):
                result = post("/rag/search", {"query": query.strip(), "channel": channel, "customer_id": customer}, operation="RAG search")
            if result is not None:
                messages.append({"query": query.strip(), "result": result, "latency_ms": (perf_counter()-started)*1000})
                st.session_state["cc_latency"] = [*st.session_state.get("cc_latency", []), messages[-1]["latency_ms"]][-100:]
    if not messages:
        st.markdown("### A thoughtful answer starts here")
        st.write("Tell me your budget, what matters to you, and where you plan to use it.")
    for index, message in enumerate(messages):
        with st.chat_message("user", avatar=":material/person:"):
            st.write(message["query"])
        with st.chat_message("assistant", avatar=":material/auto_awesome:"):
            result = message["result"]
            st.write(result["answer"])
            st.caption(f"{result['generation']} · LLM used: {result['llm_used']} · {message['latency_ms']:.0f} ms client round trip")
            for warning in result["warnings"]:
                st.warning(warning)
            cards([item["product"] for item in result["items"]], f"chat_{index}", {item["product"]["id"]: item for item in result["items"]})
            with st.expander("Sources & product evidence"):
                for item in result["items"]:
                    st.markdown(f"**{item['product']['id']} · {item['product']['name']}**")
                    st.caption(f"Document {item['document_id']} · cosine similarity {item['similarity_score']:.3f}")
                    st.write(item["document"])
                if not result["items"]:
                    st.caption("No retrieved documents matched this request.")


def comparison(get):
    st.caption("Keep the facts side by side. Compare up to four products from your catalog.")
    products = all_products(get)
    if products is None:
        return
    by_id = {p["id"]: p for p in products}
    st.session_state["cc_compare"] = [i for i in st.session_state.get("cc_compare", []) if i in by_id]
    selected = st.multiselect("Products to compare", list(by_id), format_func=lambda v: by_id[v]["name"], key="cc_compare", max_selections=4)
    if len(selected) < 2:
        st.info("Choose at least two products, or add them from Product Discovery.")
        return
    scores = st.session_state.get("cc_scores", {})
    rows = []
    for pid in selected:
        p = by_id[pid]
        rows.append({"Product ID": pid, "Product": p["name"], "Price (INR)": f"{float(p['price']):,.2f}", "Brand": p["brand"],
                     "Category": p["category"], "Rating": p["rating"], "Availability": f"{p['stock_quantity']} in stock" if p["available"] else "Out of stock",
                     "Features": ", ".join(p["features"]), "Specifications": "; ".join(f"{k}: {v}" for k,v in p["attributes"].items()),
                     "Recommendation score": f"{scores[pid]:.3f}" if pid in scores else "Not generated in this session"})
    st.dataframe(pd.DataFrame(rows).set_index("Product").T, width="stretch")
    st.caption("Scores are from the last displayed recommendation or retrieval in this session; different requests may use different scoring contexts.")
    cards([by_id[pid] for pid in selected], "comparison")


def inventory(get):
    st.caption("A transparent view of current availability.")
    st.info("Inventory is shared catalog stock. Store-level locations, warehouse feeds, and reservations are not connected.")
    products = all_products(get)
    if products is None:
        return
    for col, label, value in zip(st.columns(3), ["Available products", "Out of stock", "Catalog units"], [sum(p["available"] for p in products), sum(not p["available"] for p in products), sum(p["stock_quantity"] for p in products)]):
        col.metric(label, value)
    state = st.selectbox("Stock status", ["All products", "In stock", "Out of stock"])
    rows = [{"Product ID": p["id"], "Product": p["name"], "Category": p["category"], "Price (INR)": p["price"], "Units": p["stock_quantity"], "Available": p["available"]} for p in products if state == "All products" or p["available"] == (state == "In stock")]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
        st.download_button("Export inventory", pd.DataFrame(rows).to_csv(index=False), "context-cart-inventory.csv", "text/csv", icon=":material/download:")
    else:
        st.info("No products match this stock status.")


def evaluation(get):
    st.caption("Measure what is recorded. Keep ranking signals separate from validated quality.")
    with st.container(border=True):
        st.subheader("Ranking quality benchmarks")
        for col, name in zip(st.columns(4), ["Precision@K", "Recall@K", "MRR", "NDCG@K"]):
            col.metric(name, "Unavailable")
        st.info("No evaluation API or labeled relevance judgments are available. These metrics cannot be computed from recommendation scores alone.")
    analytics, status, index = get("/analytics/recommendations"), get("/agents/status", limit=100), get("/rag/status")
    if analytics:
        left, right = st.columns(2)
        left.metric("Recorded recommendation runs", analytics["total_runs"])
        right.metric("Mean ranking score", f"{analytics['average_score']:.3f}")
        st.caption("Ranking scores are algorithmic relevance signals, not measured precision or human satisfaction.")
        chart(analytics["daily_trend"], "date", "runs", "Recommendation activity", kind="line", key="evaluation_trend")
    if index:
        with st.expander("RAG retrieval readiness", expanded=True):
            st.write(f"Index status: {index['status']}")
            st.json(index)
            st.caption("Index readiness is operational health; retrieval quality requires a labeled query/relevance benchmark.")
    if status:
        st.subheader("Agent execution performance")
        st.caption(f"Latest {len(status['items'])} of {status['total']} workflow records. Durations use persisted start/finish timestamps.")
        runs = []
        for row in status["items"]:
            duration = None
            if row.get("finished_at") and row.get("started_at"):
                duration = (datetime.fromisoformat(row["finished_at"]) - datetime.fromisoformat(row["started_at"])).total_seconds()*1000
            runs.append({"run_id": row["run_id"], "status": row["status"], "duration_ms": duration})
        if runs:
            st.dataframe(runs, hide_index=True, width="stretch")
            chart([r for r in runs if r["duration_ms"] is not None], "run_id", "duration_ms", "Recorded workflow latency", key="evaluation_latency")
        else:
            st.info("Run an agent workflow to populate execution performance.")
    latencies = st.session_state.get("cc_latency", [])
    st.subheader("Assistant response latency")
    if latencies:
        st.metric("Mean client round trip", f"{sum(latencies)/len(latencies):.0f} ms")
        st.caption(f"Last {len(latencies)} successful assistant requests in this browser session. Includes transport and server processing.")
    else:
        st.caption("No assistant requests measured in this browser session yet.")


def about():
    st.markdown("### Thoughtful shopping. Grounded intelligence.")
    st.write("Context Cart explores how customer context, product evidence, and coordinated agents can support omnichannel retail recommendations.")
    st.caption("AN AGENTIC RETRIEVAL-AUGMENTED GENERATION ARCHITECTURE FOR CONTEXT-AWARE PRODUCT RECOMMENDATION IN OMNICHANNEL RETAIL")
    for col, title, body in zip(st.columns(3), ["Understand context", "Retrieve evidence", "Explain the match"],
                               ["Shared preferences connect website, mobile, and store simulations.", "Chroma retrieves attributed documents using local LSA embeddings.", "TF-IDF ranking and deterministic LangGraph roles produce auditable results."]):
        with col.container(border=True):
            st.subheader(title)
            st.write(body)
    st.info("Academic demonstration using fictional products, customers, and shopping events. No real retailer, payment, fulfillment, or store inventory integration is connected.")
    st.write("Built with Streamlit, FastAPI, SQLAlchemy, scikit-learn, Chroma, LangChain, LangGraph, and Plotly.")
    st.caption("Recommendations and agents work without API credentials. Standalone RAG uses local answers without a key; auto mode can use configured OpenAI selection. DEMO_MODE=true keeps AI local.")
