from ticket_remediation.db.repository import LinkRepository, RemediationRunRepository


def test_link_repository_dedup_is_a_lookup_not_a_second_insert(db_conn):
    links = LinkRepository(db_conn)
    assert links.get_jira_key("x_avit_findings", "sys-1") is None

    links.record_link("x_avit_findings", "sys-1", "AVIT0000001", "AVREM-1")
    assert links.get_jira_key("x_avit_findings", "sys-1") == "AVREM-1"

    # Recording the same (table, sys_id) again must not raise or change the link.
    links.record_link("x_avit_findings", "sys-1", "AVIT0000001", "AVREM-999")
    assert links.get_jira_key("x_avit_findings", "sys-1") == "AVREM-1"


def test_remediation_run_repository_tracks_status_progression(db_conn):
    runs = RemediationRunRepository(db_conn)
    assert runs.get_run("AVREM-1") is None
    assert not runs.is_already_delivered("AVREM-1")

    runs.upsert_run(
        "AVREM-1", status="branch_created", repo_full_name="org/repo", branch_name="remediate/AVREM-1-fix"
    )
    assert not runs.is_already_delivered("AVREM-1")

    runs.upsert_run("AVREM-1", status="pr_open", pr_url="https://example.com/pr/1", pr_number=1)
    run = runs.get_run("AVREM-1")
    assert run["status"] == "pr_open"
    assert run["repo_full_name"] == "org/repo"  # preserved via COALESCE, not overwritten with NULL
    assert run["pr_url"] == "https://example.com/pr/1"
    assert runs.is_already_delivered("AVREM-1")
