import json

from retailrag import examples
from retailrag.config import Settings


def test_examples_generate_seven_actual_persisted_recommendations(client, tmp_path, monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url=str(client.app.state.engine.url))
    monkeypatch.setattr(examples, "get_settings", lambda: settings)
    output = tmp_path / "examples.json"
    assert examples.main(["--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["saved_recommendation_ids"]) == 7
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["catalog_size"] == 24
    assert {row["request"]["mode"] for row in result["examples"]} == {"personalized", "similar", "budget", "category", "brand", "new_customer", "context_aware"}
    for row in result["examples"]:
        saved = client.get(f"/recommendations/{row['recommendation_id']}").json()
        assert row["llm_used"] is False
        assert row["items"]
        assert [item["product_id"] for item in row["items"]] == [item["product"]["id"] for item in saved["items"]]
    assert client.get("/recommendations").json()["total"] == 7
