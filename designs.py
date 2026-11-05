"""Shared invitation design registry."""
import json
from pathlib import Path

DESIGNS = {item['id']: item for item in json.loads(
    (Path(__file__).resolve().parent / 'react_src' / 'designs.json').read_text(encoding='utf-8')
)}


def valid_design(design, invite_type):
    entry = DESIGNS.get(design)
    return bool(entry and entry['type'] == invite_type)
