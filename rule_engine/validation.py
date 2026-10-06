"""规则静态校验：缺失字段、非法操作符、重复 ID、不可解析表达式。"""

import re

from .conditions import ALL_OPS, NUMERIC_OPS, STRING_OPS
from .errors import RuleValidationError

ACTION_KEYS = {"set", "add", "append", "remove"}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_condition(node, where, issues):
    if not isinstance(node, dict):
        issues.append(f"{where}: 条件必须是对象，得到 {type(node).__name__}")
        return
    combinators = [k for k in ("all", "any", "not") if k in node]
    if combinators:
        if len(combinators) > 1:
            issues.append(f"{where}: 一个条件节点只能使用一个布尔组合符，得到 {combinators}")
        key = combinators[0]
        if key in ("all", "any"):
            children = node[key]
            if not isinstance(children, list) or not children:
                issues.append(f"{where}.{key}: 必须是非空列表")
                return
            for i, child in enumerate(children):
                _validate_condition(child, f"{where}.{key}[{i}]", issues)
        else:
            _validate_condition(node["not"], f"{where}.not", issues)
        return

    missing = [k for k in ("field", "op", "value") if k not in node]
    if missing:
        issues.append(f"{where}: 叶子条件缺失字段 {missing}")
        return
    if not isinstance(node["field"], str) or not node["field"]:
        issues.append(f"{where}.field: 必须是非空字符串")
    op = node["op"]
    if op not in ALL_OPS:
        issues.append(f"{where}.op: 非法操作符 {op!r}，支持 {sorted(ALL_OPS)}")
        return
    value = node["value"]
    if op in NUMERIC_OPS and not _is_number(value):
        issues.append(f"{where}.value: 操作符 {op} 要求数值，得到 {value!r}")
    if op in ("starts_with", "ends_with") and not isinstance(value, str):
        issues.append(f"{where}.value: 操作符 {op} 要求字符串，得到 {value!r}")
    if op == "matches":
        if not isinstance(value, str):
            issues.append(f"{where}.value: matches 要求字符串正则，得到 {value!r}")
        else:
            try:
                re.compile(value)
            except re.error as exc:
                issues.append(f"{where}.value: 正则无法解析 {value!r}: {exc}")
    if op in ("in", "not_in") and not isinstance(value, list):
        issues.append(f"{where}.value: 操作符 {op} 要求列表，得到 {value!r}")


def _validate_action(action, where, issues):
    if not isinstance(action, dict) or len(action) != 1:
        issues.append(f"{where}: action 必须是只含一个键的对象，得到 {action!r}")
        return
    kind = next(iter(action))
    if kind not in ACTION_KEYS:
        issues.append(f"{where}: 非法 action 类型 {kind!r}，支持 {sorted(ACTION_KEYS)}")
        return
    body = action[kind]
    if not isinstance(body, dict):
        issues.append(f"{where}.{kind}: 必须是对象")
        return
    field = body.get("field")
    if not isinstance(field, str) or not field:
        issues.append(f"{where}.{kind}.field: 必须是非空字符串")
    if kind in ("set", "add", "append") and "value" not in body:
        issues.append(f"{where}.{kind}: 缺失 value")
    if kind == "add" and "value" in body and not _is_number(body["value"]):
        issues.append(f"{where}.add.value: 必须是数值，得到 {body['value']!r}")


def validate_rules(data):
    """校验规则文档，返回规则列表；有问题时抛出 RuleValidationError。"""
    issues = []
    if isinstance(data, dict) and "rules" in data:
        rules = data["rules"]
    else:
        rules = data
    if not isinstance(rules, list) or not rules:
        raise RuleValidationError(["规则文件必须是非空规则列表（或含 rules 列表的对象）"])

    seen_ids = set()
    for i, rule in enumerate(rules):
        where = f"rules[{i}]"
        if not isinstance(rule, dict):
            issues.append(f"{where}: 规则必须是对象")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            issues.append(f"{where}: 缺失或非法 id")
            rule_id = f"<第 {i} 条规则>"
        elif rule_id in seen_ids:
            issues.append(f"{where}: 重复的规则 id {rule_id!r}")
        else:
            seen_ids.add(rule_id)
        where = f"规则 {rule_id!r}"

        if "priority" in rule and not _is_number(rule["priority"]):
            issues.append(f"{where}: priority 必须是数值，得到 {rule['priority']!r}")
        if "repeat" in rule and not isinstance(rule["repeat"], bool):
            issues.append(f"{where}: repeat 必须是布尔值")

        if "conditions" not in rule:
            issues.append(f"{where}: 缺失 conditions")
        else:
            _validate_condition(rule["conditions"], f"{where}.conditions", issues)

        actions = rule.get("actions")
        if not isinstance(actions, list) or not actions:
            issues.append(f"{where}: actions 必须是非空列表")
        else:
            for j, action in enumerate(actions):
                _validate_action(action, f"{where}.actions[{j}]", issues)

    if issues:
        raise RuleValidationError(issues)
    return rules
