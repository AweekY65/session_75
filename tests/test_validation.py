"""静态校验与加载测试：缺失字段、非法操作符、重复 ID、非法表达式。"""

import json

import pytest

from rule_engine import RuleValidationError, load_facts, load_rules, validate_rules


def valid_rule(rule_id="r1"):
    return {
        "id": rule_id,
        "conditions": {"field": "x", "op": "eq", "value": 1},
        "actions": [{"set": {"field": "y", "value": 2}}],
    }


def issues_of(data):
    with pytest.raises(RuleValidationError) as excinfo:
        validate_rules(data)
    return excinfo.value.issues


class TestValidation:
    def test_valid_rule_passes(self):
        rules = validate_rules({"rules": [valid_rule()]})
        assert rules[0]["id"] == "r1"

    def test_missing_required_fields(self):
        issues = issues_of([{"id": "r1"}])
        assert any("conditions" in i for i in issues)
        assert any("actions" in i for i in issues)

    def test_missing_id(self):
        rule = valid_rule()
        del rule["id"]
        assert any("id" in i for i in issues_of([rule]))

    def test_duplicate_ids_rejected(self):
        issues = issues_of([valid_rule("dup"), valid_rule("dup")])
        assert any("重复" in i and "dup" in i for i in issues)

    def test_illegal_operator(self):
        rule = valid_rule()
        rule["conditions"] = {"field": "x", "op": "~~", "value": 1}
        assert any("非法操作符" in i for i in issues_of([rule]))

    def test_numeric_op_requires_number(self):
        rule = valid_rule()
        rule["conditions"] = {"field": "x", "op": "gt", "value": "three"}
        assert any("数值" in i for i in issues_of([rule]))

    def test_unparseable_regex_rejected(self):
        rule = valid_rule()
        rule["conditions"] = {"field": "x", "op": "matches", "value": "([unclosed"}
        assert any("正则" in i for i in issues_of([rule]))

    def test_leaf_condition_missing_value(self):
        rule = valid_rule()
        rule["conditions"] = {"field": "x", "op": "eq"}
        assert any("缺失字段" in i for i in issues_of([rule]))

    def test_empty_boolean_combination_rejected(self):
        rule = valid_rule()
        rule["conditions"] = {"all": []}
        assert any("非空列表" in i for i in issues_of([rule]))

    def test_illegal_action(self):
        rule = valid_rule()
        rule["actions"] = [{"explode": {"field": "x"}}]
        assert any("非法 action" in i for i in issues_of([rule]))

    def test_add_requires_numeric_value(self):
        rule = valid_rule()
        rule["actions"] = [{"add": {"field": "x", "value": "one"}}]
        assert any("数值" in i for i in issues_of([rule]))

    def test_non_list_document_rejected(self):
        with pytest.raises(RuleValidationError):
            validate_rules({"not_rules": {}})


class TestLoader:
    def test_load_json_rules_and_facts(self, tmp_path):
        rules_path = tmp_path / "rules.json"
        rules_path.write_text(json.dumps({"rules": [valid_rule()]}), encoding="utf-8")
        facts_path = tmp_path / "facts.json"
        facts_path.write_text(json.dumps({"x": 1}), encoding="utf-8")
        assert load_rules(str(rules_path))[0]["id"] == "r1"
        assert load_facts(str(facts_path)) == {"x": 1}

    def test_load_yaml_rules(self, tmp_path):
        path = tmp_path / "rules.yaml"
        path.write_text(
            "rules:\n"
            "  - id: r1\n"
            "    conditions: {field: x, op: eq, value: 1}\n"
            "    actions:\n"
            "      - set: {field: y, value: 2}\n",
            encoding="utf-8",
        )
        assert load_rules(str(path))[0]["id"] == "r1"

    def test_invalid_rule_file_raises_with_issues(self, tmp_path):
        path = tmp_path / "rules.yaml"
        path.write_text("rules:\n  - id: a\n  - id: a\n", encoding="utf-8")
        with pytest.raises(RuleValidationError) as excinfo:
            load_rules(str(path))
        assert any("重复" in i for i in excinfo.value.issues)

    def test_unparseable_file_raises(self, tmp_path):
        path = tmp_path / "rules.json"
        path.write_text("{not json", encoding="utf-8")
        from rule_engine import RuleEngineError
        with pytest.raises(RuleEngineError):
            load_rules(str(path))
