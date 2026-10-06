"""条件求值：数值/字符串比较、集合包含与布尔组合。"""

import re

COMPARISON_OPS = {"eq", "ne", "gt", "ge", "lt", "le"}
STRING_OPS = {"starts_with", "ends_with", "matches"}
COLLECTION_OPS = {"contains", "not_contains", "in", "not_in"}
ALL_OPS = COMPARISON_OPS | STRING_OPS | COLLECTION_OPS

NUMERIC_OPS = {"gt", "ge", "lt", "le"}

_MISSING = object()


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate_leaf(node, facts):
    """求值叶子条件 {field, op, value}。

    返回 (matched, detail)。fact 缺失或类型不匹配时按不匹配处理，
    detail 说明原因，供 execution trace 使用。
    """
    field = node["field"]
    op = node["op"]
    expected = node.get("value")
    actual = facts.get(field, _MISSING)

    if actual is _MISSING:
        return False, f"fact '{field}' 缺失"

    if op == "eq":
        return actual == expected, f"{field}({actual!r}) == {expected!r}"
    if op == "ne":
        return actual != expected, f"{field}({actual!r}) != {expected!r}"

    if op in NUMERIC_OPS:
        if not (_is_number(actual) and _is_number(expected)):
            return False, f"{field}({actual!r}) 与 {expected!r} 不是可比较的数值"
        result = {
            "gt": actual > expected,
            "ge": actual >= expected,
            "lt": actual < expected,
            "le": actual <= expected,
        }[op]
        return result, f"{field}({actual!r}) {op} {expected!r}"

    if op in STRING_OPS:
        if not isinstance(actual, str) or not isinstance(expected, str):
            return False, f"{field}({actual!r}) 或 {expected!r} 不是字符串"
        if op == "starts_with":
            return actual.startswith(expected), f"{field}({actual!r}) starts_with {expected!r}"
        if op == "ends_with":
            return actual.endswith(expected), f"{field}({actual!r}) ends_with {expected!r}"
        return bool(re.search(expected, actual)), f"{field}({actual!r}) matches /{expected}/"

    if op in ("contains", "not_contains"):
        if not isinstance(actual, (list, tuple, str, set)):
            return False, f"{field}({actual!r}) 不是集合/字符串，无法包含判断"
        result = expected in actual
        if op == "not_contains":
            result = not result
        return result, f"{field}({actual!r}) {op} {expected!r}"

    if op in ("in", "not_in"):
        if not isinstance(expected, (list, tuple, set)):
            return False, f"value {expected!r} 不是列表，无法做 in 判断"
        result = actual in expected
        if op == "not_in":
            result = not result
        return result, f"{field}({actual!r}) {op} {expected!r}"

    return False, f"未知操作符 {op!r}"


def evaluate(node, facts, trace=None, path="condition"):
    """递归求值条件树，返回 (matched, details)。"""
    if "all" in node:
        children = node["all"]
        results = [evaluate(c, facts, trace, f"{path}.all[{i}]") for i, c in enumerate(children)]
        matched = all(r for r, _ in results)
        details = [d for _, ds in results for d in ds]
        return matched, details
    if "any" in node:
        children = node["any"]
        results = [evaluate(c, facts, trace, f"{path}.any[{i}]") for i, c in enumerate(children)]
        matched = any(r for r, _ in results)
        details = [d for _, ds in results for d in ds]
        return matched, details
    if "not" in node:
        matched, details = evaluate(node["not"], facts, trace, f"{path}.not")
        return (not matched), details
    matched, detail = evaluate_leaf(node, facts)
    return matched, [f"{'PASS' if matched else 'FAIL'}: {detail}"]
