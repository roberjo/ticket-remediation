import json
import logging
import sys

from ticket_remediation.logging_config import JsonFormatter, configure_logging


def _make_record(exc_info: bool = False) -> logging.LogRecord:
    if exc_info:
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord(
                name="test.logger",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="something failed",
                args=(),
                exc_info=sys.exc_info(),
            )
    else:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
    return record


def test_json_formatter_produces_valid_json_with_expected_keys():
    formatter = JsonFormatter()
    record = _make_record()

    output = formatter.format(record)
    payload = json.loads(output)

    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert "timestamp" in payload
    assert "exc_info" not in payload


def test_json_formatter_includes_traceback_for_exceptions():
    formatter = JsonFormatter()
    record = _make_record(exc_info=True)

    output = formatter.format(record)
    payload = json.loads(output)

    assert payload["message"] == "something failed"
    assert "ValueError: boom" in payload["exc_info"]
    assert "Traceback" in payload["exc_info"]


def test_configure_logging_plain_text_still_works(capsys):
    configure_logging(level=logging.INFO, json_output=False)
    logging.getLogger("plain.logger").info("plain message")

    captured = capsys.readouterr()
    assert "plain message" in captured.err
    try:
        json.loads(captured.err.strip())
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("plain-text log output should not parse as JSON")


def test_configure_logging_json_output(capsys):
    configure_logging(level=logging.INFO, json_output=True)
    logging.getLogger("json.logger").info("json message")

    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["message"] == "json message"
    assert payload["logger"] == "json.logger"
