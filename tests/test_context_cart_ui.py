from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_frontend import backend_mock, backend_post_mock

FRONTEND = Path(__file__).parents[1] / "src/retailrag/frontend.py"


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_new_pages_and_honest_evaluation_without_benchmarks(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        for page in ["Product Discovery", "AI Shopping Assistant", "Product Comparison", "Inventory & Store Availability", "Evaluation Dashboard", "About", "Settings"]:
            app.sidebar.radio[0].set_value(page).run(timeout=25)
            assert not app.exception, page
            assert app.title[0].value == page
        app.sidebar.radio[0].set_value("Evaluation Dashboard").run()
        assert [m.value for m in app.metric[:4]] == ["Unavailable"] * 4
        assert any("labeled relevance" in item.value for item in app.info)
        assert client.get("/recommendations").json()["total"] == 0


def test_discovery_filters_and_comparison_use_real_catalog(client):
    with patch("httpx.get", side_effect=backend_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        app.sidebar.radio[0].set_value("Product Discovery").run()
        app.text_input[0].set_value("headphones")
        next(w for w in app.number_input if w.label == "Maximum price (INR)").set_value(3000)
        next(w for w in app.selectbox if w.label == "Availability").set_value("In stock")
        button(app, "Discover products").click().run()
        assert not app.exception
        assert any("1 products" in h.value for h in app.subheader)
        button(app, "Compare").click().run()
        assert app.session_state["cc_compare"] == ["P001"]
        button(app, "Details").click().run()
        assert any("Specifications & provenance" == e.label for e in app.expander)
        app.sidebar.radio[0].set_value("Product Comparison").run()
        app.multiselect[0].set_value(["P001", "P003"]).run()
        assert not app.exception
        frame = app.dataframe[0].value
        assert frame.loc["Price (INR)", "Wireless Everyday Headphones"] == "2,499.00"
        assert frame.loc["Recommendation score", "Wireless Everyday Headphones"] == "Not generated in this session"


def test_assistant_real_retrieval_citations_history_and_latency(client):
    client.post("/rag/ingest", json={}).raise_for_status()
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)) as post:
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        app.sidebar.radio[0].set_value("AI Shopping Assistant").run()
        app.text_input[0].set_value("wireless headphones under INR 3000")
        button(app, "Send message").click().run(timeout=30)
        assert not app.exception
        assert len(app.get("chat_message")) == 2
        assert any("P001" in m.value for m in app.markdown)
        assert app.session_state["cc_messages"][0]["result"]["llm_used"] is False
        calls = post.call_count
        button(app, "Compare").click().run()
        assert post.call_count == calls  # card actions never repeat retrieval
        app.sidebar.radio[0].set_value("Evaluation Dashboard").run()
        assert any(m.label == "Mean client round trip" for m in app.metric)
        assert client.get("/recommendations").json()["total"] == 0


def test_dashboard_query_routes_to_discovery_without_writes(client):
    with patch("httpx.get", side_effect=backend_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        app.text_input[0].set_value("headphones")
        button(app, "Explore products").click().run()
        assert not app.exception
        assert app.title[0].value == "Product Discovery"
        assert app.text_input[0].value == "headphones"
        assert client.get("/recommendations").json()["total"] == 0


def test_discovery_natural_query_uses_existing_rag_contract_and_rating_filter(client):
    client.post("/rag/ingest", json={}).raise_for_status()
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        app.sidebar.radio[0].set_value("Product Discovery").run()
        app.text_input[0].set_value("wireless headphones under INR 3000")
        next(w for w in app.toggle if w.label == "Use natural language discovery").set_value(True)
        next(w for w in app.selectbox if w.label == "Availability").set_value("In stock")
        button(app, "Discover products").click().run(timeout=30)
        assert not app.exception
        assert any("2 products" in s.value for s in app.subheader), ([s.value for s in app.subheader], [e.value for e in app.error], [i.value for i in app.info])
        next(w for w in app.selectbox if w.label == "Minimum rating").set_value(4.5)
        button(app, "Discover products").click().run(timeout=30)
        assert any("0 products" in s.value for s in app.subheader)
        assert client.get("/recommendations").json()["total"] == 0


def test_suggested_dashboard_query_runs_grounded_discovery_and_preserves_query_budget(client):
    client.post("/rag/ingest", json={}).raise_for_status()
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=25).run()
        button(app, "Wireless headphones under INR 3000").click().run(timeout=30)
        assert not app.exception
        assert app.title[0].value == "Product Discovery"
        result = app.session_state["cc_discovery_result"]["result"]
        assert result["items"]
        assert all(float(item["product"]["price"]) < 3000 for item in result["items"])
