import logging
import pytest

from backend.app.main import parse_log_level


def test_basic_config_handles_blank():
    level = parse_log_level("")
    assert level == logging.INFO
    logging.basicConfig(level=level)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, logging.INFO),
        ("", logging.INFO),
        (" ", logging.INFO),
        ("debug", logging.DEBUG),
        ("20", 20),
        ("INFO", logging.INFO),
        (" info ", logging.INFO),
        ("foo", logging.INFO),
    ],
)
def test_parse_log_level_various(value, expected):
    assert parse_log_level(value) == expected
