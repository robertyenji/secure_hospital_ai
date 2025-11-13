# mcp_server/utils.py
"""
Utility helpers for consistent LLM-facing responses and JSON-safety.
"""

from typing import Any, Dict
from datetime import datetime, date
from collections.abc import Mapping, Sequence


def shape_llm(data: Any, *, model: str, role: str, redacted: bool) -> Dict[str, Any]:
    """
    Standard envelope for LLMs — predictable fields and a meta block.
    """
    return {
        "jsonrpc": "2.0",
        "result": {
            "data": data,
            "meta": {
                "model": model,
                "role": role,
                "redacted": redacted,
                "provenance": "mcp-fastapi",
            },
        },
    }


def to_jsonable(obj: Any) -> Any:
    """
    Recursively convert datetimes/dates and other non-JSON types into JSON-safe types.
    """
    # datetime/date
    if isinstance(obj, datetime):
        return obj.isoformat().replace("+00:00", "Z")
    if isinstance(obj, date):
        return obj.isoformat()

    # mappings/lists
    if isinstance(obj, Mapping):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        return [to_jsonable(v) for v in obj]

    # leave primitives as-is
    return obj
