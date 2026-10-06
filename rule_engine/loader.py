"""从本地 JSON/YAML 文件加载规则与 facts，不依赖任何外部服务。"""

import json
import os

import yaml

from .errors import FactLoadError, RuleEngineError
from .validation import validate_rules


def _load_document(path):
    if not os.path.isfile(path):
        raise RuleEngineError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".json":
            return json.loads(text)
        if ext in (".yaml", ".yml"):
            return yaml.safe_load(text)
        # 未知后缀：先 JSON 后 YAML 尝试
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise RuleEngineError(f"无法解析文件 {path}: {exc}") from exc


def load_rules(path):
    """加载并静态校验规则文件，返回规则字典列表。"""
    data = _load_document(path)
    return validate_rules(data)


def load_facts(path):
    """加载 facts 文件（JSON/YAML 对象），返回 dict。"""
    data = _load_document(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise FactLoadError(f"facts 文件必须是对象，得到 {type(data).__name__}: {path}")
    return data
