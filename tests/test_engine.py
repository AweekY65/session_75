from rule_engine import STATUS_COMPLETED, STATUS_MAX_STEPS_EXCEEDED, RuleEngine


def run(rules, facts, max_steps=1000):
    return RuleEngine(rules, max_steps=max_steps).run(facts)


def test_priority_orders_execution():
    rules = [
        {"id": "low", "priority": 1,
         "conditions": {"field": "x", "op": "eq", "value": 1},
         "actions": [{"set": {"field": "order", "value": ["low"]}}]},
        {"id": "high", "priority": 10,
         "conditions": {"field": "x", "op": "eq", "value": 1},
         "actions": [{"set": {"field": "winner", "value": "high"}}]},
    ]
    result = run(rules, {"x": 1})
    assert result.status == STATUS_COMPLETED
    assert result.fired_rules[0] == "high"
    assert result.facts["winner"] == "high"


def test_stable_tiebreak_for_equal_priority():
    rules = [
        {"id": "second-defined",
         "conditions": {"field": "x", "op": "eq", "value": 1},
         "actions": [{"append": {"field": "log", "value": "b"}}]},
        {"id": "first-defined",
         "conditions": {"field": "x", "op": "eq", "value": 1},
         "actions": [{"append": {"field": "log", "value": "a"}}]},
    ]
    result = run(rules, {"x": 1})
    # Same priority (default 0): definition order wins.
    assert result.fired_rules == ["second-defined", "first-defined"]
    assert result.facts["log"] == ["b", "a"]


def test_chained_triggering():
    rules = [
        {"id": "r1", "priority": 5,
         "conditions": {"field": "temp", "op": "gt", "value": 30},
         "actions": [{"set": {"field": "hot", "value": True}}]},
        {"id": "r2", "priority": 1,
         "conditions": {"field": "hot", "op": "eq", "value": True},
         "actions": [{"set": {"field": "ac_on", "value": True}}]},
    ]
    result = run(rules, {"temp": 35})
    assert result.fired_rules == ["r1", "r2"]
    assert result.facts["ac_on"] is True


def test_rule_fires_at_most_once_by_default():
    rules = [
        {"id": "self-sustaining",
         "conditions": {"field": "n", "op": "ge", "value": 1},
         "actions": [{"add": {"field": "n", "value": 1}}]},
    ]
    result = run(rules, {"n": 1})
    assert result.status == STATUS_COMPLETED
    assert result.fired_rules == ["self-sustaining"]
    assert result.facts["n"] == 2


def test_repeat_rule_loops_until_condition_fails():
    rules = [
        {"id": "countdown", "repeat": True,
         "conditions": {"field": "n", "op": "gt", "value": 0},
         "actions": [{"add": {"field": "n", "value": -1}}]},
    ]
    result = run(rules, {"n": 5})
    assert result.status == STATUS_COMPLETED
    assert result.facts["n"] == 0
    assert result.fired_rules == ["countdown"] * 5


def test_cycle_stops_at_max_steps_and_reports():
    rules = [
        {"id": "ping", "repeat": True, "priority": 1,
         "conditions": {"field": "ball", "op": "eq", "value": "ping"},
         "actions": [{"set": {"field": "ball", "value": "pong"}}]},
        {"id": "pong", "repeat": True,
         "conditions": {"field": "ball", "op": "eq", "value": "pong"},
         "actions": [{"set": {"field": "ball", "value": "ping"}}]},
    ]
    result = run(rules, {"ball": "ping"}, max_steps=10)
    assert result.status == STATUS_MAX_STEPS_EXCEEDED
    assert result.steps == 10
    assert set(result.cycle_candidates) == {"ping", "pong"}
    reasons = [e for e in result.trace if e["event"] == "terminated"]
    assert reasons[0]["reason"] == STATUS_MAX_STEPS_EXCEEDED


def test_repeat_rule_retires_when_no_change():
    rules = [
        {"id": "noop", "repeat": True,
         "conditions": {"field": "x", "op": "eq", "value": 1},
         "actions": [{"set": {"field": "y", "value": 1}}]},
    ]
    # First firing creates y; the second firing would set the same value,
    # so the rule is retired instead of looping forever.
    result = run(rules, {"x": 1})
    assert result.status == STATUS_COMPLETED
    assert result.fired_rules == ["noop", "noop"]
    assert result.facts["y"] == 1
    assert any(e["event"] == "rule_retired" for e in result.trace)


def test_missing_fact_does_not_match_and_is_traced():
    rules = [
        {"id": "needs-age",
         "conditions": {"field": "age", "op": "ge", "value": 18},
         "actions": [{"set": {"field": "adult", "value": True}}]},
    ]
    result = run(rules, {"name": "kim"})
    assert result.fired_rules == []
    assert "adult" not in result.facts
    checked = [e for e in result.trace if e["event"] == "rule_checked"]
    assert checked[0]["matched"] is False
    assert any("missing fact" in n for n in checked[0]["notes"])


def test_boolean_combinators_and_collection_ops():
    rules = [
        {"id": "combo",
         "conditions": {"all": [
             {"any": [
                 {"field": "role", "op": "eq", "value": "admin"},
                 {"field": "role", "op": "eq", "value": "root"},
             ]},
             {"not": {"field": "banned", "op": "eq", "value": True}},
             {"field": "tags", "op": "contains", "value": "staff"},
             {"field": "level", "op": "in", "value": [3, 4, 5]},
             {"field": "name", "op": "starts_with", "value": "a"},
         ]},
         "actions": [{"set": {"field": "allowed", "value": True}}]},
    ]
    facts = {"role": "admin", "banned": False, "tags": ["staff", "ops"],
             "level": 4, "name": "amy"}
    result = run(rules, facts)
    assert result.facts["allowed"] is True

    facts["level"] = 9
    result = run(rules, facts)
    assert "allowed" not in result.facts


def test_actions_add_append_remove():
    rules = [
        {"id": "mutate",
         "conditions": {"field": "go", "op": "eq", "value": True},
         "actions": [
             {"add": {"field": "count", "value": 2}},
             {"append": {"field": "items", "value": "x"}},
             {"remove": {"field": "go"}},
         ]},
    ]
    result = run(rules, {"go": True, "count": 1, "items": []})
    assert result.facts["count"] == 3
    assert result.facts["items"] == ["x"]
    assert "go" not in result.facts


def test_conflicting_rules_resolve_deterministically():
    # Both rules match and write the same fact; higher priority wins first,
    # and the whole run is reproducible.
    rules = [
        {"id": "discount-a", "priority": 5,
         "conditions": {"field": "vip", "op": "eq", "value": True},
         "actions": [{"set": {"field": "discount", "value": 0.2}}]},
        {"id": "discount-b", "priority": 5,
         "conditions": {"field": "vip", "op": "eq", "value": True},
         "actions": [{"set": {"field": "discount", "value": 0.1}}]},
    ]
    first = run(rules, {"vip": True})
    second = run(rules, {"vip": True})
    assert first.fired_rules == second.fired_rules == ["discount-a", "discount-b"]
    assert first.facts == second.facts
    assert first.trace == second.trace
    # discount-b fires last, so its value remains.
    assert first.facts["discount"] == 0.1


def test_trace_records_checked_fired_and_modified():
    rules = [
        {"id": "hit",
         "conditions": {"field": "x", "op": "eq", "value": 1},
         "actions": [{"set": {"field": "y", "value": 2}}]},
        {"id": "miss",
         "conditions": {"field": "x", "op": "eq", "value": 99},
         "actions": [{"set": {"field": "z", "value": 3}}]},
    ]
    result = run(rules, {"x": 1})
    events = [e["event"] for e in result.trace]
    assert "rule_checked" in events
    assert "rule_fired" in events
    assert "fact_modified" in events
    modified = [e for e in result.trace if e["event"] == "fact_modified"]
    assert modified[0]["rule_id"] == "hit"
    assert modified[0]["field"] == "y"
    assert modified[0]["old"] is None
    assert modified[0]["new"] == 2
    fired = [e for e in result.trace if e["event"] == "rule_fired"]
    assert [e["rule_id"] for e in fired] == ["hit"]
