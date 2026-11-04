from pathlib import Path
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest


FRONTEND = Path(__file__).parents[1] / "src" / "retailrag" / "frontend.py"


def backend_mock(client):
    def request(url, params=None, timeout=None):
        response = client.get(httpx.URL(url).raw_path.decode(), params=params)
        # Starlette may use HTTPX2 internally; the frontend's real transport is HTTPX.
        return httpx.Response(response.status_code, content=response.content, headers=dict(response.headers), request=httpx.Request("GET", url))
    return request


def backend_post_mock(client):
    def request(url, json=None, timeout=None):
        response = client.post(httpx.URL(url).raw_path.decode(), json=json)
        return httpx.Response(response.status_code, content=response.content, headers=dict(response.headers), request=httpx.Request("POST", url))
    return request


def test_overview_reports_backend_health(client):
    with patch("httpx.get", side_effect=backend_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
    assert not app.exception
    assert app.title[0].value == "Discover Products Smarter with AI"
    assert [metric.value for metric in app.metric] == ["24", "6", "0", "Not tracked"]


def test_backend_failure_and_settings_navigation():
    with patch("httpx.get", side_effect=httpx.ConnectError("offline")):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
    assert not app.exception
    assert "unavailable" in app.error[0].value
    app.sidebar.radio[0].set_value("Settings").run()
    assert not app.exception
    assert app.title[0].value == "Settings"


def test_catalog_search_budget_and_stock_filters(client):
    with patch("httpx.get", side_effect=backend_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Product Catalog").run()
        assert not app.exception
        assert len(app.dataframe[0].value) == 20
        app.text_input[0].set_value("headphones")
        app.checkbox[0].set_value(True)
        app.number_input[0].set_value(3000.0)
        app.checkbox[1].set_value(True)
        app.button[0].click().run()
        assert not app.exception
        assert list(app.dataframe[0].value["id"]) == ["P001"]


def test_customer_context_and_channel_navigation(client):
    with patch("httpx.get", side_effect=backend_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Customer Context").run()
        assert not app.exception
        assert len(app.dataframe[0].value) == 8
        app.selectbox[1].set_value("mobile").run()
        assert not app.exception
        assert set(app.dataframe[0].value["channel"]) == {"mobile"}
        app.selectbox[0].set_value("C008").run()
        assert not app.exception
        assert "No interaction history" in app.info[0].value


def test_recommendation_generation_and_history_navigation(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[0].set_value("AI Recommendations").run()
        assert not app.exception
        app.text_area[0].set_value("wireless headphones under INR 3000")
        app.button[0].click().run(timeout=15)
        assert not app.exception
        assert app.dataframe[0].value.iloc[0]["Product ID"] == "P001"
        assert "no LLM" in app.info[0].value
        assert client.get("/recommendations").json()["total"] == 1
        app.sidebar.radio[1].set_value("Recommendation History").run()
        assert not app.exception
        assert len(app.dataframe[0].value) == 1
        assert app.dataframe[1].value.iloc[0]["Product ID"] == "P001"
        # Opening saved history must not generate another recommendation.
        assert client.get("/recommendations").json()["total"] == 1


def test_recommendation_validation_and_empty_state(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[0].set_value("AI Recommendations").run()
        app.button[0].click().run()
        assert not app.exception
        assert "failed" in app.error[0].value
        assert client.get("/recommendations").json()["total"] == 0
        app.text_area[0].set_value("qzxwunmatched")
        app.button[0].click().run(timeout=15)
        assert not app.exception
        assert "No products match" in app.info[0].value
        assert not app.dataframe


def test_rag_ingestion_search_filters_and_empty_state(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("RAG Search").run()
        assert not app.exception
        app.button[0].click().run(timeout=30)
        assert not app.exception
        assert "24 products" in app.success[0].value
        app.text_area[0].set_value("wireless headphones under INR 3000")
        app.text_input[1].set_value("SoundNest")
        app.button[1].click().run(timeout=30)
        assert not app.exception
        assert list(app.dataframe[0].value["Product ID"]) == ["P001"]
        assert "2499.00" in app.text[0].value
        assert "Deterministic" in app.text[0].value
        app.text_area[0].set_value("qzxwunmatched")
        app.button[1].click().run(timeout=30)
        assert not app.exception
        assert "No grounded" in app.info[0].value
        assert not app.dataframe
        assert client.get("/recommendations").json()["total"] == 0


def test_agent_workflow_page_runs_graph_and_displays_only_actual_trace(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Agent Workflow").run()
        assert not app.exception
        assert "No agent workflows" in app.info[0].value
        app.text_area[0].set_value("wireless headphones under INR 3000")
        app.text_input[0].set_value("C001")
        app.selectbox[1].set_value("content")
        app.selectbox[2].set_value("mobile")
        app.button[0].click().run(timeout=30)
        assert not app.exception
        trace = next(frame.value for frame in app.dataframe if "Agent" in frame.value.columns)
        assert len(trace) == 10 and set(trace["Status"]) == {"completed"}
        products = next(frame.value for frame in app.dataframe if "Product ID" in frame.value.columns)
        assert products.iloc[0]["Product ID"] == "P001"
        assert client.get("/agents/status").json()["total"] == 1
        app.button[1].click().run()
        assert not app.exception
        assert client.get("/agents/status").json()["total"] == 1
        app.sidebar.radio[1].set_value("Recommendation History").run()
        assert not app.exception
        assert "no LLM" in app.info[0].value


def test_agent_failure_page_does_not_claim_a_saved_recommendation(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Agent Workflow").run()
        app.text_area[0].set_value("headphones")
        app.selectbox[1].set_value("rag")
        app.button[0].click().run(timeout=30)
        assert not app.exception
        trace = next(frame.value for frame in app.dataframe if "Agent" in frame.value.columns)
        assert list(trace["Agent"]) == ["supervisor", "response"]
        assert app.error
        assert not any("Saved recommendation" in caption.value for caption in app.caption)
        assert client.get("/recommendations").json()["total"] == 0


def test_agent_transport_failure_directs_user_to_actual_run_status(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=httpx.ReadTimeout("injected timeout")):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Agent Workflow").run()
        app.text_area[0].set_value("headphones")
        app.button[0].click().run()
        assert not app.exception
        assert "Check Agent Workflow status before retrying" in app.error[0].value


def test_tool_explorer_executes_real_read_tool_and_inspects_persisted_result(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Tool Explorer").run()
        assert not app.exception
        assert "No public tools" in app.info[0].value
        app.selectbox[0].set_value("get_product_details").run()
        app.button[0].click().run()
        assert not app.exception
        calls = client.get("/tools/invocations").json()
        assert calls["total"] == 1 and calls["items"][0]["tool"] == "get_product_details"
        result = client.get(f"/tools/invocations/{calls['items'][0]['call_id']}").json()
        assert result["result"]["product"]["price"] == "2499.00"
        app.button[1].click().run()
        assert client.get("/tools/invocations").json()["total"] == 1


def test_tool_explorer_save_retry_is_idempotent_and_bad_json_is_not_executed(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=15).run()
        app.sidebar.radio[1].set_value("Tool Explorer").run()
        app.text_area[0].set_value("not-json")
        app.button[0].click().run()
        assert not app.exception and "valid JSON object" in app.error[0].value
        assert client.get("/tools/invocations").json()["total"] == 0
        app.selectbox[0].set_value("save_recommendation").run()
        app.button[0].click().run(timeout=30)
        assert not app.exception
        assert client.get("/recommendations").json()["total"] == 1
        app.button[0].click().run(timeout=30)
        assert not app.exception
        assert client.get("/recommendations").json()["total"] == 1
        assert client.get("/tools/invocations").json()["total"] == 1
