import json
from typing import Any


def utf8_json_size_bytes(payload: dict[str, Any]) -> int:
    """Return the compact JSON UTF-8 byte size of a request payload."""
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return len(payload_json.encode("utf-8"))
