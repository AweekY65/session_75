"""Static validation of rule definitions.

Rules are plain dicts loaded from JSON/YAML. Validation runs before any
execution and reports every problem found (missing fields, illegal
operators, duplicate ids, obviously unparseable expressions).
"""

import re

from .errors import RuleValidationError

COMPARISON_OPS = {"eq", "ne", "gt", "ge", "lt", "le"}
STRING_OPS = {"starts_with", "ends_with", "matches"}
COLLECTION_OPS = {"contains", "not_contains", "in", "not_in"}
NUMERIC_OPS = {"gt", "ge", "lt", "le"}
ALL_OPS = COMPARISON_OPS | STRING_OPS | COLLECTION_OPS

ACTION_KEYS = {"set", "add", "append", "remove"}
BOOLEAN_KEYS = {"all", "any", "not"}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_condition(node, path, problems):
    if not isinstance(node, dict):
        problems.append(f"{path}: condition must be an object")
        return

    bool_keys = [k for k in node if k in BOOLEAN_KEYS]
    if bool_keys:
        if len(node) != 1:
            problems.append(
                f"{path}: boolean combinator cannot be mixed with other keys"
            )
        key = bool_keys[0]
        if key in ("all", "any"):
            children = node[key]
            if not isinstance(children, list) or not children:
                problems.append(f"{path}.{key}: must be a non-empty list")
            else:
                for i, child in enumerate(children):
                    _validate_condition(child, f"{path}.{key}[{i}]", problems)
        else:  # not
            child = node[key]
            if not isinstance(child, dict):
                problems.append(f"{path}.not: must be a single condition object")
            else:
                _validate_condition(child, f"{path}.not", problems)
        return

    # Leaf condition: {field, op, value}
    field = node.get("field")
    if not isinstance(field, str) or not field:
        problems.append(f"{path}: leaf condition requires a non-empty 'field'")

    op = node.get("op")
    if op is None:
        problems.append(f"{path}: leaf condition is missing 'op'")
    elif op not in ALL_OPS:
        problems.append(f"{path}: illegal operator {op!r}")

    if "value" not in node:
        problems.append(f"{path}: leaf condition is missing 'value'")
        return

    value = node["value"]
    if op in NUMERIC_OPS and not _is_number(value):
        problems.append(
            f"{path}: operator {op!r} requires a numeric value, got {value!r}"
        )
    if op in ("in", "not_in") and not isinstance(value, list):
        problems.append(
            f"{path}: operator {op!r} requires a list value, got {value!r}"
        )
    if op in ("starts_with", "ends_with", "matches") and not isinstance(value, str):
        problems.append(
            f"{path}: operator {op!r} requires a string value, got {value!r}"
        )
    if op == "matches" and isinstance(value, str):
        try:
            re.compile(value)
        except re.error as exc:
            problems.append(f"{path}: unparseable regex {value!r}: {exc}")


def _validate_action(action, path, problems):
    if not isinstance(action, dict) or len(action) != 1:
        problems.append(f"{path}: action must be an object with exactly one key")
        return
    kind, spec = next(iter(action.items()))
    if kind not in ACTION_KEYS:
        problems.append(f"{path}: unknown action {kind!r}")
        return
    if not isinstance(spec, dict):
        problems.append(f"{path}.{kind}: action body must be an object")
        return
    field = spec.get("field")
    if not isinstance(field, str) or not field:
        problems.append(f"{path}.{kind}: requires a non-empty 'field'")
    if kind in ("set", "add", "append"):
        if "value" not in spec:
            problems.append(f"{path}.{kind}: missing 'value'")
        elif kind == "add" and not _is_number(spec["value"]):
            problems.append(
                f"{path}.add: 'value' must be numeric, got {spec['value']!r}"
            )


def validate_rules(rules):
    """Validate a list of rule dicts. Raises RuleValidationError."""
    problems = []
    if not isinstance(rules, list):
        raise RuleValidationError(["rules document must be a list of rules"])

    seen_ids = set()
    for i, rule in enumerate(rules):
        path = f"rules[{i}]"
        if not isinstance(rule, dict):
            problems.append(f"{path}: rule must be an object")
            continue

        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            problems.append(f"{path}: rule requires a non-empty string 'id'")
        elif rule_id in seen_ids:
            problems.append(f"{path}: duplicate rule id {rule_id!r}")
        else:
            seen_ids.add(rule_id)
        path = f"rule({rule_id if isinstance(rule_id, str) else i})"

        if "priority" in rule and not _is_number(rule["priority"]):
            problems.append(f"{path}: 'priority' must be a number")
        if "repeat" in rule and not isinstance(rule["repeat"], bool):
            problems.append(f"{path}: 'repeat' must be a boolean")

        if "conditions" not in rule:
            problems.append(f"{path}: missing 'conditions'")
        else:
            _validate_condition(rule["conditions"], f"{path}.conditions", problems)

        actions = rule.get("actions")
        if not isinstance(actions, list) or not actions:
            problems.append(f"{path}: 'actions' must be a non-empty list")
        else:
            for j, action in enumerate(actions):
                _validate_action(action, f"{path}.actions[{j}]", problems)

    if problems:
        raise RuleValidationError(problems)
    return rules
