from coding_agent.context import (
    FingerprintFactory,
    NoProgressDetector,
    NoProgressReason,
    NoProgressReport,
    ProgressStrategy,
)


def test_normalized_fingerprints_ignore_superficial_formatting() -> None:
    first = FingerprintFactory.tool(
        "read_file",
        {"path": "app/main.py", "line": 10},
    )
    second = FingerprintFactory.tool(
        "READ_FILE",
        {"line": 10, "path": "  APP/main.py  "},
    )

    assert first == second
    assert FingerprintFactory.command("pytest   -q") == FingerprintFactory.command(("pytest", "-q"))
    assert FingerprintFactory.result("failed", error_fingerprint="error")


def test_same_command_error_twice_requests_replanning() -> None:
    detector = NoProgressDetector(max_identical_errors=2)

    first = detector.record_command_error(
        ("pytest", "-q"),
        code="test_failed",
        message="Process 12345 returned the same assertion.",
    )
    second = detector.record_command_error(
        "pytest -q",
        code="TEST_FAILED",
        message="Process 67890 returned the same assertion.",
    )

    assert first is None
    assert second is not None
    assert second.reason is NoProgressReason.REPEATED_ERROR
    assert second.strategy is ProgressStrategy.REPLAN
    assert not second.allow_execution


def test_third_identical_action_is_blocked_before_execution() -> None:
    detector = NoProgressDetector(max_identical_actions=2)
    arguments = {"path": "app/main.py"}
    for _ in range(2):
        assert detector.before_tool("read_file", arguments) is None
        detector.record_tool("read_file", arguments)

    blocked = detector.before_tool("read_file", arguments)

    assert blocked is not None
    assert blocked.reason is NoProgressReason.REPEATED_ACTION
    assert not blocked.allow_execution
    assert len(detector.attempts) == 2


def test_alternating_a_b_a_b_cycle_is_detected() -> None:
    detector = NoProgressDetector()
    signal = None
    for name in ("read_file", "search_files", "read_file", "search_files"):
        signal = detector.record_tool(name, {"path": "app"})

    assert signal is not None
    assert signal.reason is NoProgressReason.ALTERNATING_CYCLE
    assert signal.strategy is ProgressStrategy.CHANGE_STRATEGY


def test_rereading_unchanged_file_without_evidence_is_detected() -> None:
    detector = NoProgressDetector()

    assert detector.record_file_read("app/main.py", content_digest="digest-1") is None
    signal = detector.record_file_read("app/main.py", content_digest="digest-1")

    assert signal is not None
    assert signal.reason is NoProgressReason.REPEATED_READ
    assert signal.strategy is ProgressStrategy.REQUEST_EVIDENCE_OR_PERMISSION


def test_new_evidence_resets_no_progress_counters() -> None:
    detector = NoProgressDetector(max_identical_actions=2)
    arguments = {"path": "app/main.py"}
    detector.record_tool("read_file", arguments)
    detector.record_tool("read_file", arguments)
    assert detector.before_tool("read_file", arguments) is not None

    assert detector.note_progress(evidence_ids=("repo-evidence-1",))

    assert detector.before_tool("read_file", arguments) is None
    assert detector.record_file_read("app/main.py", content_digest="digest-1") is None


def test_iteration_and_stagnant_phase_limits_choose_explicit_strategies() -> None:
    detector = NoProgressDetector(max_stagnant_phases=2)
    assert detector.record_iteration(2, maximum=3) is None
    exhausted = detector.record_iteration(3, maximum=3)
    assert exhausted is not None
    assert exhausted.strategy is ProgressStrategy.STOP

    assert detector.record_phase("exploring", evidence_ids=(), change_ids=()) is None
    assert detector.record_phase("researching", evidence_ids=(), change_ids=()) is None
    stagnant = detector.record_phase("implementing", evidence_ids=(), change_ids=())
    assert stagnant is not None
    assert stagnant.reason is NoProgressReason.STAGNANT_PHASES
    assert stagnant.strategy is ProgressStrategy.ASK_HELP


def test_final_report_explains_attempts_strategy_and_missing_information() -> None:
    detector = NoProgressDetector(max_identical_errors=1)
    signal = detector.record_command_error(
        "pytest -q",
        code="test_failed",
        message="Assertion failed",
    )
    assert signal is not None

    rendered = NoProgressReport.from_signal(signal).render()

    assert "Attempted: command-error:pytest -q" in rendered
    assert "Chosen strategy: replan" in rendered
    assert "Missing to continue:" in rendered
    assert "new diagnosis" in rendered
