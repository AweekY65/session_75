# 本地业务规则引擎

纯本地实现：规则、facts、执行记录与结果全部来自/写入本地 JSON/YAML 文件或内存，
不依赖 Drools 服务、数据库、消息系统或任何外部服务。仅使用 Python 标准库 + PyYAML。

## 规则格式

规则文件为 JSON 或 YAML，顶层是规则列表（或 `{"rules": [...]}`）：

```yaml
rules:
  - id: senior-discount        # 必填，全局唯一
    priority: 20               # 可选，数值，越大越先执行，默认 0
    repeat: false              # 可选，默认 false（同一规则最多触发一次）
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
| 通用比较 | `eq`、`ne` |
| 数值比较 | `gt`、`ge`、`lt`、`le`（value 必须是数字） |
| 字符串比较 | `starts_with`、`ends_with`、`matches`（正则） |
| 集合包含 | `contains`、`not_contains`（fact 为列表/字符串）；`in`、`not_in`（value 为列表） |

布尔组合：`all`（与）、`any`（或）为非空列表，`not` 为单个条件节点，可任意嵌套。
引用的 fact 缺失或类型不匹配时，该条件按不匹配处理，原因记录在 trace 的 `check` 事件中。

### 动作

- `set: {field, value}` — 设置 fact
- `add: {field, value}` — 数值累加（value 必须是数字，目标 fact 缺失时从 0 开始）
- `append: {field, value}` — 追加到列表 fact（不存在则创建）
- `remove: {field}` — 删除 fact

## 执行模型

1. 每个执行步对**所有**规则求值，trace 记录每条规则的 `check` 结果。
2. 冲突消解：按 `(-priority, 定义顺序)` 排序，优先级高者先执行；
   优先级相同按规则在文件中的定义顺序（稳定 tie-break），保证完全确定性。
3. 每步触发排序最前的一条可执行规则，其 actions 修改 facts（trace 记录
   `change` 事件：字段、旧值、新值）；新事实可在后续步触发其他规则（链式触发）。
4. 没有可执行规则时正常结束，结果 `status: completed`。

## 循环保护

- 默认 `repeat: false`：同一规则最多触发一次（no-loop），不会无限自触发。
- `repeat: true` 的规则可重复触发；若某次触发未改变任何 fact，该规则被隔离
  （trace 记录 `quiesce` 事件），避免原地空转。
- 全局 `--max-steps`（默认 1000）兜底：达到上限时停止，`status: max_steps_reached`，
  并在结果的 `cycle` 字段与 trace 的 `halt` 事件中报告疑似循环的规则序列。

## 静态校验

加载规则时自动校验，发现问题抛出 `RuleValidationError`（含全部问题列表）：

- 缺失必填字段（`id`、`conditions`、`actions`，叶子条件的 `field/op/value`）
- 非法操作符、非法 action 类型
- 重复规则 ID
- 明显不可解析的表达式（如非法正则）、类型不匹配（数值操作符配非数值等）

## 执行结果与 trace

`run_engine` 返回 `ExecutionResult`：`status`、`steps`、最终 `facts`、
`fired_rules`（触发序列）、`cycle`（疑似循环）和完整 `trace`
（`check` / `fire` / `change` / `quiesce` / `halt` 事件流）。

## 使用

```bash
# 命令行执行（结果 JSON 打印到 stdout，可用 -o 写入本地文件）
python -m rule_engine examples/rules.yaml examples/facts.json --max-steps 100 -o result.json
```

```python
from rule_engine import load_rules, load_facts, run_engine

result = run_engine(load_rules("rules.yaml"), load_facts("facts.json"))
print(result.status, result.facts)
```

## 测试

```bash
python -m pytest -q
```

覆盖：规则优先级与稳定 tie-break、链式触发、冲突规则、规则循环（no-loop /
quiesce / max-steps）、非法配置（缺失字段、非法操作符、重复 ID、非法正则）、
缺失 fact、确定性执行等场景。
