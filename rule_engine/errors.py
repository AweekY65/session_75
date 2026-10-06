"""规则引擎的异常类型。"""


class RuleEngineError(Exception):
    """规则引擎基础异常。"""


class RuleValidationError(RuleEngineError):
    """规则静态校验失败。issues 为可读的问题描述列表。"""

    def __init__(self, issues):
        self.issues = list(issues)
        message = "规则校验失败:\n" + "\n".join(f"  - {i}" for i in self.issues)
        super().__init__(message)


class FactLoadError(RuleEngineError):
    """facts 文件加载失败。"""
