"""纯本地业务规则引擎：规则、facts、执行记录与结果仅使用本地 JSON/YAML 或内存。"""

from .engine import ExecutionResult, Rule, run_engine
from .errors import FactLoadError, RuleEngineError, RuleValidationError
from .loader import load_facts, load_rules
from .validation import validate_rules

__all__ = [
    "ExecutionResult",
    "FactLoadError",
    "Rule",
    "RuleEngineError",
    "RuleValidationError",
    "load_facts",
    "load_rules",
    "run_engine",
    "validate_rules",
]

__version__ = "0.1.0"
