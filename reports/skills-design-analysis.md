# `skills/` 目录深度分析 — virtuoso-bridge-lite 的 Agent Skill 设计

范围: `skills/{virtuoso,spectre,netlist,optimizer}`，共 20 个文件、约 3963 行 Markdown + 1 个 Python checker 脚本。

---

## 1. 整体结构：标准 Claude Skill 布局 + 领域特化的三层分层

```
skills/
├── virtuoso/       SKILL.md (654行) + references/ (12个文件) + 隐式依赖 examples/01_virtuoso/
├── spectre/        SKILL.md (257行) + references/ (2个文件) + 隐式依赖 examples/02_spectre/
├── netlist/        SKILL.md (57行)  + references/cleaning.md + scripts/check_spectre_netlist.py
└── optimizer/      SKILL.md (139行) — 无 references/，纯范式说明
```

每个 `SKILL.md` 头部都是标准 YAML front-matter，只有 `name` + `description` 两个字段，没有滥用 `allowed-tools` 之类的机制——`description` 字段本身承担"触发器"职责，写法很讲究：

```yaml
description: "... TRIGGER when the user wants to optimize, tune, size, sweep... 
Do NOT trigger for single-variable parametric sweeps or analytical calculations."
```

四个 skill 里三个（spectre/optimizer/netlist）显式写了 `TRIGGER when...` 和 `Do NOT trigger when...`，说明作者非常清楚 Claude/Codex 类 agent 是靠 description 语义匹配来决定是否加载 skill 的，并主动做了**正例 + 反例**的边界声明，减少误触发（比如 optimizer 明确排除"单变量扫描"和"有解析解"的场景，避免小题大做地调用黑盒优化器）。

四个 skill 之间还建立了一个**"Related skills"引用图**（每个 SKILL.md 结尾都有），形成互相路由：
- `virtuoso` → 指向 `spectre`（"有 .scs 网表直接跑用 spectre"）
- `spectre` → 指向 `virtuoso`（"GUI 里的 Maestro 流程用 virtuoso"）
- `optimizer` → 同时指向 `spectre` 和 `virtuoso`（作为它的两种评估后端）
- `netlist` 独立，服务于前两者产出的网表清理

这本质上是把多个 skill 组织成一个**有向路由图**，而不是孤立的功能点清单。

---

## 2. 核心设计原则：反幻觉（anti-hallucination）优先

`virtuoso/SKILL.md` 开篇第一句话不是功能介绍，而是一条硬性禁令：

> **CRITICAL: Do NOT invent SKILL code or API calls from memory.**
> 1. Search `references/` for the function name
> 2. Check `examples/` for a working example
> 3. Read the actual function signature
>
> If the function is not documented in references or examples, it probably does not exist — never guess parameter names.

这是全篇反复强调的主题（"Never guess function names"、"fabricating a wrong name wastes time debugging in CIW"）。原因很实际：SKILL 语言是 Cadence 私有的、LLM 预训练语料里几乎没有覆盖，模型极易编造出"看起来合理"但实际不存在的函数名或参数名，而错误只有在真实连接到 Virtuoso 之后才会暴露（round-trip 慢、报错信息晦涩）。所以整个 skill 设计的第一优先级是**收窄模型的自由发挥空间**，逼它去查文档而不是编。

配套的还有"三级抽象"表格，明确规定优先级（Python API > inline SKILL > SKILL 文件），要求"始终使用能满足需求的最高层级"，进一步限制不必要的裸 SKILL 编写。

---

## 3. 面向 Agent 的性能工程：把"人类最佳实践"编码进文档

最值得注意的是 `fetch()` / `fetch_one()` 那一节。这不是简单的 API 说明，而是显式给出了**性能推理**：

> `execute_skill()` 对 DFII 对象只返回一个不透明句柄，要拿属性得再发一次 SKILL 调用——每次往返 ~100ms。`fetch(expr, fields)` 把 `mapcar(lambda((o) list(o~>f1 o~>f2...)) expr)` 一次性发出去解析回来。
>
> **为什么不做 skillbridge 那样的懒代理风格？** 懒代理语法更好看，但每次属性访问触发一次往返——100 个对象 × 3 个字段 = 300 次 SSH 跳转（~30秒）。`fetch` 一次搞定（~200ms）。

这段文字直接对标了同类项目 skillbridge 的设计取舍，并给出量化对比（30s vs 200ms），本质上是在教 agent"不要写出 N+1 查询式的 SKILL 代码"——这是专门针对 LLM Agent 高频调用场景写的性能指南，普通人类工程师文档不会强调到这个粒度。

同样的量化风格贯穿 `spectre/SKILL.md`：仿真模式选择给出了以 ENOB（有效位数）损失和加速比为维度的实测表格：

| 模式 | 速度 | ENOB Δ | 用途 |
|---|---|---|---|
| `ax` | 2.0× | -0.03 (噪声内) | 日常默认 |
| `lx` | 5.9× | -2.8 (SAR 不可用) | 仅限小信号 AC |
| `vx` | 8.8× | -8.5 (完全失效) | 仅限连通性检查 |

以及 Verilog-A 替换收益的非单调性分析（"替换大 cell 有收益，替换小 cell 反而更慢，因为 `transition()` 事件队列开销 vs BSIM 方程节省不是线性关系"）——这些都标注了具体测量条件（"11-bit SAR ADC, N=64/128, ax baseline ≈ 220s"），不是泛泛而谈，而是可复现、可追溯的工程知识沉淀。

---

## 4. 故障手册化：把踩过的坑做成可搜索的"症状→原因→修复"数据库

`references/troubleshooting.md`（205 行）和 spectre skill 里的 "Gotchas" 一节，统一采用固定格式：

```
### <症状/函数名标题>
<根因解释>
**Fix / Workaround:** <具体代码>
```

例如 "ASSEMBLER-8127: cellview already open in edit mode" 这一条，不仅给出 SKILL 层面的规避方法，还给出了当 SKILL 通道本身被模态框卡死、连 `hiFormDone` 都打不进去时的终极手段——直接用 Python2.7 + ctypes 调 X11 的 `XTestFakeKeyEvent` 发送按键。这是三层递进式的故障恢复（SKILL API → 更底层 SKILL → 绕过 SKILL 走 X11），文档把这套"升级路径"完整保留了下来。

AGENTS.md 里提到的那个经典案例（`strmin` 崩溃却让轮询器空等满 10 分钟）本质上和这里是同一种文档哲学：**把生产环境中真实发生过、日期可查（"2026-05-14 observed"）的故障案例转成规则**，而不是假设性的最佳实践。

---

## 5. 渐进式加载（Progressive Disclosure）设计

`virtuoso/SKILL.md` 结尾的 References 表格明确写了"Load on demand"，把 12 个 reference 文件的职责边界列得很细（schematic SKILL API vs Python API 分开、layout 同理、maestro 同理），目的是控制单次加载的上下文体积——SKILL.md 本身 654 行已经不小，如果把所有 reference 内容都塞进主文件会严重膨胀 agent 的上下文窗口。这是标准的 Skill 分层模式（entry point 精简 + 按需查阅的 reference），但这里做得比较彻底：几乎每个子领域（schematic/layout/maestro/netlist/skill-finder）都拆成独立的 python-api + skill-api 两份文档，对应"三级抽象"中的两条路径。

`examples/` 目录（不在 skills/ 内，但被所有 SKILL.md 大量引用）承担了"可运行的最终真相源"角色——SKILL.md 反复强调"Always check examples first"、"don't reinvent from scratch"，把 40+ 个带编号的示例脚本当作事实上的集成测试 + 用法范例双重角色。

---

## 6. `netlist` skill：一个反直觉但很清醒的设计——"脚本是检查器,不是引擎"

这是四个 skill 里最短（57 行）但设计理念最明确的一个。它开篇就划清了边界：

> The primary cleanup engine is semantic understanding by the model and engineer. **Do not treat netlist cleanup as a blind text rewrite.** A checker can report leftover tool artifacts, but it cannot decide circuit boundaries, node meaning, or instance names.

也就是说，作者刻意没有把"清理网表"做成一个确定性脚本工具去自动化，而是要求 agent 先做语义理解（画出 DUT/testbench/run-deck 边界、判断节点含义、给随机命名的节点想语义化名字），**之后**才允许跑 `check_spectre_netlist.py` 做兜底检查（读了脚本源码，它只做正则匹配式的"MOS 尾巴参数残留""随机节点名""DUT/TB 混杂"检测，`--mode dut/tb` 切换规则集，不做任何自动重写）。这是对"LLM 该做什么、脚本该做什么"边界的一次清晰表态：脚本擅长穷举式模式检测,LLM 擅长语义判断,不要用脚本去替代需要理解电路拓扑的决策。

---

## 7. `optimizer` skill：唯一没有 `references/` 的 skill——因为不需要

Optimizer skill 只有 139 行 SKILL.md，没有独立 reference 文件，原因是它设计成一个**领域无关的黑盒优化外壳**：参数、评估函数、目标函数三个抽象概念，`evaluate()` 函数是唯一随场景变化的部分，文档给了三种可插拔后端范例（Spectre 网表模板替换 / Maestro SKILL 调用 / 任意 Python 可调用对象）。文档中段还专门讨论了何时改用外部工具 `IC-opt-workflow`（当任务规模超出单一黑盒函数、需要多测试台/多角聚合、需要可复现产物时），把自己的定位限定得很清楚："保留 virtuoso-bridge-lite 作为 Cadence 访问层，把外部工作流当作可插拔后端调用，而不是把它 vendored 进来"——体现了克制的模块化边界意识,不做大而全的框架。

目标函数设计部分也有一条容易被忽略但很关键的工程提示：**必须返回 `1e6` 惩罚值而非 `nan`/`inf`**，因为 TuRBO 底层用高斯过程（GP）代理模型，`nan`/`inf` 会直接破坏 GP 拟合导致优化发散——这是深入到优化算法内部机制的提示，而非表面的 API 说明。

---

## 8. 综合评价

**做得好的地方：**
1. **触发边界清晰**：description 里的 TRIGGER/DO NOT TRIGGER 显式声明，减少 skill 误召回或漏召回。
2. **反幻觉设计贯穿全篇**：从"禁止编造 SKILL 函数名"到"scripts 是检查器不是引擎"，反复强调 LLM 的能力边界——该发挥语义理解的地方发挥，该查文档验证的地方必须查证。
3. **量化胜过泛泛而谈**：几乎每一条"最佳实践"都配了测量数据（时延、ENOB 损失、加速比、故障复现日期），而不是空洞的建议。
4. **故障手册结构化**：症状 → 根因 → 修复的固定模板，方便 agent 用关键词搜索定位，而不是要求 agent 从头推理。
5. **skill 间路由图**：四个 skill 通过 "Related skills" 互相指路，形成一个可组合的技能网络而非孤岛。

**可能的局限：**
1. **文档规模已经不小**（virtuoso 一个 skill 主文件 654 行 + 12 个 reference），随着功能增长，"进量控制"会越来越难，未来可能需要再拆分或做更激进的索引化（比如 skill-finder 那种按需检索机制，目前只对 SKILL 函数做了，对 references 本身没有做搜索索引）。
2. **强假设 Cadence 环境和特定实验室配置**（IC618、Spectre 21.1、特定 lab cluster 的性能数字），这些经验值随 Cadence 版本/PDK/硬件环境变化可能失效，是"当前快照"而非"永久真理"，需要持续验证与更新（文档本身没有标注失效检测机制）。
3. **netlist skill 的 checker 脚本用正则式模式匹配**，对复杂层级网表（多级 subckt 嵌套）的边界判断能力有限，仍然高度依赖模型自身的语义理解，脚本更像是"linter"角色。
