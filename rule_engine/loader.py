"""Load rules and facts from local JSON/YAML files. No external services."""

import json
import os

import yaml

from .errors import RuleFileError


def load_file(path):
    """Load a JSON or YAML file into Python data."""
    if not os.path.isfile(path):
        raise RuleFileError(f"file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".json":
            return json.loads(text)
        if ext in (".yaml", ".yml"):
            return yaml.safe_load(text)
        # Unknown extension: try JSON first, then YAML.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise RuleFileError(f"cannot parse {path}: {exc}") from exc


def load_rules(path):
    data = load_file(path)
    if isinstance(data, dict) and "rules" in data:
        data = data["rules"]
    if not isinstance(data, list):
        raise RuleFileError(f"{path}: expected a list of rules")
    return data


def load_facts(path):
    data = load_file(path)
    if isinstance(data, dict) and "facts" in data:
        data = data["facts"]
    if not isinstance(data, dict):
        raise RuleFileError(f"{path}: expected an object of facts")
    return data
