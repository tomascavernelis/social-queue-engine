import json
from datetime import date, datetime
from pathlib import Path


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def parse_date(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def stamp(item):
    """Item -> datetime, for sorting and gap maths."""
    return datetime.fromisoformat(f"{item['date']}T{item['time']}")
