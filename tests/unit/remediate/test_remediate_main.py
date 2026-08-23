import json
import logging

from typer.testing import CliRunner

from ticket_remediation.db.connection import get_connection
from ticket_remediation.db.repository import RemediationRunRepository
from ticket_remediation.remediate import __main__ as remediate_main
from ticket_remediation.remediate.pipeline import RemediateResult
from ticket_remediation.remediate.pr_sync import PrSyncResult

runner = CliRunner()


def _seed_db(monkeypatch, tmp_path):
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    return get_connection(db_path)


def _seed_db_for_run(monkeypatch, tmp_path):
    """`run` also constructs a real GitHubRestClient, which needs a non-empty token."""
    conn = _seed_db(monkeypatch, tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    return conn


class FakePipeline:
    last_init_kwargs: dict = {}
    last_run_kwargs: dict = {}
    result: RemediateResult = RemediateResult()

    def __init__(self, **kwargs):
        FakePipeline.last_init_kwargs = kwargs

    def run(self, **kwargs):
        FakePipeline.last_run_kwargs = kwargs
        return FakePipeline.result


class FakeSyncer:
    result: PrSyncResult = PrSyncResult()

    def __init__(self, github_client, runs):
        pass

    def sync(self):
        return FakeSyncer.result


def test_sync_pr_status_prints_json_summary(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakeSyncer.result = PrSyncResult(merged=["AVREM-1"], closed=["AVREM-2"], checked=2, errors=[])
    monkeypatch.setattr(remediate_main, "PrStatusSyncer", FakeSyncer)

    result = runner.invoke(remediate_main.app, ["sync-pr-status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload == {"merged": ["AVREM-1"], "closed": ["AVREM-2"], "checked": 2, "errors": []}


def test_sync_pr_status_skips_when_lock_is_held(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)

    def _raise_lock_held(path):
        raise remediate_main.LockHeldError(f"lock held: {path}")

    monkeypatch.setattr(remediate_main, "pipeline_lock", _raise_lock_held)

    result = runner.invoke(remediate_main.app, ["sync-pr-status"])

    assert result.exit_code == 0


def test_status_reports_no_runs(monkeypatch, tmp_path):
    _seed_db(monkeypatch, tmp_path)

    result = runner.invoke(remediate_main.app, ["status"])

    assert result.exit_code == 0
    assert "No remediation runs recorded." in result.output


def test_status_lists_and_filters_by_status(monkeypatch, tmp_path):
    conn = _seed_db(monkeypatch, tmp_path)
    runs = RemediationRunRepository(conn)
    runs.upsert_run(
        "AVREM-1", status="pr_open", repo_full_name="org/repo", pr_url="https://example.com/pr/1", pr_number=1
    )
    runs.upsert_run("AVREM-2", status="failed", error_message="boom", stage="llm_generate")

    result_all = runner.invoke(remediate_main.app, ["status"])
    assert result_all.exit_code == 0
    assert "AVREM-1" in result_all.output
    assert "AVREM-2" in result_all.output

    result_filtered = runner.invoke(remediate_main.app, ["status", "--status", "failed"])
    assert result_filtered.exit_code == 0
    assert "AVREM-2" in result_filtered.output
    assert "AVREM-1" not in result_filtered.output


def test_show_prints_full_detail_for_a_recorded_run(monkeypatch, tmp_path):
    conn = _seed_db(monkeypatch, tmp_path)
    runs = RemediationRunRepository(conn)
    runs.upsert_run(
        "AVREM-1", status="pr_open", repo_full_name="org/repo", pr_url="https://example.com/pr/1", pr_number=1
    )

    result = runner.invoke(remediate_main.app, ["show", "AVREM-1"])

    assert result.exit_code == 0
    assert "status: pr_open" in result.output
    assert "pr_url: https://example.com/pr/1" in result.output


def test_show_reports_a_clear_message_for_an_unknown_key(monkeypatch, tmp_path):
    _seed_db(monkeypatch, tmp_path)

    result = runner.invoke(remediate_main.app, ["show", "AVREM-999"])

    assert result.exit_code == 1
    assert "No run recorded for AVREM-999" in result.output


def test_ignore_marks_run_ignored_with_reason(monkeypatch, tmp_path):
    conn = _seed_db(monkeypatch, tmp_path)

    result = runner.invoke(remediate_main.app, ["ignore", "AVREM-1", "--reason", "known false positive"])

    assert result.exit_code == 0
    run = RemediationRunRepository(conn).get_run("AVREM-1")
    assert run["status"] == "ignored"
    assert run["error_message"] == "known false positive"


def test_run_json_flag_prints_valid_json_summary(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakePipeline.result = RemediateResult(
        opened_prs=["AVREM-1"], skipped=1, blocked=["AVREM-2"], deferred=0, failed=[], batch_error=None
    )
    monkeypatch.setattr(remediate_main, "RemediatePipeline", FakePipeline)

    result = runner.invoke(remediate_main.app, ["run", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload == {
        "opened_prs": ["AVREM-1"],
        "skipped": 1,
        "blocked": ["AVREM-2"],
        "deferred": 0,
        "failed": [],
        "batch_error": None,
    }


def test_run_json_flag_exits_nonzero_when_there_are_failures(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakePipeline.result = RemediateResult(failed=["AVREM-1"])
    monkeypatch.setattr(remediate_main, "RemediatePipeline", FakePipeline)

    result = runner.invoke(remediate_main.app, ["run", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["failed"] == ["AVREM-1"]


def test_run_ticket_flag_is_passed_through_to_the_pipeline_as_the_jql_key(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakePipeline.result = RemediateResult()
    monkeypatch.setattr(remediate_main, "RemediatePipeline", FakePipeline)

    result = runner.invoke(remediate_main.app, ["run", "--ticket", "AVREM-42"])

    assert result.exit_code == 0
    assert FakePipeline.last_run_kwargs["ticket_key"] == "AVREM-42"
    assert FakePipeline.last_run_kwargs["bypass_skip_for"] is None


def test_run_force_without_ticket_is_rejected_rather_than_silently_ignored(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakePipeline.result = RemediateResult()
    monkeypatch.setattr(remediate_main, "RemediatePipeline", FakePipeline)

    result = runner.invoke(remediate_main.app, ["run", "--force"])

    assert result.exit_code != 0
    assert "--force" in result.output
    assert "--ticket" in result.output


def test_run_force_with_ticket_bypasses_the_skip_gate_only_for_that_ticket(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakePipeline.result = RemediateResult()
    monkeypatch.setattr(remediate_main, "RemediatePipeline", FakePipeline)

    result = runner.invoke(remediate_main.app, ["run", "--ticket", "AVREM-42", "--force"])

    assert result.exit_code == 0
    assert FakePipeline.last_run_kwargs["ticket_key"] == "AVREM-42"
    assert FakePipeline.last_run_kwargs["bypass_skip_for"] == "AVREM-42"


def test_run_verbose_flag_overrides_the_configured_log_level_to_debug(monkeypatch, tmp_path):
    _seed_db_for_run(monkeypatch, tmp_path)
    FakePipeline.result = RemediateResult()
    monkeypatch.setattr(remediate_main, "RemediatePipeline", FakePipeline)
    captured = {}

    def fake_configure_logging(level, json_output):
        captured["level"] = level
        captured["json_output"] = json_output

    monkeypatch.setattr(remediate_main, "configure_logging", fake_configure_logging)

    result = runner.invoke(remediate_main.app, ["run", "--verbose"])

    assert result.exit_code == 0
    assert captured["level"] == logging.DEBUG
