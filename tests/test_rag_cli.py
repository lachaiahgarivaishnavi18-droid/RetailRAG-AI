import json

from retailrag import rag_cli
from retailrag.config import Settings


def test_rag_cli_ingest_search_examples_and_delete(seeded_engine, tmp_path, monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url=str(seeded_engine.url), rag_directory=tmp_path / "chroma")
    monkeypatch.setattr(rag_cli, "get_settings", lambda: settings)
    assert rag_cli.main(["ingest"]) == 0
    assert json.loads(capsys.readouterr().out)["products"] == 24
    assert rag_cli.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    assert rag_cli.main(["search", "--query", "wireless headphones under INR 3000"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["references"][0] == "P001"
    output = tmp_path / "examples.json"
    assert rag_cli.main(["examples", "--output", str(output)]) == 0
    capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(report["examples"]) == 4
    assert report["examples"][0]["references"][0] == "P001"
    assert report["examples"][-1]["items"] == []
    assert rag_cli.main(["delete", "--product-id", "P001"]) == 0
    assert json.loads(capsys.readouterr().out)["deleted_product_id"] == "P001"
    assert rag_cli.main(["delete", "--product-id", "MISSING"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
