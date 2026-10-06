"""规则执行引擎：agenda、冲突消解、链式触发与循环保护。"""

import copy
import json
from dataclasses import dataclass, field as dc_field

from .conditions import evaluate
from .errors import RuleEngineError

DEFAULT_MAX_STEPS = 1000


@dataclass
class Rule:
    id: str
    conditions: dict
    actions: list
    priority: float = 0
    repeat: bool = False
    index: int = 0  # 定义顺序，用于稳定 tie-break

    @classmethod
    def from_dict(cls, data, index):
        return cls(
            id=data["id"],
            conditions=data["conditions"],
            actions=data["actions"],
            priority=data.get("priority", 0),
            repeat=data.get("repeat", False),
            index=index,
        )


@dataclass
class ExecutionResult:
    status: str
    steps: int
    facts: dict
    trace: list = dc_field(default_factory=list)
    fired_rules: list = dc_field(default_factory=list)
    cycle: list = dc_field(default_factory=list)

    def to_dict(self):
        return {
            "status": self.status,
            "steps": self.steps,
            "facts": self.facts,
            "fired_rules": self.fired_rules,
            "cycle": self.cycle,
            "trace": self.trace,
        }


def _apply_action(action, facts, trace, step, rule_id):
    kind, body = next(iter(action.items()))
    field = body["field"]
    old = copy.deepcopy(facts.get(field, None))
    existed = field in facts

    if kind == "set":
        facts[field] = copy.deepcopy(body["value"])
    elif kind == "add":
        current = facts.get(field, 0)
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise RuleEngineError(
                f"规则 {rule_id!r}: 无法对非数值 fact {field!r}({current!r}) 执行 add"
            )
        facts[field] = current + body["value"]
    elif kind == "append":
        if not existed:
            facts[field] = []
        if not isinstance(facts[field], list):
            raise RuleEngineError(
                f"规则 {rule_id!r}: 无法对非列表 fact {field!r} 执行 append"
            )
        facts[field].append(copy.deepcopy(body["value"]))
    elif kind == "remove":
        facts.pop(field, None)
    else:  # 静态校验已拦截，防御性处理
        raise RuleEngineError(f"规则 {rule_id!r}: 未知 action {kind!r}")

    new = copy.deepcopy(facts.get(field, None))
    changed = (not existed and field in facts) or old != new or (existed and field not in facts)
    trace.append({
        "event": "change",
        "step": step,
        "rule": rule_id,
        "action": kind,
        "field": field,
        "old": old if existed else None,
        "new": new if field in facts else None,
        "changed": changed,
    })
    return changed


def _detect_cycle(fired_sequence):
    """在触发序列末尾寻找最短重复模式，用于循环报告。"""
    n = len(fired_sequence)
    for size in range(1, n // 2 + 1):
        pattern = fired_sequence[n - size:]
        if fired_sequence[n - 2 * size:n - size] == pattern:
            return pattern
    return fired_sequence[-1:]


def run_engine(rule_dicts, facts, max_steps=DEFAULT_MAX_STEPS):
    """执行规则，返回 ExecutionResult。

    每步对所有规则求值，按 (-priority, 定义顺序) 选出最高优先级的
    可执行规则并触发；新事实可在后续步骤触发其他规则（链式触发）。
    """
    rules = sorted(
        (Rule.from_dict(d, i) for i, d in enumerate(rule_dicts)),
        key=lambda r: (-r.priority, r.index),
    )
    facts = copy.deepcopy(facts)
    trace = []
    fired_sequence = []
    fired_count = {r.id: 0 for r in rules}
    quiesced = set()
    status = "completed"
    steps = 0

    while steps < max_steps:
        eligible = []
        for rule in rules:
            matched, details = evaluate(rule.conditions, facts)
            trace.append({
                "event": "check",
                "step": steps,
                "rule": rule.id,
                "matched": matched,
                "details": details,
            })
            if not matched:
                continue
            if rule.id in quiesced:
                continue
            if not rule.repeat and fired_count[rule.id] > 0:
                continue
            eligible.append(rule)

        if not eligible:
            break

        rule = eligible[0]
        trace.append({"event": "fire", "step": steps, "rule": rule.id,
                      "priority": rule.priority})
        changed_any = False
        for action in rule.actions:
            if _apply_action(action, facts, trace, steps, rule.id):
                changed_any = True

        fired_count[rule.id] += 1
        fired_sequence.append(rule.id)
        steps += 1

        if rule.repeat and not changed_any:
            # 重复触发且未改变任何事实：继续执行只会原地空转，隔离该规则
            quiesced.add(rule.id)
            trace.append({
                "event": "quiesce",
                "step": steps,
                "rule": rule.id,
                "reason": "重复触发未改变任何 fact，已隔离以避免无限循环",
            })
    else:
        status = "max_steps_reached"

    result = ExecutionResult(
        status=status,
        steps=steps,
        facts=facts,
        trace=trace,
        fired_rules=fired_sequence,
    )
    if status == "max_steps_reached":
        result.cycle = _detect_cycle(fired_sequence)
        trace.append({
            "event": "halt",
            "step": steps,
            "reason": f"达到最大执行步数 {max_steps}，疑似规则循环",
            "cycle": result.cycle,
        })
    else:
        trace.append({"event": "halt", "step": steps, "reason": "无可执行规则，正常结束"})
    return result


def result_to_json(result):
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
