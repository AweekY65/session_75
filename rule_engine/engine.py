"""Agenda-based local rule engine.

Execution model:
  1. Evaluate every rule's conditions against the current facts.
  2. Eligible matches are sorted by (-priority, definition order) so the
     highest priority rule fires first and ties break deterministically.
  3. The winning rule's actions mutate the fact store; mutations may
     activate other rules on the next cycle (chaining).
  4. A rule fires at most once unless it declares ``repeat: true``. A
     repeating rule that produces no fact change is retired, and the
     global ``max_steps`` budget guarantees termination; exhausting it
     stops the run and reports the rules involved in the loop.
"""

from dataclasses import dataclass, field

from . import conditions as cond
from .validation import validate_rules

STATUS_COMPLETED = "completed"
STATUS_MAX_STEPS_EXCEEDED = "max_steps_exceeded"


@dataclass
class Rule:
    id: str
    conditions: dict
    actions: list
    priority: float = 0
    repeat: bool = False
    index: int = 0  # definition order, used as stable tie-break


@dataclass
class ExecutionResult:
    facts: dict
    status: str
    steps: int
    trace: list = field(default_factory=list)
    fired_rules: list = field(default_factory=list)
    cycle_candidates: list = field(default_factory=list)

    @property
    def ok(self):
        return self.status == STATUS_COMPLETED


def _apply_actions(rule, facts, trace, step):
    """Apply a rule's actions. Returns the list of fact changes."""
    changes = []
    for action in rule.actions:
        kind, spec = next(iter(action.items()))
        name = spec["field"]
        old = facts.get(name, cond.MISSING)

        if kind == "set":
            new = spec["value"]
        elif kind == "add":
            if old is cond.MISSING:
                old = 0
            if not isinstance(old, (int, float)) or isinstance(old, bool):
                trace.append({
                    "event": "action_error", "step": step, "rule_id": rule.id,
                    "detail": f"cannot 'add' on non-numeric fact {name!r}",
                })
                continue
            new = old + spec["value"]
        elif kind == "append":
            if old is cond.MISSING:
                old = []
            if not isinstance(old, list):
                trace.append({
                    "event": "action_error", "step": step, "rule_id": rule.id,
                    "detail": f"cannot 'append' on non-list fact {name!r}",
                })
                continue
            new = old + [spec["value"]]
        elif kind == "remove":
            if old is cond.MISSING:
                continue
            new = cond.MISSING
        else:  # pragma: no cover - guarded by validation
            raise ValueError(f"unknown action: {kind!r}")

        if new is cond.MISSING:
            facts.pop(name, None)
        else:
            facts[name] = new
        change = {
            "event": "fact_modified", "step": step, "rule_id": rule.id,
            "field": name,
            "old": None if old is cond.MISSING else old,
            "new": None if new is cond.MISSING else new,
        }
        if old is cond.MISSING:
            change["old"] = None
            change["created"] = True
        if new is cond.MISSING:
            change["new"] = None
            change["removed"] = True
        trace.append(change)
        changes.append(change)
    return changes


class RuleEngine:
    def __init__(self, rules, max_steps=1000):
        validate_rules(rules)
        if max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        self.rules = [
            Rule(
                id=r["id"],
                conditions=r["conditions"],
                actions=r["actions"],
                priority=r.get("priority", 0),
                repeat=r.get("repeat", False),
                index=i,
            )
            for i, r in enumerate(rules)
        ]
        self.max_steps = max_steps

    def run(self, facts):
        facts = dict(facts)
        trace = []
        fired_counts = {r.id: 0 for r in self.rules}
        retired = set()  # repeat rules that stopped producing changes
        fired_order = []
        step = 0

        while True:
            matched = []
            for rule in self.rules:
                notes = []
                hit = cond.evaluate(rule.conditions, facts, notes)
                trace.append({
                    "event": "rule_checked", "step": step, "rule_id": rule.id,
                    "matched": hit, "notes": notes,
                })
                if not hit:
                    continue
                if rule.id in retired:
                    continue
                if fired_counts[rule.id] > 0 and not rule.repeat:
                    continue  # no-loop: each rule fires at most once
                matched.append(rule)

            if not matched:
                trace.append({"event": "terminated", "reason": STATUS_COMPLETED,
                              "steps": step})
                return ExecutionResult(
                    facts=facts, status=STATUS_COMPLETED, steps=step,
                    trace=trace, fired_rules=fired_order,
                )

            # Conflict resolution: highest priority, then definition order.
            matched.sort(key=lambda r: (-r.priority, r.index))
            rule = matched[0]

            step += 1
            if step > self.max_steps:
                cycle = sorted(rid for rid, n in fired_counts.items() if n > 1)
                if not cycle:
                    cycle = [r.id for r in matched]
                trace.append({
                    "event": "terminated", "reason": STATUS_MAX_STEPS_EXCEEDED,
                    "steps": self.max_steps, "cycle_candidates": cycle,
                })
                return ExecutionResult(
                    facts=facts, status=STATUS_MAX_STEPS_EXCEEDED,
                    steps=self.max_steps, trace=trace, fired_rules=fired_order,
                    cycle_candidates=cycle,
                )

            fired_counts[rule.id] += 1
            fired_order.append(rule.id)
            trace.append({
                "event": "rule_fired", "step": step, "rule_id": rule.id,
                "priority": rule.priority,
            })
            changes = _apply_actions(rule, facts, trace, step)
            effective = any(
                c.get("created") or c.get("removed") or c["old"] != c["new"]
                for c in changes
            )
            if rule.repeat and not effective:
                retired.add(rule.id)
                trace.append({
                    "event": "rule_retired", "step": step, "rule_id": rule.id,
                    "detail": "repeat rule produced no fact change",
                })
