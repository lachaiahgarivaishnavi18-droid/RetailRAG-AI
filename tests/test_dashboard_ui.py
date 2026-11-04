from pathlib import Path
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest

from test_frontend import backend_mock, backend_post_mock

FRONTEND = Path(__file__).parents[1] / "src" / "retailrag" / "frontend.py"


def test_phase9_dashboard_renders_real_plotly_charts_and_dark_theme(client):
    with patch("httpx.get", side_effect=backend_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=20).run()
        assert not app.exception
        assert [metric.value for metric in app.metric] == ["24", "6", "0", "Not tracked"]
        assert any(button.label == "Compare" for button in app.button)
        app.sidebar.toggle[0].set_value(True).run()
        assert not app.exception
        assert app.session_state["dark_mode"] is True


def test_phase9_omnichannel_page_generates_and_replays_actual_journey(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=20).run()
        app.sidebar.radio[1].set_value("Omnichannel Analytics").run()
        assert not app.exception
        assert len(app.get("plotly_chart")) >= 2
        app.selectbox[0].set_value("C008")
        submit = next(button for button in app.button if button.label == "Run shopping simulation")
        submit.click().run(timeout=30)
        assert not app.exception
        assert client.get("/customers/C008/history").json()["total"] == 3
        assert client.get("/recommendations").json()["total"] == 3
        next(button for button in app.button if button.label == "Run shopping simulation").click().run(timeout=30)
        assert not app.exception
        assert client.get("/customers/C008/history").json()["total"] == 3
        assert any("already recorded" in message.value for message in app.success)


def test_phase9_catalog_editor_creates_real_product_through_api(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=20).run()
        app.sidebar.radio[1].set_value("Product Catalog").run()
        assert not app.exception
        def text(label):
            return next(widget for widget in app.text_input if widget.label == label)
        text("Product ID").set_value("UI001")
        text("Product name").set_value("UI Local Product")
        text("Product category").set_value("Home")
        text("Product brand").set_value("Local Demo")
        next(widget for widget in app.text_area if widget.label == "Description").set_value("Locally created catalog demonstration product")
        next(button for button in app.button if button.label == "Save catalog product").click().run(timeout=30)
        assert not app.exception
        assert client.get("/products/UI001").status_code == 200
        assert client.get("/products/UI001").json()["source"] == "user_catalog"


def test_phase9_each_navigation_destination_and_settings_function(client):
    with patch("httpx.get", side_effect=backend_mock(client)), patch("httpx.post", side_effect=backend_post_mock(client)):
        app = AppTest.from_file(str(FRONTEND), default_timeout=20).run()
        for page in ["Product Catalog", "Customer Context", "AI Recommendations", "RAG Search", "Agent Workflow", "Omnichannel Analytics", "Tool Explorer", "Recommendation History", "Settings", "Overview"]:
            app.sidebar.radio[0 if page in {"Settings", "AI Recommendations", "Overview"} else 1].set_value(page).run(timeout=25)
            assert not app.exception, page
            assert app.title[0].value == {"Overview": "Discover Products Smarter with AI", "AI Recommendations": "Recommendations"}.get(page, page)
