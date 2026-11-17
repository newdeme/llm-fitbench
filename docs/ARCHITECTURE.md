# llm-fitbench 架构与图维护

> 代码基线：`v0.4.2`，提交 `05eb8caaba5b31e8a60b975347be2742e9a2c3b1`。本图描述仓库实现与文档约束，不证明某个本地引擎正在运行，也不提供模型性能排名。

## 1. 图与事实源

- [交互架构图](diagrams/system-overview.html)：下载后用浏览器打开；GitHub 文件页不运行 HTML。
- [结构化图源](diagrams/system-overview.json)：JavaScript Object Notation（JSON），存放节点、关系、源码证据与引导视图。
- [验收摘要](diagrams/verification.json)：记录本次图源和页面的 SHA-256（用于确认文件字节一致的摘要值）及验收状态。

图采用 Archify（从结构化描述生成自包含交互页面的架构可视化工具）。节点的“来源”入口链接到上述固定提交，避免默认分支后续移动导致证据错位。主图合并同类组件，不是逐函数调用图；未绘出的操作入口不代表不存在。

## 2. 架构读法

### 2.1 性能与通用质量路径

用户或 Agent（按操作指引执行任务的智能助手）选择脚本：

- `scripts/bench.py`：Ollama 入口，支持 `baseline`（基线吞吐）、`ladder`（上下文长度阶梯）、`athermal`（随机顺序与冷却的去热对比）、`stress`（窗口探测）、`quality`（内置通用题快筛）。
- `scripts/bench_lms.py`：LM Studio 入口，支持同名子命令；通过 `from bench import BANK, grade, build_prompt, save` 复用通用题库、判分、提示构造和保存函数。

两者分别向本地推理引擎发送请求，并由脚本保存结果。图中没有“引擎直接写结果文件”的边。

计量口径并不完全相同：Ollama 由 `rates()` 读取服务端计数与时长；LM Studio 的 `chat_stream()` 根据流式片段计算首响应延迟与吞吐，并保留服务端用量字段用于分歧审计。流式片段计数不是普适的精确 token（模型文本计量单位）计数；跨引擎比较仍须遵循方法论的交叉验证约束。

### 2.2 独立场景质量路径

`quality_v2.py` 不导入 `bench.py` 或 `bench_lms.py`，独立实现：

1. `load_bank()` 加载外置题库；`build_needle_doc()` 把目标事实插入长文指定位置，构造检索题。
2. `gen_answer()` 适配 Ollama 或 LM Studio。
3. `grade()` 确定性判分；`run()` 对空回答或疑似预算不足情形按实现规则复测，并汇总各场景结果。
4. `wilson_ci()` 计算正确率置信区间；`save()` 写 JSON，`report()` 打印终端对比。

用户也可直接从命令行选择该入口。图将“外置题库 → 场景化质量评测”作为这一路径的阅读起点，并不表示题库自行启动脚本。

公开示例包括遥感科研题库与 GSM8K（Grade School Math 8K，基础数学文字题数据集）分层子集；不传 `--bank` 时只使用中性演示题库。场景权重由题库声明，不由图推导或重设。

### 2.3 方法与结果边界

- `docs/METHODOLOGY.md` 与 `skill/` 是操作约束和指导，不是常驻服务或自动执行器。
- 三个脚本优先把结果写到环境变量 `BENCH_DATA_DIR` 指定的目录；未设置则回落到仓库的 `bench_results/`。
- `.gitignore` 忽略默认结果目录，但忽略规则不等于自动脱敏：自定义私有题库、其他结果文件仍需自行隔离。
- 综合裁决与私有台账维护由人或 Agent 按方法论完成；程序已有 JSON 输出和部分终端汇总，尚无自动生成 `RESULTS.md` 的完整报告系统。
- `tests/test_core.py` 检查判分、题库加载及公共逻辑；`.github/workflows/ci.yml` 的 CI（Continuous Integration，持续集成，即自动编译和测试）不启动推理引擎。它不证明真实引擎请求、硬件适配性或整套偏差控制均已端到端通过。

图不含模型下载器、训练器、统一调度服务、付费接口或云端数据上传节点。更多引擎与自动报告仍属于路线图，不能画成现有能力。

## 3. 节点与源码对应

以下行号对应固定基线提交，不随将来的文件编辑自动更新。图中共有八个合并组件，附二十处源码引用。

| 图节点 | 主要实现或文档证据 | 边界说明 |
|---|---|---|
| 方法论与偏差控制 | `docs/METHODOLOGY.md:17–42` | 方法约束；不是自动中间件；同样适用于场景质量评测 |
| 用户 / Agent 入口 | `skill/SKILL.md:17–44`；`README.md:29–47` | 操作入口；三个脚本分别启动 |
| 性能与通用质量评测 | `scripts/bench.py:88–264`；`scripts/bench_lms.py:14–18` | 合并展示两个入口；复用关系仅指已导入的公共函数 |
| 本地推理引擎 | `scripts/bench.py:55–73`；`scripts/bench_lms.py:18–71`；`scripts/quality_v2.py:71–101` | Ollama 默认端口 11434；LM Studio 默认端口 1234；引擎在仓外运行 |
| 外置场景题库 | `examples/question-bank-template.md:1`；两个示例 `bank.json:1` | 文件输入，不是数据库服务；私有题库不应入公开仓 |
| 场景化质量评测 | `scripts/quality_v2.py:36–69,103–182` | 题库加载、独立请求适配、判分与汇总 |
| 本地结果文件 | `scripts/bench.py:11–15,79–82`；`scripts/quality_v2.py:168–182` | 文件存档，不是结果数据库；建议仓外保存 |
| 人工 / Agent 综合裁决 | `docs/METHODOLOGY.md:82–103`；`docs/EVAL-LOG.md:1–16` | 人工流程，不是已实现的自动报告服务 |

三种引导视图分别聚焦“性能与窗口”“场景化质量”“方法与数据边界”。为保持可读性，图没有穷举全部指导关系；完整对应以本节和代码为准。下方质量保障卡不另建一个虚构的运行服务。

## 4. 借鉴的项目管理方法

复用 david-sync 的维护原则，而不复制其设备拓扑或整个目录体系：

1. **项目事实留项目仓**：图源、生成页面、架构说明同仓维护；外部组合索引只需链接项目入口，不复制图的事实。
2. **图源与页面配对**：JSON 为可维护正本，HTML 为生成物；不直接修改生成页面修补布局。
3. **证据先于连线**：节点绑定源码路径和行号；请求、文件写入、指导和人工审阅分别表达，不把人工流程画成自动系统。
4. **变更同步更新**：新增入口、引擎、题库协议、结果路径或关键依赖时，在同一变更中更新图、对应说明和 README 入口。
5. **公开与私有隔离**：公开仓只放通用工具、方法、示例和合成说明；个人评测原始数据、机器路径、凭据、跨项目规划不进入图或验收摘要。

本项目已有 `docs/` 文档区，因此图落在 `docs/diagrams/`，而非机械新增 `notes/system/`。本轮不移动任何私有目录，也不改外部组合台账。

## 5. 复现与维护

Archify 是文档作者工具，不是 llm-fitbench 的运行依赖。需另备该技能包和 Node.js（执行其命令行工具的 JavaScript 运行时）；无需向本项目安装依赖。下列命令从项目根目录运行，将 `ARCHIFY_HOME` 设置成你自己的技能包目录：

```bash
export ARCHIFY_HOME=/path/to/archify
node "$ARCHIFY_HOME/bin/archify.mjs" validate architecture \
  docs/diagrams/system-overview.json --quality showcase --repo-root "$PWD" --json
node "$ARCHIFY_HOME/bin/archify.mjs" deliver architecture \
  docs/diagrams/system-overview.json docs/diagrams/system-overview.html \
  --quality showcase --repo-root "$PWD" --json
node "$ARCHIFY_HOME/bin/archify.mjs" visual-check \
  docs/diagrams/system-overview.html --json
```

`--repo-root` 不可省略：图声明了源码证据，工具需要本地 Git 仓库核对固定提交与文件。更新基线时先核本地、远端和工作区，再更新 `meta.repository.revision`、各 `sources` 的路径与行号及本说明。

维护顺序：备份旧图源 → 修改 JSON → 校验 → 生成页面 → 浏览器检查 → 实际截图审阅 → 更新验收摘要。校验失败时不能把旧页面当作新候选验收；修改图源后必须重新生成、重新检查。

showcase 是 Archify 的展示级结构检查；浏览器检查与视觉审阅是另外两道验收，任何一道通过都不能替代其余两道。浏览器检查采用工具规定的 1440×900、1600×1000、1920×1080、2048×1320 四种尺寸，并捕获明暗主题。尺寸来自工具交付规约，不是评测参数。

`visual-check` 会在页面旁产生 `*.visual-check.*` 临时证据文件，其中回执包含作者机器的绝对路径；只作本地复核，不直接提交公开仓。仓内 `verification.json` 保留去本机路径的摘要；再次生成页面后须重新取得回执，不沿用旧哈希。

## 6. 本次制作与取舍

代码和远端先核对到同一提交，再读取三个脚本、方法论、题库模板、测试与工作流。首版消除了请求线与保存线的共用走廊；实际截图随后发现笔记本尺寸小字偏小，因此压缩空白并重新检查。紧凑版一度出现纵向溢出，按浏览器实测修正为宽图布局并精简重复卡片，没有隐藏溢出或缩小文字。

为降低界面冗余，首版“真实代码边界”卡片的内容移入本说明，最终下方只保留质量保障与隐私边界短卡；脚本列表与非自动调度边界没有删除。图未穷举指导边，也未复制简版/完整版两份相同结构。

| 我方盲区 | 可复用经验 |
|---|---|
| 自动结构检查通过，仍可能字号偏小；不能直接宣布视觉通过 | 对实际明暗截图独立审阅，以真实视口检查校准排版 |
| 仅缩窄画布会改变宽高比并影响查看器的高度适配 | 保持工具支持的宽图布局，先压缩空白、精简重复说明，不改生成器、不伪造无溢出 |

本次只验证文档图及源码证据，不运行模型评测，不把既有单元测试说明冒充本次测试执行结果。
