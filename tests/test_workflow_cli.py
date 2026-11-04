import json

from retailrag import workflow_cli
from retailrag.config import Settings


def test_workflow_cli_definition_examples_and_inspection(client, tmp_path, monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url=str(client.app.state.engine.url), rag_directory=tmp_path / "chroma")
    monkeypatch.setattr(workflow_cli, "get_settings", lambda: settings)
    assert workflow_cli.main(["definition"]) == 0
    assert len(json.loads(capsys.readouterr().out)["nodes"]) == 10
    output = tmp_path / "phase5.json"
    assert workflow_cli.main(["examples", "--output", str(output)]) == 0
    capsys.readouterr()
    examples = json.loads(output.read_text(encoding="utf-8"))["examples"]
    assert len(examples) == 3 and all(run["status"] == "completed" for run in examples)
    assert len(examples[0]["steps"]) == 10 and len(examples[-1]["steps"]) == 6
    assert examples[-1]["output"]["items"] == []
    assert workflow_cli.main(["inspect", "--run-id", examples[0]["run_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["output"] == examples[0]["output"]
    assert workflow_cli.main(["run", "--query", "headphones", "--customer-id", "MISSING", "--strategy", "content"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
