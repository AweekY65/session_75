"""执行引擎测试：优先级、链式触发、冲突、循环、缺失 fact、确定性。"""

import pytest

from rule_engine import RuleEngineError, run_engine


def make_rule(rule_id, priority=0, conditions=None, actions=None, repeat=False):
    return {
        "id": rule_id,
        "priority": priority,
        "repeat": repeat,
        "conditions": conditions or {"field": "go", "op": "eq", "value": True},
        "actions": actions or [{"set": {"field": "done", "value": True}}],
    }


def fires(result):
    return [e["rule"] for e in result.trace if e["event"] == "fire"]


class TestPriorityAndTieBreak:
    def test_higher_priority_fires_first(self):
        rules = [
            make_rule("low", priority=1, actions=[{"append": {"field": "order", "value": "low"}}]),
            make_rule("high", priority=9, actions=[{"append": {"field": "order", "value": "high"}}]),
            make_rule("mid", priority=5, actions=[{"append": {"field": "order", "value": "mid"}}]),
        ]
        result = run_engine(rules, {"go": True})
        assert fires(result) == ["high", "mid", "low"]
        assert result.facts["order"] == ["high", "mid", "low"]

    def test_equal_priority_uses_definition_order(self):
        rules = [
            make_rule("first", actions=[{"append": {"field": "order", "value": "first"}}]),
            make_rule("second", actions=[{"append": {"field": "order", "value": "second"}}]),
            make_rule("third", actions=[{"append": {"field": "order", "value": "third"}}]),
        ]
        result = run_engine(rules, {"go": True})
        assert fires(result) == ["first", "second", "third"]

    def test_conflicting_rules_resolved_by_priority(self):
        # 两条规则写同一字段，高优先级先执行；no-loop 下低优先级后执行覆盖
        rules = [
            make_rule("standard", priority=1,
                      actions=[{"set": {"field": "level", "value": "standard"}}]),
            make_rule("premium", priority=10,
                      actions=[{"set": {"field": "level", "value": "premium"}}]),
        ]
        result = run_engine(rules, {"go": True})
        assert fires(result) == ["premium", "standard"]
        assert result.facts["level"] == "standard"

    def test_conflicting_rules_low_priority_blocked_by_condition(self):
        # 高优先级规则修改 fact 后，冲突的低优先级规则条件不再满足
        rules = [
            make_rule("guard", priority=10,
                      actions=[{"set": {"field": "go", "value": False}}]),
            make_rule("blocked", priority=1,
                      actions=[{"set": {"field": "level", "value": "x"}}]),
        ]
        result = run_engine(rules, {"go": True})
        assert fires(result) == ["guard"]
        assert "level" not in result.facts


class TestChainedFiring:
    def test_new_fact_triggers_followup_rule(self):
        rules = [
            {
                "id": "produce",
                "priority": 5,
                "conditions": {"field": "age", "op": "ge", "value": 65},
                "actions": [{"set": {"field": "senior", "value": True}}],
            },
            {
                "id": "consume",
                "priority": 1,
                "conditions": {"field": "senior", "op": "eq", "value": True},
                "actions": [{"set": {"field": "discount", "value": 0.3}}],
            },
        ]
        result = run_engine(rules, {"age": 70})
        assert fires(result) == ["produce", "consume"]
        assert result.facts["discount"] == 0.3

    def test_no_loop_rule_fires_at_most_once(self):
        rules = [{
            "id": "self",
            "conditions": {"field": "n", "op": "lt", "value": 100},
            "actions": [{"add": {"field": "n", "value": 1}}],
        }]
        result = run_engine(rules, {"n": 0})
        assert fires(result) == ["self"]
        assert result.facts["n"] == 1
        assert result.status == "completed"


class TestLoopProtection:
    def test_repeat_rule_stops_when_no_change(self):
        rules = [{
            "id": "noop",
            "repeat": True,
            "conditions": {"field": "flag", "op": "eq", "value": True},
            "actions": [{"set": {"field": "flag", "value": True}}],
        }]
        result = run_engine(rules, {"flag": True})
        assert result.status == "completed"
        assert fires(result) == ["noop"]
        assert any(e["event"] == "quiesce" and e["rule"] == "noop" for e in result.trace)

    def test_cycle_stops_at_max_steps_and_reports(self):
        rules = [
            {
                "id": "a",
                "priority": 2,
                "repeat": True,
                "conditions": {"field": "x", "op": "eq", "value": 1},
                "actions": [{"set": {"field": "x", "value": 2}}],
            },
            {
                "id": "b",
                "priority": 1,
                "repeat": True,
                "conditions": {"field": "x", "op": "eq", "value": 2},
                "actions": [{"set": {"field": "x", "value": 1}}],
            },
        ]
        result = run_engine(rules, {"x": 1}, max_steps=10)
        assert result.status == "max_steps_reached"
        assert result.steps == 10
        assert result.cycle == ["a", "b"]
        halt = [e for e in result.trace if e["event"] == "halt"][-1]
        assert "循环" in halt["reason"]

    def test_repeat_rule_counts_down_to_completion(self):
        rules = [{
            "id": "count",
            "repeat": True,
            "conditions": {"field": "n", "op": "lt", "value": 5},
            "actions": [{"add": {"field": "n", "value": 1}}],
        }]
        result = run_engine(rules, {"n": 0})
        assert result.status == "completed"
        assert result.facts["n"] == 5
        assert fires(result) == ["count"] * 5


class TestConditions:
    def test_missing_fact_is_not_matched_and_traced(self):
        rules = [make_rule("needs-fact", conditions={"field": "ghost", "op": "eq", "value": 1})]
        result = run_engine(rules, {})
        assert result.status == "completed"
        assert fires(result) == []
        check = [e for e in result.trace if e["event"] == "check"][0]
        assert check["matched"] is False
        assert any("缺失" in d for d in check["details"])

    def test_string_and_collection_operators(self):
        rules = [
            make_rule("r1", conditions={"all": [
                {"field": "name", "op": "starts_with", "value": "Al"},
                {"field": "tags", "op": "contains", "value": "vip"},
                {"any": [
                    {"field": "name", "op": "matches", "value": r"^Al.*e$"},
                    {"field": "name", "op": "ends_with", "value": "z"},
                ]},
                {"not": {"field": "role", "op": "in", "value": ["banned", "muted"]}},
            ]}),
        ]
        result = run_engine(rules, {"name": "Alice", "tags": ["vip"], "role": "user"})
        assert fires(result) == ["r1"]

    def test_type_mismatch_is_not_matched(self):
        rules = [make_rule("r", conditions={"field": "n", "op": "gt", "value": 3})]
        result = run_engine(rules, {"n": "not-a-number"})
        assert fires(result) == []


class TestTraceAndDeterminism:
    def test_trace_records_checks_fires_and_changes(self):
        rules = [make_rule("r", actions=[{"set": {"field": "x", "value": 1}}])]
        result = run_engine(rules, {"go": True})
        events = [e["event"] for e in result.trace]
        assert "check" in events and "fire" in events and "change" in events
        change = [e for e in result.trace if e["event"] == "change"][0]
        assert change["field"] == "x" and change["old"] is None and change["new"] == 1

    def test_execution_is_deterministic(self):
        rules = [
            make_rule("b", priority=1, actions=[{"append": {"field": "log", "value": "b"}}]),
            make_rule("a", priority=1, actions=[{"append": {"field": "log", "value": "a"}}]),
            make_rule("c", priority=2, actions=[{"append": {"field": "log", "value": "c"}}]),
        ]
        first = run_engine(rules, {"go": True}).to_dict()
        second = run_engine(rules, {"go": True}).to_dict()
        assert first == second
        assert first["facts"]["log"] == ["c", "b", "a"]

    def test_input_facts_are_not_mutated(self):
        facts = {"go": True}
        run_engine([make_rule("r")], facts)
        assert facts == {"go": True}

    def test_add_on_non_numeric_fact_raises(self):
        rules = [make_rule("r", actions=[{"add": {"field": "s", "value": 1}}])]
        with pytest.raises(RuleEngineError):
            run_engine(rules, {"go": True, "s": "text"})
