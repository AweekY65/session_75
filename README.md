# Local Rule Engine

一个纯本地的业务规则引擎：规则、facts、执行记录与结果全部来自/写入
本地 JSON/YAML 文件或内存，不依赖 Drools、数据库、消息系统或任何外部服务。

## 规则格式

规则文件为 JSON 或 YAML，顶层是规则列表（或 `{"rules": [...]}`）：

```yaml
rules:
  - id: senior-discount        # 必填，全局唯一
    priority: 20               # 可选，数值，越大越先执行，默认 0
    repeat: false              # 可选，默认 false（规则最多触发一次）
    conditions:                # 必填，条件树
      all:
        - field: age
          op: ge
          value: 65
        - not:
            field: banned
            op: eq
            value: true
    actions:                   # 必填，非空列表
      - set: {field: discount, value: 0.3}
```

### 条件

叶子条件为 `{field, op, value}`，支持的操作符：

| 类别 | 操作符 |
| --- | --- |
| 通用比较 | `eq`, `ne` |
| 数值比较 | `gt`, `ge`, `lt`, `le`（value 必须是数字） |
| 字符串比较 | `starts_with`, `ends_with`, `matches`（正则） |
| 集合包含 | `contains`, `not_contains`（fact 是列表/字符串），`in`, `not_in`（value 是列表） |

布尔组合：`all`（与）、`any`（或）为非空列表，`not` 为单个条件节点，可任意嵌套。
引用的 fact 缺失时条件按不匹配处理，并记录在 trace 中。

### 动作

- `set: {field, value}` — 设置 fact
- `add: {field, value}` — 数值累加（value 必须是数字）
- `append: {field, value}` — 追加到列表 fact（不存在则创建）
- `remove: {field}` — 删除 fact

## 执行模型

1. 每个执行周期对**所有**规则求值，得到匹配集合。
2. 冲突消解：按 `(-priority, 定义顺序)` 排序，优先级高者先执行；
   优先级相同按规则在文件中的定义顺序（稳定 tie-break），保证确定性。
3. 选中规则的 actions 修改 facts；新事实可能在下一周期触发后续规则（链式触发）。
4. 没有可执行规则时正常结束（`status: completed`）。

## 循环保护

- 默认 `repeat: false`：同一规则最多触发一次（no-loop）。
- `repeat: true` 的规则可重复触发，但某次执行没有实际改变任何 fact
  时会被退休（retire），不再参与后续匹配。
- 全局 `max_steps`（默认 1000）限制最大触发次数。耗尽时执行停止，
  返回 `status: max_steps_exceeded`，并在 `cycle_candidates` 中报告
  疑似构成循环的规则（触发次数大于 1 的规则）。

## 静态校验

执行前自动校验（也可 `python -m rule_engine rules.yaml --validate-only` 单独运行），
检测：缺失必填字段（`id`/`conditions`/`actions`）、非法操作符、重复规则 ID、
数值/列表/字符串类型不匹配的操作数、无法编译的正则表达式、空的布尔组合、
未知 action 等。所有问题一次性汇总抛出 `RuleValidationError`。

## Execution Trace

`ExecutionResult.trace` 按顺序记录事件：

- `rule_checked`：每条规则每个周期的求值结果与失败原因（如缺失 fact）
- `rule_fired`：规则触发（含 step 与 priority）
- `fact_modified`：字段修改（`field`/`old`/`new`，含 `created`/`removed` 标记）
- `rule_retired` / `action_error` / `terminated`

CLI 可用 `--trace-out trace.json` 导出。

## 使用

```bash
# 命令行执行
python -m rule_engine examples/rules.yaml examples/facts.json \
    --max-steps 100 --trace-out trace.json --facts-out final_facts.json

# 仅静态校验
python -m rule_engine examples/rules.yaml --validate-only
```

```python
from rule_engine import RuleEngine, load_rules, load_facts

rules = load_rules("examples/rules.yaml")
facts = load_facts("examples/facts.json")
result = RuleEngine(rules, max_steps=100).run(facts)
print(result.status, result.facts, result.fired_rules)
```

## 测试

```bash
python -m pytest tests/ -v
```

覆盖：规则优先级、稳定 tie-break、链式触发、冲突规则的确定性消解、
规则循环与 max_steps 停止、repeat 规则退休、非法配置校验、缺失 fact、
布尔组合与集合操作、action 类型以及执行确定性（多次运行结果一致）。
