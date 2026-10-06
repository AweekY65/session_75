import pytest

from rule_engine import RuleValidationError, validate_rules


def problems_of(rules):
    with pytest.raises(RuleValidationError) as excinfo:
        validate_rules(rules)
    return excinfo.value.problems


def valid_rule(**overrides):
    rule = {
        "id": "r1",
        "conditions": {"field": "x", "op": "eq", "value": 1},
        "actions": [{"set": {"field": "y", "value": 2}}],
    }
    rule.update(overrides)
    return rule


def test_valid_rule_set_passes():
    assert validate_rules([valid_rule()]) == [valid_rule()]


def test_missing_required_fields():
    problems = problems_of([{"priority": 1}])
    text = "\n".join(problems)
    assert "'id'" in text
    assert "conditions" in text
    assert "actions" in text


def test_illegal_operator():
    rule = valid_rule(conditions={"field": "x", "op": "~~", "value": 1})
    problems = problems_of([rule])
    assert any("illegal operator" in p for p in problems)


def test_duplicate_ids_rejected():
    problems = problems_of([valid_rule(), valid_rule()])
    assert any("duplicate rule id" in p for p in problems)


def test_numeric_op_requires_numeric_value():
    rule = valid_rule(conditions={"field": "x", "op": "gt", "value": "high"})
    problems = problems_of([rule])
    assert any("requires a numeric value" in p for p in problems)


def test_in_operator_requires_list():
    rule = valid_rule(conditions={"field": "x", "op": "in", "value": "abc"})
    problems = problems_of([rule])
    assert any("requires a list value" in p for p in problems)


def test_unparseable_regex_detected():
    rule = valid_rule(conditions={"field": "x", "op": "matches", "value": "(["})
    problems = problems_of([rule])
    assert any("unparseable regex" in p for p in problems)


def test_boolean_combinator_must_be_non_empty():
    rule = valid_rule(conditions={"all": []})
    problems = problems_of([rule])
    assert any("non-empty list" in p for p in problems)


def test_bad_action_detected():
    rule = valid_rule(actions=[{"teleport": {"field": "y"}}])
    problems = problems_of([rule])
    assert any("unknown action" in p for p in problems)

    rule = valid_rule(actions=[{"add": {"field": "y", "value": "lots"}}])
    problems = problems_of([rule])
    assert any("must be numeric" in p for p in problems)


def test_nested_condition_errors_are_located():
    rule = valid_rule(conditions={
        "any": [
            {"field": "x", "op": "eq", "value": 1},
            {"field": "y", "op": "bogus", "value": 2},
        ]
    })
    problems = problems_of([rule])
    assert any("any[1]" in p and "illegal operator" in p for p in problems)
