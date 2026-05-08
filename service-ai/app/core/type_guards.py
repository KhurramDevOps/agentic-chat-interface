"""
app/core/type_guards.py  (T010)
───────────────────────────────
Runtime type-guard utilities for agent payload validation.

Constitution mandate (Section V):
  "Recursive agentic logic in Python MUST enforce strict runtime type
   validation. Dictionary key access SHALL occur only after explicit
   dictionary type checks to prevent AttributeError crashes."

All functions in this module raise TypeError with a descriptive message
rather than letting Python raise an opaque AttributeError or KeyError
deep inside an agent loop.

Usage pattern:
    payload = get_llm_response()
    ensure_dict(payload, "LLM response root")
    content = require_key(payload, "choices", "LLM response root")
    ensure_list(content, "choices")
    first = content[0]
    ensure_dict(first, "choices[0]")
    message = require_key(first, "message", "choices[0]")
    ...
"""

from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


# ── Primitive type guards ─────────────────────────────────────────────────────

def ensure_dict(value: Any, label: str = "value") -> dict:
    """
    Assert that *value* is a dict.

    Args:
        value: The object to check.
        label: Human-readable name used in the error message.

    Returns:
        The same value, typed as dict.

    Raises:
        TypeError: If value is not a dict.
    """
    if not isinstance(value, dict):
        raise TypeError(
            f"Expected '{label}' to be a dict, got {type(value).__name__!r}. "
            "Check the upstream payload shape."
        )
    return value


def ensure_list(value: Any, label: str = "value") -> list:
    """Assert that *value* is a list."""
    if not isinstance(value, list):
        raise TypeError(
            f"Expected '{label}' to be a list, got {type(value).__name__!r}."
        )
    return value


def ensure_str(value: Any, label: str = "value") -> str:
    """Assert that *value* is a str."""
    if not isinstance(value, str):
        raise TypeError(
            f"Expected '{label}' to be a str, got {type(value).__name__!r}."
        )
    return value


def ensure_int(value: Any, label: str = "value") -> int:
    """Assert that *value* is an int (bool excluded)."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(
            f"Expected '{label}' to be an int, got {type(value).__name__!r}."
        )
    return value


def ensure_type(value: Any, expected: type[T], label: str = "value") -> T:
    """
    Generic type guard for any type.

    Example:
        ensure_type(obj, MyModel, "agent response")
    """
    if not isinstance(value, expected):
        raise TypeError(
            f"Expected '{label}' to be {expected.__name__!r}, "
            f"got {type(value).__name__!r}."
        )
    return value  # type: ignore[return-value]


# ── Dict key helpers ──────────────────────────────────────────────────────────

def require_key(d: dict, key: str, label: str = "dict") -> Any:
    """
    Retrieve *key* from *d*, raising KeyError with context if absent.

    Always call ensure_dict() before this function.

    Args:
        d:     A dict (already validated).
        key:   The key to retrieve.
        label: Human-readable name of the dict for error messages.

    Returns:
        The value at d[key].

    Raises:
        KeyError: If key is not present.
    """
    if key not in d:
        available = list(d.keys())
        raise KeyError(
            f"Required key '{key}' not found in '{label}'. "
            f"Available keys: {available}"
        )
    return d[key]


def safe_get(d: dict, key: str, default: Any = None) -> Any:
    """
    Safe dict access that first validates *d* is a dict.

    Returns *default* if key is absent. Never raises on missing key.

    Raises:
        TypeError: If *d* is not a dict.
    """
    ensure_dict(d, label=f"safe_get target (key='{key}')")
    return d.get(key, default)


# ── Agent payload helpers ─────────────────────────────────────────────────────

def extract_text_delta(chunk: Any, label: str = "stream chunk") -> str | None:
    """
    Safely extract the text delta from an OpenAI-style streaming chunk dict.

    Expected shape:
        {"choices": [{"delta": {"content": "..."}}]}

    Returns None if the delta is empty or the path doesn't exist,
    rather than raising — callers should treat None as "no token yet".

    Raises:
        TypeError / KeyError: Only on structurally invalid payloads.
    """
    ensure_dict(chunk, label)
    choices = safe_get(chunk, "choices", default=[])
    ensure_list(choices, f"{label}.choices")
    if not choices:
        return None
    first = choices[0]
    ensure_dict(first, f"{label}.choices[0]")
    delta = safe_get(first, "delta", default={})
    if not isinstance(delta, dict):
        return None
    return delta.get("content")  # None if key absent


def validate_agent_handoff(payload: Any, label: str = "handoff payload") -> dict:
    """
    Validate that an agent handoff payload is a non-empty dict
    with at least an 'agent' key identifying the target agent.

    Raises:
        TypeError: If payload is not a dict.
        KeyError:  If 'agent' key is missing.
    """
    ensure_dict(payload, label)
    require_key(payload, "agent", label)
    return payload  # type: ignore[return-value]


def validate_memory_record(record: Any, label: str = "memory record") -> dict:
    """
    Validate a mem0 memory record has the required fields.

    Required: memory_id, context_id, content.

    Raises:
        TypeError / KeyError on invalid structure.
    """
    ensure_dict(record, label)
    for field in ("memory_id", "context_id", "content"):
        require_key(record, field, label)
    content = record["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError(
            f"'{label}.content' must be a non-empty string, got: {content!r}"
        )
    return record  # type: ignore[return-value]
