import re

from ranchhand.handler import new_ulid

ULID_RE = re.compile(r"[0-7][0-9A-HJKMNP-TV-Z]{25}")


def test_format():
    assert ULID_RE.fullmatch(new_ulid())

def test_timestamp_prefix_is_deterministic():
    a, b = new_ulid(1_700_000_000_000), new_ulid(1_700_000_000_000)
    assert a[:10] == b[:10]
    assert a != b
