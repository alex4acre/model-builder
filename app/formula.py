# SPDX-License-Identifier: MIT

"""ExpressionScript formulas of axis bindings: the safe linear parser (never evaluates anything) and the light validation
of a formula text."""

import math
import re

MAX_FORMULA = 200

_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
_FORMS = [
    (re.compile(r"value"), lambda: (1.0, 0.0)),
    (re.compile(r"-\s*value"), lambda: (-1.0, 0.0)),
    (re.compile(rf"({_NUM})\s*-\s*value"), lambda k: (-1.0, k)),
    (re.compile(rf"({_NUM})\s*\+\s*value"), lambda k: (1.0, k)),
    (re.compile(rf"value\s*\+\s*({_NUM})"), lambda k: (1.0, k)),
    (re.compile(rf"value\s*-\s*({_NUM})"), lambda k: (1.0, -k)),
    (re.compile(rf"({_NUM})\s*\*\s*value"), lambda k: (k, 0.0)),
    (re.compile(rf"value\s*\*\s*({_NUM})"), lambda k: (k, 0.0)),
    (re.compile(rf"value\s*/\s*({_NUM})"), lambda k: (1.0 / k, 0.0) if k else None),
]


def parse_formula(script):
    """(a, b) with model value = a * value + b for the simple linear forms the viewer's ExpressionScripts use in practice
    (value, -value, k - value, value + k, value - k, k * value, value * k, value / k, k + value), else None ("not
    understood"). Never evaluates anything: only these patterns, with numeric k, are accepted."""
    if script is None:
        return (1.0, 0.0)
    text = str(script).strip()
    if text == "":
        return (1.0, 0.0)
    for pattern, make in _FORMS:
        m = pattern.fullmatch(text)
        if m:
            try:
                r = make(*[float(g) for g in m.groups()])
            except (ValueError, OverflowError):
                return None
            if r is None or not all(math.isfinite(c) for c in r):
                return None
            return r
    return None


def check_formula(text) -> str:
    """The formula text as it is (written unchanged into the ExpressionScript); ValueError if it is empty, has a line
    break or is longer than MAX_FORMULA characters."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("A formula must not be empty (use: value)")
    if "\n" in text or "\r" in text:
        raise ValueError("A formula is one line")
    if len(text) > MAX_FORMULA:
        raise ValueError(f"A formula has at most {MAX_FORMULA} characters")
    return text
