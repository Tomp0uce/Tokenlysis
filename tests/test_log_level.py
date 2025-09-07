from backend.app.main import parse_log_level
import logging


def test_parse_log_level_values():
    assert parse_log_level(None) == logging.INFO
    assert parse_log_level("") == logging.INFO
    assert parse_log_level(" ") == logging.INFO
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level(" INFO ") == logging.INFO
    assert parse_log_level("15") == 15
    assert parse_log_level("foo") == logging.INFO
