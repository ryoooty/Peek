import importlib


tz_mod = importlib.import_module("app.utils.tz")
parse_tz_offset = tz_mod.parse_tz_offset


def test_parse_tz_offset_valid():
    cases = {
        "+3": 180,
        "- 3": -180,
        "-03": -180,
        "+03:00": 180,
        "4:30": 270,
        "-12:30": -750,
        "0": 0,
        "00:30": 30,
    }
    for text, expected in cases.items():
        assert parse_tz_offset(text) == expected


def test_parse_tz_offset_invalid():
    for text in [
        "",
        "abc",
        "+13",
        "2:15",
        "+12:45",
        "--3",
        "+3:5",
    ]:
        assert parse_tz_offset(text) is None

