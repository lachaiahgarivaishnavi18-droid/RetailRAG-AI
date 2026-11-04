import json

from retailrag import tool_cli
from retailrag.config import Settings


def test_tool_cli_lists_executes_inspects_and_exports_actual_examples(client, tmp_path, monkeypatch, capsys):
    client.post("/rag/ingest", json={})
    settings = Settings(_env_file=None, database_url=str(client.app.state.engine.url), rag_directory=client.app.state.rag_store.directory)
    monkeypatch.setattr(tool_cli, "get_settings", lambda: settings)
    assert tool_cli.main(["list"]) == 0
    assert json.loads(capsys.readouterr().out)["total"] == 11
    assert tool_cli.main(["describe", "--name", "get_product_details"]) == 0
    assert json.loads(capsys.readouterr().out)["effect"] == "read"
    arguments = tmp_path / "arguments.json"
    arguments.write_text(json.dumps({"product_id": "P001"}), encoding="utf-8")
    assert tool_cli.main(["execute", "--name", "get_product_details", "--arguments-file", str(arguments)]) == 0
    invocation = json.loads(capsys.readouterr().out)
    assert invocation["result"]["product"]["price"] == "2499.00"
    assert tool_cli.main(["inspect", "--call-id", invocation["call_id"]]) == 0
    assert json.loads(capsys.readouterr().out) == invocation
    output = tmp_path / "examples.json"
    assert tool_cli.main(["examples", "--output", str(output)]) == 0
    capsys.readouterr()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["tool_count"] == 11 and len(report["examples"]) == 12
    assert all(example["execution"]["status"] == "completed" for example in report["examples"])
    assert report["examples"][-1]["execution"]["replayed"] is True
    assert report["examples"][-1]["execution"]["call_id"] == report["examples"][-3]["execution"]["call_id"]
    assert client.get("/recommendations").json()["total"] == 1


def test_tool_cli_invalid_arguments_and_unknown_names_return_nonzero(client, tmp_path, monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url=str(client.app.state.engine.url), rag_directory=tmp_path / "chroma")
    monkeypatch.setattr(tool_cli, "get_settings", lambda: settings)
    assert tool_cli.main(["execute", "--name", "not_registered"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "unknown_tool"
    assert tool_cli.main(["execute", "--name", "get_product_details", "--arguments", "not-json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
