"""Professional Streamlit presentation of real analytics and shopping simulations."""

import json
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st
from retailrag.product_photos import render_product_photo

COLORS = ["#087F8C", "#3C6EEB", "#7894B0", "#D6A14D"]
CHANNEL_LABELS = {"ecommerce": "E-commerce website", "mobile": "Mobile shopping app", "store": "Physical retail store"}


def apply_theme(dark):
    background, surface, text, muted, border = ("#0B1120", "#111C32", "#E8EEF9", "#A8BAD2", "#253552") if dark else ("#FFFFFF", "#FFFFFF", "#14213D", "#586B81", "#E3E9F2")
    st.markdown(f"""<style>
    .stApp {{background:{background};color:{text};font-family:Inter,'Segoe UI',sans-serif;}}
    [data-testid="stHeader"] {{background:transparent;}}
    .block-container {{max-width:1440px;padding-top:2.6rem;padding-bottom:3rem;}}
    h1 {{font-size:2.3rem!important;font-weight:750!important;letter-spacing:-.055rem;}}
    h2,h3 {{letter-spacing:-.02rem;}}
    [data-testid="stSidebar"] {{background:#101C37;border-right:1px solid #23345A;}}
    [data-testid="stSidebar"] * {{color:#E4ECFF;}}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{color:#A4B5D7;}}
    [data-testid="stSidebar"] [role="radiogroup"] label {{padding:.48rem .6rem;border-radius:10px;}}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {{background:#1D315B;}}
    [data-testid="stMetric"] {{background:{surface};border:1px solid {border};border-radius:16px;padding:1.2rem;box-shadow:0 5px 20px #0B163207;}}
    [data-testid="stMetricValue"] {{font-weight:750;color:{text};}}
    [data-testid="stMetricLabel"], [data-testid="stCaptionContainer"] {{color:{muted};}}
    [data-testid="stForm"], [data-testid="stVerticalBlockBorderWrapper"] {{border-color:{border}!important;border-radius:16px;}}
    [data-testid="stForm"] {{background:{surface};padding:1.2rem;}}
    .stButton button, .stFormSubmitButton button {{border-radius:9px;border-color:{border};font-weight:600;transition:all .15s ease;}}
    .stButton button:hover, .stFormSubmitButton button:hover {{border-color:#4169E1;color:#4169E1;transform:translateY(-1px);}}
    [data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stNumberInput"] input {{background:{surface};color:{text};}}
    [data-baseweb="select"] > div {{background:{surface};color:{text};border-color:{border};}}
    [data-testid="stExpander"] {{border-color:{border};}}
    .block-container {{max-width:1480px;padding:3.2rem 3.4rem;}}
    [data-testid="stAppDeployButton"] {{display:none;}}
    [data-testid="stSidebar"] {{background:#102239;}}
    [data-testid="stSidebarContent"] {{padding-top:1.4rem;}}
    [data-testid="stSidebar"] h1 {{font-size:1.5rem!important;}}
    .cc-brand {{display:flex;gap:12px;align-items:center;font-weight:700;font-size:22px;letter-spacing:-.6px;margin:0 0 2.3rem;}}
    .cc-brand small {{display:block;font-size:9px;letter-spacing:1.8px;color:#94AFC4;font-weight:500;margin-top:4px;}}
    .cc-logo {{display:flex;align-items:center;justify-content:center;width:43px;height:43px;background:#128D98;border-radius:13px;font-size:26px;color:white;}}
    .cc-logo span {{font-size:18px;margin-left:-6px;margin-top:9px;}}
    [data-testid="stSidebar"] [role="radiogroup"] {{gap:.25rem;}}
    [data-testid="stSidebar"] [role="radiogroup"] label {{padding:.6rem .6rem!important;min-height:42px;border:1px solid transparent;transition:background .16s ease;}}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{background:#173C51;border-color:#286076;box-shadow:inset 3px 0 #39C4C0;}}
    [data-testid="stSidebar"] [role="radiogroup"] label p {{font-size:.88rem;}}
    [data-testid="stSidebar"] [role="radiogroup"]:has(input[value="8"]) label > div > div:first-child {{display:none;}}
    [data-testid="stSidebar"] [role="radiogroup"]:has(input[value="8"]) label > div::before {{font-family:'Material Symbols Rounded';font-size:20px;content:'circle' / '';margin-right:11px;color:#9AB3CA;}}
    [data-testid="stSidebar"] [role="radiogroup"]:has(input[value="8"]) label:has(input:checked) > div::before {{color:#58D5CD;}}
    [data-testid="stSidebar"] label:has(input[value="0"]) > div::before {{content:'space_dashboard' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="1"]) > div::before {{content:'search' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="2"]) > div::before {{content:'auto_awesome' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="3"]) > div::before {{content:'recommend' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="4"]) > div::before {{content:'compare_arrows' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="5"]) > div::before {{content:'inventory_2' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="6"]) > div::before {{content:'monitoring' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="7"]) > div::before {{content:'settings' / ''!important;}}
    [data-testid="stSidebar"] label:has(input[value="8"]) > div::before {{content:'info' / ''!important;}}
    [data-testid="stSidebar"] [data-testid="stExpander"] {{background:#142B43;border:0;margin-top:1rem;}}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{font-size:10px;letter-spacing:1.2px;color:#A1B7CD;}}
    .cc-sidebar-note {{border-top:1px solid #2A3C52;margin-top:1.5rem;padding:1.5rem .6rem;line-height:1.9;font-size:12px;color:#A3B7CA!important;}}
    .cc-sidebar-note b {{color:#E8F2FA;}}
    .cc-eyebrow {{font-size:10px;font-weight:700;color:#087F8C;letter-spacing:2px;margin-bottom:.9rem;}}
    h1 {{font-size:2.5rem!important;letter-spacing:-1.2px!important;line-height:1.15!important;}}
    h3 {{font-size:1.2rem!important;font-weight:650!important;line-height:1.4!important;}}
    [data-testid="stMetric"] {{box-shadow:0 4px 18px #10223905;border-radius:13px;padding:1.15rem;}}
    [data-testid="stMetricValue"] {{font-size:2rem!important;letter-spacing:-1px;}}
    [data-testid="stMetricValue"] > div {{white-space:normal;overflow-wrap:anywhere;}}
    [data-testid="stMetricLabel"] p {{font-size:.8rem;color:{muted};}}
    [data-testid="stVerticalBlockBorderWrapper"] > div {{border-radius:16px!important;}}
    [data-testid="stVerticalBlockBorderWrapper"] {{box-shadow:0 6px 24px #10223904;}}
    [data-testid="stForm"] {{background:{surface};border-color:{border};}}
    [data-testid="stTextInput"] input {{min-height:44px;}}
    .stButton button,.stFormSubmitButton button {{min-height:40px;font-size:.82rem!important;}}
    button[kind="primary"],button[kind="primaryFormSubmit"] {{background:#087F8C;color:#FFFFFF;border-color:#087F8C;}}
    button[kind="primary"]:hover,button[kind="primaryFormSubmit"]:hover {{background:#066A75;color:#FFFFFF;border-color:#066A75;}}
    [data-testid="stImage"] {{width:100%;}}
    [data-testid="stImage"] img {{width:100%;height:auto;aspect-ratio:4/3;object-fit:contain;border-radius:12px;background:#F5F7F9;}}
    [data-testid="stChatMessage"] {{border:1px solid {border};border-radius:16px;background:{surface};padding:1.3rem;}}
    [data-testid="stDataFrame"] {{border-radius:12px;overflow:hidden;}}
    @media(max-width:1100px) {{.block-container {{padding:2.4rem 1.5rem;}}h1 {{font-size:2.1rem!important;}}}}
    @media(max-width:640px) {{.block-container {{padding:2rem 1rem;}}h1 {{font-size:1.9rem!important;letter-spacing:-.7px!important;}}[data-testid="stMetricValue"] {{font-size:1.8rem!important;}}}}
    @media(prefers-reduced-motion:reduce) {{* {{transition:none!important;}}}}
    </style>""", unsafe_allow_html=True)


def chart(rows, x, y, title, *, kind="bar", color=None, key=None):
    if not rows:
        st.caption(f"{title}: no recorded data yet.")
        return
    template = "plotly_dark" if st.session_state.get("dark_mode") else "plotly_white"
    frame = pd.DataFrame(rows)
    if kind == "line":
        figure = px.line(frame, x=x, y=y, color=color, markers=True, title=title, template=template, color_discrete_sequence=COLORS)
    else:
        figure = px.bar(frame, x=x, y=y, color=color, title=title, template=template, color_discrete_sequence=COLORS)
    figure.update_layout(height=330, margin=dict(l=12, r=12, t=55, b=20), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(family="Inter, Segoe UI, sans-serif", size=12), title_font_size=17, showlegend=bool(color))
    if x == "date":
        # ISO day labels remain readable even when only one day is recorded.
        figure.update_xaxes(type="category", categoryorder="category ascending")
    if y in {"runs", "interactions", "count"}:
        figure.update_yaxes(rangemode="tozero", tickformat="d")
    st.plotly_chart(figure, width="stretch", key=key, config={"displayModeBar": False}, alt=title)


def overview_details(get):
    overview = get("/analytics/overview")
    recommendations = get("/analytics/recommendations")
    if overview is None or recommendations is None:
        return
    left, right = st.columns([1.25, 1])
    with left.container(border=True):
        chart(recommendations["daily_trend"], "date", "runs", "Recommendation activity", kind="line", key="overview_trend")
    with right.container(border=True):
        chart(overview["channel_activity"], "channel", "interactions", "Shopping channel activity", color="channel", key="overview_channels")
    left, right = st.columns(2)
    with left.container(border=True):
        chart(overview["popular_categories"], "category", "count", "Popular categories", key="overview_categories")
    with right.container(border=True):
        st.subheader("Popular products")
        if overview["popular_products"]:
            st.dataframe(overview["popular_products"][:5], hide_index=True, width="stretch")
        else:
            st.caption("Product popularity appears after recorded shopping activity.")
    st.subheader("Recent recommendations")
    if overview["recent_recommendations"]:
        st.dataframe(overview["recent_recommendations"], hide_index=True, width="stretch")
    else:
        st.info("Generate a recommendation to populate recent activity.")
    st.caption("All metrics are calculated from application records. Bundled shopping events and simulation activity are synthetic.")


def product_cards(products, key_prefix="catalog", scores=None):
    for offset in range(0, len(products), 3):
        columns = st.columns(3)
        for column, product in zip(columns, products[offset:offset + 3]):
            with column.container(border=True):
                render_product_photo(product)
                st.caption(f"{product['category']} · {product['brand']}")
                st.subheader(product["name"])
                st.markdown(f"**{product['currency']} {float(product['price']):,.2f}**")
                st.caption(f"Rating {product['rating']:.1f}/5 · " + (f"In stock: {product['stock_quantity']}" if product["available"] else "Out of stock"))
                st.caption(f"Product {product['id']} · Source: {product['source']}")
                if scores and product["id"] in scores:
                    item = scores[product["id"]]
                    st.caption(f"Similarity {item.get('similarity_score', 0):.3f} · Relevance {item['relevance_score']:.3f}")
                    st.write(item["explanation"])
                else:
                    with st.expander("Product details"):
                        st.write(product["description"])
                        st.write("Features: " + (", ".join(product["features"]) or "Not specified"))
                        st.json(product["attributes"])


def catalog_editor(get, mutate):
    with st.expander("Manage catalog products"):
        st.caption("Create or edit local catalog records. Edits preserve recommendation history and require index synchronization before updated vector retrieval.")
        action = st.selectbox("Catalog action", ["Create product", "Update product"], key="catalog_action")
        selected = None
        if action == "Update product":
            product_id = st.text_input("Existing product ID", key="catalog_existing_id")
            if product_id.strip():
                selected = get(f"/products/{product_id.strip()}")
            if selected is None:
                st.caption("Enter an existing product ID to load its editable fields.")
                return
        initial = selected or {"id": "", "name": "", "description": "", "brand": "", "category": "", "price": "0.00", "rating": 0.0, "stock_quantity": 0, "features": [], "attributes": {}, "image_url": None}
        suffix = initial["id"] or "new"
        with st.form(f"catalog_editor_{action}_{suffix}"):
            product_id = st.text_input("Product ID", value=initial["id"], disabled=selected is not None)
            name = st.text_input("Product name", value=initial["name"])
            description = st.text_area("Description", value=initial["description"])
            left, right = st.columns(2)
            category = left.text_input("Product category", value=initial["category"])
            brand = right.text_input("Product brand", value=initial["brand"])
            price = left.number_input("Price (INR)", min_value=0.0, value=float(initial["price"]), step=100.0)
            stock = right.number_input("Stock quantity", min_value=0, value=initial["stock_quantity"], step=1)
            rating = st.number_input("Rating", min_value=0.0, max_value=5.0, value=float(initial["rating"]), step=0.1)
            features = st.text_input("Features (comma separated)", value=", ".join(initial["features"]))
            attributes = st.text_area("Attributes (JSON object)", value=json.dumps(initial["attributes"]))
            image = st.text_input("Image URL (optional)", value=initial["image_url"] or "")
            save = st.form_submit_button("Save catalog product")
        if save:
            try:
                parsed = json.loads(attributes)
                if not isinstance(parsed, dict):
                    raise ValueError("Object required")
            except ValueError:
                st.error("Attributes must be a valid JSON object.")
                return
            payload = {"id": product_id, "name": name, "description": description, "category": category, "brand": brand,
                       "price": f"{price:.2f}", "stock_quantity": stock, "rating": rating, "features": [value.strip() for value in features.split(",") if value.strip()],
                       "attributes": parsed, "image_url": image.strip() or None}
            result = mutate(f"/products/{product_id}" if selected else "/products", payload,
                            operation="Catalog update" if selected else "Catalog create", method="PUT" if selected else "POST")
            if result is not None:
                st.success(f"Saved product {result['id']} at INR {result['price']}.")


def omnichannel_page(get, post):
    st.caption("Explore shared preferences across three synthetic shopping channels. Charts use actual application records.")
    insights, simulator = st.tabs(["Channel analytics", "Shopping simulator"])
    with insights:
        use_dates = st.checkbox("Filter analytics by UTC dates")
        left, right = st.columns(2)
        start = left.date_input("From date", key="analytics_from")
        end = right.date_input("To date", key="analytics_to")
        params = {"date_from": start.isoformat(), "date_to": end.isoformat()} if use_dates else {}
        if use_dates and start > end:
            st.error("From date must be no later than To date.")
        else:
            channels = get("/analytics/channels", **params)
            recommendations = get("/analytics/recommendations", **params)
            if channels is not None and recommendations is not None:
                columns = st.columns(3)
                for column, row in zip(columns, channels["channels"]):
                    with column.container(border=True):
                        st.subheader(CHANNEL_LABELS[row["channel"]])
                        st.metric("Interactions", row["interactions"])
                        st.caption(f"{row['active_customers']} active customers · {row['recommendation_runs']} recommendation runs")
                st.caption(f"{channels['cross_channel_customers']} customers have recorded activity across multiple channels.")
                left, right = st.columns(2)
                with left:
                    chart(channels["daily_activity"], "date", "interactions", "Channel activity over time", kind="line", color="channel", key="channel_trend")
                with right:
                    chart(recommendations["daily_trend"], "date", "runs", "Recommendation trend", kind="line", key="channel_recs")
                left, right = st.columns(2)
                with left:
                    chart(recommendations["category_distribution"], "category", "count", "Recommended categories", key="recommended_categories")
                with right:
                    chart(channels["event_mix"], "channel", "count", "Customer engagement events", color="event_type", key="event_mix")
                st.subheader("Product recommendation frequency and scores")
                if recommendations["product_performance"]:
                    st.dataframe(recommendations["product_performance"], hide_index=True, width="stretch")
                else:
                    st.info("Generate recommendations to populate product recommendation statistics.")
                st.caption(recommendations["measurement_notes"])
                st.download_button("Download channel analytics (CSV)", pd.DataFrame(channels["channels"]).to_csv(index=False), file_name="retailrag-channel-analytics.csv", mime="text/csv")
    with simulator:
        st.subheader("One customer. Three shopping touchpoints.")
        st.caption("This records synthetic events and generates one recommendation per channel. It does not place orders, charge payments, or change inventory.")
        customers, products = get("/customers", limit=100), get("/products", limit=100)
        if not customers or not products or not customers["items"] or not products["items"]:
            st.info("Load customers and products before running a simulation.")
            return
        names = {row["id"]: f"{row['name']} ({row['id']})" for row in customers["items"]}
        product_names = {row["id"]: f"{row['name']} ({row['id']})" for row in products["items"]}
        if st.button("Start a new journey"):
            st.session_state["simulation_key"] = uuid.uuid4().hex
            st.session_state.pop("simulation_result", None)
        with st.form("shopping_simulation"):
            customer_id = st.selectbox("Simulation customer", list(names), format_func=names.get)
            selected_channels = st.multiselect("Shopping touchpoints", list(CHANNEL_LABELS), default=list(CHANNEL_LABELS), format_func=CHANNEL_LABELS.get)
            events = []
            for channel in CHANNEL_LABELS:
                left, right = st.columns([2, 1])
                product_id = left.selectbox(f"{CHANNEL_LABELS[channel]} product", list(product_names), format_func=product_names.get, key=f"simulation_product_{channel}")
                event = right.selectbox(f"{CHANNEL_LABELS[channel]} activity", ["view", "wishlist", "cart", "purchase"], key=f"simulation_event_{channel}")
                if channel in selected_channels:
                    events.append({"product_id": product_id, "event_type": event, "channel": channel})
            query = st.text_input("Recommendation request (optional)", key="simulation_query")
            submitted = st.form_submit_button("Run shopping simulation")
        if submitted:
            if not events:
                st.error("Select at least one shopping touchpoint.")
            else:
                signature = json.dumps({"customer_id": customer_id, "events": events, "query": query}, sort_keys=True)
                if st.session_state.get("simulation_request_signature") != signature:
                    st.session_state["simulation_key"] = uuid.uuid4().hex
                    st.session_state["simulation_request_signature"] = signature
                key = st.session_state.setdefault("simulation_key", uuid.uuid4().hex)
                result = post("/omnichannel/simulations", {"customer_id": customer_id, "events": events, "query": query, "idempotency_key": key}, operation="Shopping simulation")
                if result is not None:
                    st.session_state["simulation_result"] = result
        result = st.session_state.get("simulation_result")
        if result:
            st.success("Journey already recorded; original result loaded." if result["replayed"] else "Synthetic shopping journey recorded across the selected channels.")
            st.caption(result["message"])
            st.dataframe(result["events"], hide_index=True, width="stretch")
            for channel, recommendation in result["recommendations"].items():
                with st.expander(f"{CHANNEL_LABELS[channel]} recommendations · #{recommendation['id']}"):
                    st.write(recommendation["message"])
                    st.dataframe([{"Product": item["product"]["name"], "Price (INR)": item["product"]["price"], "Relevance": item["relevance_score"], "Explanation": item["explanation"]} for item in recommendation["items"]], hide_index=True, width="stretch")
            with st.expander("Shared profiles and original simulation evidence"):
                st.json(result)
