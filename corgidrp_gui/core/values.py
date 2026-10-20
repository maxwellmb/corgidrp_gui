"""Turn text typed into the Builder into recipe JSON values, and back."""
from __future__ import annotations

import ast
import json
import re
from typing import Any

_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*([eE][+-]?\d+)?|\.\d+([eE][+-]?\d+)?)$")


def parse_value(text: str, hint: str = "") -> Any:
    """Parse ``text`` as JSON, then as a Python literal, else keep it as a string.

    ``hint`` is the documented type (``"float"``, ``"bool"`` ...) and only breaks
    ties: with hint ``str`` a bare number stays a string.
    """
    t = text.strip()
    if t == "":
        return ""
    low = t.lower()
    if low in ("none", "null"):
        return None
    if low in ("true", "false") and "str" not in hint:
        return low == "true"
    if "str" in hint and not (t.startswith(("[", "{", "(", '"', "'"))):
        return t
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        pass
    try:
        return ast.literal_eval(t)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        pass
    if _NUMBER.match(t):
        return float(t)
    return t


def format_value(v: Any) -> str:
    """Compact, Python-flavoured display (``True``, ``None``, ``'image'``, ``[1, 2]``)."""
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, float):
        s = repr(v)
        return s
    try:
        return json.dumps(v)
    except (TypeError, ValueError):
        return repr(v)


def values_equal(a: Any, b: Any) -> bool:
    """Equality that treats 1 == 1.0 and lists == tuples, as recipe JSON would."""
    if isinstance(a, tuple):
        a = list(a)
    if isinstance(b, tuple):
        b = list(b)
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    return a == b
