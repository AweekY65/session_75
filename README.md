# sat-solver

一个完全本地运行的 SAT 求解器，核心 DPLL 算法使用 Python 标准库从零实现。
不依赖 Z3、MiniSat 或任何云求解服务；所有 CNF 输入、求解状态、模型与测试
数据仅保存在本地文件或内存中。

## 文件结构

- `sat_solver.py` — DIMACS 解析器、DPLL 求解器、统计与命令行入口
- `tests/test_sat_solver.py` — 自动化测试（含穷举 oracle 对照）

## 输入格式（DIMACS CNF）

```
c 注释行以 c 开头
p cnf <变量数> <子句数>
1 -2 0
2 3 0
%
```

解析器严格校验：

- 必须有且仅有一行 `p cnf <vars> <clauses>` 头部，且出现在任何子句之前；
- 每个 literal 为整数，绝对值不得超过声明的变量数；
- 每个子句必须以 `0` 结尾（子句可跨行书写）；
- 实际子句数必须与头部声明一致；
- 可选的文件结束标记 `%` 之后只允许出现空行，否则报错。

确定语义：

- 空公式（0 个子句）恒为 SAT，返回全 `False` 的完整赋值；
- 空子句使公式恒为 UNSAT，无需搜索直接返回；
- 子句内重复 literal 在解析时去重；
- 恒真子句（同时含 `x` 与 `-x`）在解析时丢弃。

## DPLL 流程

`solve()` 对每个子句集合递归执行：

1. **Unit propagation**：扫描长度为 1 的子句，将其 literal 赋真并化简
   公式；化简产生空子句即判定冲突，返回上一层。重复直至不动点。
2. **Pure literal elimination**：统计每个变量出现的极性，只以单一极性
   出现的变量直接按该极性赋值并化简。重复直至不动点。
3. **变量选择（DLIS 风格启发式）**：选择在剩余子句中出现次数最多的
   未赋值变量，并列时取编号最小者保证确定性；优先尝试其出现次数较多
   的极性。
4. **决策与回溯**：对所选变量递归尝试两个分支；分支冲突则回溯尝试
   另一值，两个分支均失败则向上一层返回 UNSAT。

UNSAT 结论只在整个搜索树被完整探索后得出，不使用超时猜测。

## 输出与统计

命令行：

```
$ python3 -m sat_solver examples/sat.cnf
c stats: decisions=3 propagations=8 backtracks=1
s SATISFIABLE
v 1 -2 3 0
```

- 退出码：`0` = SAT，`1` = UNSAT，`2` = 解析错误；
- `decisions` / `propagations` / `backtracks` 分别统计决策次数、
  传播（unit + pure）次数与回溯次数；
- SAT 时输出覆盖全部 `1..n` 变量的完整模型，未受约束的变量默认
  赋 `False`（模型明确可扩展）；`verify_model()` 可对原始子句重新
  验证模型。

## 运行测试

所有测试直接在终端执行：

```
python3 -m unittest discover -s tests -v
```

测试覆盖：SAT/UNSAT 实例、unit propagation 链、pure literal 消除、
深度回溯（3 鸽 2 笼鸽巢原理）、DIMACS 各类解析错误、空公式/空子句/
重复 literal/恒真子句语义，以及 300 个随机小公式与穷举 oracle 的
对照验证。
