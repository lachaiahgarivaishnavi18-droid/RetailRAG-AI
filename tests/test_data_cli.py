import json

from retailrag import data_cli
from retailrag.config import Settings


def test_cli_init_demo_status_and_repeat(tmp_path, monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'nested' / 'cli.db').as_posix()}")
    monkeypatch.setattr(data_cli, "get_settings", lambda: settings)
    assert data_cli.main(["init"]) == 0
    capsys.readouterr()
    assert data_cli.main(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["tables"]["products"]["inserted"] == 24
    assert data_cli.main(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["tables"]["products"]["skipped_existing"] == 24
    assert data_cli.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["customer_interactions"] == 56


def test_cli_missing_files_is_nonzero(tmp_path, monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url="sqlite:///:memory:")
    monkeypatch.setattr(data_cli, "get_settings", lambda: settings)
    assert data_cli.main(["import", "--directory", str(tmp_path / "absent")]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "error"
