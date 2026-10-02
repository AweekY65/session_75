# Local SAT Solver

一个完全本地化的 SAT 求解器：仅使用 Python 标准库，核心 DPLL 算法自行实现，
不调用 Z3、MiniSat、云求解服务或任何外部服务。所有 CNF 输入、求解状态、
模型与测试数据只保存在本地文件或内存中。

## 功能

- 严格的 DIMACS CNF 解析与校验（变量数量、clause 格式、文件结束标记）
- DPLL：unit propagation、pure literal elimination、变量选择启发式
- SAT 时返回完整变量赋值，并可用 `verify()` 重新验证所有 clause
- UNSAT 由算法完备性保证，不依赖超时猜测
- 搜索统计：propagations、pure literals、decisions、backtracks

## 输入格式（DIMACS CNF）

```
c 注释行以 c 开头
p cnf <变量数> <子句数>
1 -2 0
2 3 0
```

- 每个子句以 `0` 结束，可跨行书写。
- 字面量取值范围为 `[-变量数, -1] ∪ [1, 变量数]`，越界即报错。
- 实际子句数必须与头部声明一致，文件不得在子句中间结束。
- 支持传统的 `%` 文件结束标记，其后只允许空白与注释。

### 边界语义（确定性）

| 输入 | 语义 |
| --- | --- |
| 空公式（0 个子句） | SAT，模型中所有变量取默认值 `False` |
| 空子句（`0`） | 恒假，公式 UNSAT |
| 子句内重复字面量 | 加载时去重 |
| 重言式子句（含 `x` 与 `-x`） | 恒真，加载时丢弃 |

## DPLL 流程

1. **Unit propagation**：反复找到只剩一个未赋值字面量的子句并强制赋值，
   直到不动点或冲突；每次赋值计入 `propagations`。
2. **Pure literal elimination**：在未被满足的子句中只以单一极性出现的
   变量直接按该极性赋值，计入 `pure_literals`。
3. **变量选择**：统计每个未赋值变量在未满足子句中的出现次数，选择出现
   次数最多者（平局时取编号最小者，保证确定性），计入 `decisions`。
4. **分支与回溯**：先尝试 `True` 再尝试 `False`；分支失败时恢复决策前的
   赋值快照并计入 `backtracks`。两个分支都失败则返回 UNSAT。

SAT 时，未出现在任何子句中的变量属于 don't-care，模型以 `False` 补全为
完整赋值；`verify(clauses, model)` 可重新检查所有子句均被满足。

## 使用方法

```bash
python3 -m sat_solver path/to/formula.cnf
```

输出 `SAT`/`UNSAT`、模型（`v 1 -2 3 0` 形式）及搜索统计；退出码：
SAT 为 0，UNSAT 为 1，输入非法为 2。

作为库使用：

```python
from sat_solver import parse_dimacs, solve, verify

num_vars, clauses = parse_dimacs(open("formula.cnf").read())
is_sat, model, stats = solve(num_vars, clauses)
assert not is_sat or verify(clauses, model)
```

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：SAT/UNSAT 实例、unit propagation 链、pure literal、深度回溯
（鸽笼原理）、DIMACS 各类错误输入、空公式/空子句/重复字面量/重言式语义，
以及 300 个随机小公式与穷举 oracle 的对拍验证。
