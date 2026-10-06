"""Condition evaluation against the fact store."""

import re

MISSING = object()  # sentinel for absent facts


def _compare(op, actual, expected):
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    try:
        if op == "gt":
            return actual > expected
        if op == "ge":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "le":
            return actual <= expected
    except TypeError:
        return False
    if op == "contains":
        try:
            return expected in actual
        except TypeError:
            return False
    if op == "not_contains":
        try:
            return expected not in actual
        except TypeError:
            return False
    if op == "in":
        return actual in expected
    if op == "not_in":
        return actual not in expected
    if op == "starts_with":
        return isinstance(actual, str) and actual.startswith(expected)
    if op == "ends_with":
        return isinstance(actual, str) and actual.endswith(expected)
    if op == "matches":
        return isinstance(actual, str) and re.search(expected, actual) is not None
    raise ValueError(f"unknown operator: {op!r}")


def evaluate(node, facts, notes=None):
    """Evaluate a condition tree against facts.

    Returns True/False. Missing facts and type mismatches evaluate to
    False; a human-readable note is appended to ``notes`` when provided.
    """
    if "all" in node:
        return all(evaluate(c, facts, notes) for c in node["all"])
    if "any" in node:
        return any(evaluate(c, facts, notes) for c in node["any"])
    if "not" in node:
        return not evaluate(node["not"], facts, notes)

    field = node["field"]
    actual = facts.get(field, MISSING)
    if actual is MISSING:
        if notes is not None:
            notes.append(f"missing fact {field!r}")
        return False
    result = _compare(node["op"], actual, node["value"])
    if notes is not None and not result:
        notes.append(
            f"{field}={actual!r} does not satisfy "
            f"{node['op']} {node['value']!r}"
        )
    return result
