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


def test_failure_count_increments_on_repeated_failures_and_resets_on_success(db_conn):
    runs = RemediationRunRepository(db_conn)

    runs.upsert_run("AVREM-1", status="failed", error_message="boom")
    assert runs.get_run("AVREM-1")["failure_count"] == 1

    runs.upsert_run("AVREM-1", status="failed", error_message="boom again")
    assert runs.get_run("AVREM-1")["failure_count"] == 2

    runs.upsert_run("AVREM-1", status="branch_created", repo_full_name="org/repo", branch_name="b")
    assert runs.get_run("AVREM-1")["failure_count"] == 0


def test_is_permanently_failed_at_the_threshold_boundary(db_conn):
    runs = RemediationRunRepository(db_conn)
    assert not runs.is_permanently_failed("AVREM-1", max_failures=3)

    runs.upsert_run("AVREM-1", status="failed", error_message="boom")
    runs.upsert_run("AVREM-1", status="failed", error_message="boom")
    assert not runs.is_permanently_failed("AVREM-1", max_failures=3)

    runs.upsert_run("AVREM-1", status="failed", error_message="boom")
    assert runs.is_permanently_failed("AVREM-1", max_failures=3)


def test_mark_ignored_sets_status_and_reason(db_conn):
    runs = RemediationRunRepository(db_conn)
    runs.mark_ignored("AVREM-1", reason="known false positive")

    run = runs.get_run("AVREM-1")
    assert run["status"] == "ignored"
    assert run["error_message"] == "known false positive"


def test_should_skip_covers_delivered_ignored_and_permanently_failed(db_conn):
    runs = RemediationRunRepository(db_conn)

    assert not runs.should_skip("AVREM-1", max_retries=3)

    runs.upsert_run("AVREM-1", status="pr_open", pr_url="https://example.com/pr/1", pr_number=1)
    assert runs.should_skip("AVREM-1", max_retries=3)

    runs.mark_ignored("AVREM-2")
    assert runs.should_skip("AVREM-2", max_retries=3)

    for _ in range(3):
        runs.upsert_run("AVREM-3", status="failed", error_message="boom")
    assert runs.should_skip("AVREM-3", max_retries=3)

    runs.upsert_run("AVREM-4", status="failed", error_message="boom")
    assert not runs.should_skip("AVREM-4", max_retries=3)

    runs.upsert_run("AVREM-5", status="pr_closed", repo_full_name="org/repo", pr_number=5)
    assert runs.should_skip("AVREM-5", max_retries=3)
    assert not runs.is_already_delivered("AVREM-5")  # closed-without-merge is not "delivered"
