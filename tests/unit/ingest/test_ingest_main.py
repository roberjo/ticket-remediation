from typer.testing import CliRunner

from ticket_remediation.db.connection import get_connection
from ticket_remediation.db.repository import LinkRepository
from ticket_remediation.ingest import __main__ as ingest_main

runner = CliRunner()


def _seed_db(monkeypatch, tmp_path):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    return get_connection(db_path)


def test_status_reports_no_links(monkeypatch, tmp_path):
    _seed_db(monkeypatch, tmp_path)

    result = runner.invoke(ingest_main.app, ["status"])

    assert result.exit_code == 0
    assert "No ServiceNow<->Jira links recorded." in result.output


def test_status_lists_recorded_links(monkeypatch, tmp_path):
    conn = _seed_db(monkeypatch, tmp_path)
    links = LinkRepository(conn)
    links.record_link("x_avit_findings", "sys-1", "AVIT0000001", "AVREM-1")
    links.record_link("x_avit_findings", "sys-2", "AVIT0000002", "AVREM-2")

    result = runner.invoke(ingest_main.app, ["status"])

    assert result.exit_code == 0
    assert "AVIT0000001" in result.output
    assert "AVREM-1" in result.output
    assert "AVIT0000002" in result.output
    assert "AVREM-2" in result.output
