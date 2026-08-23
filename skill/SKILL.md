---
name: local-model-bench
description: 本地开源模型与 Apple Silicon Mac 适配性的实证评测与选型工作流（Ollama / LM Studio / MLX / GGUF）。当用户部署、下载了新的本地模型并想测试其快慢好坏，对比本地模型选型，判断某模型能否在自己的电脑上跑，或排查本地推理慢、加载失败、长上下文截断等问题时使用。触发词：测一下这个模型、评测XX模型、本地模型对比、XX能跑吗、为什么本地模型这么慢、tok/s、TTFT、benchmark 本地模型、给电脑配本地模型。
---

# 本地模型评测

## 核心原则（违反即数据作废）

1. **实测优先**：一切结论来自本机命令输出；不引用网上 benchmark 数字代替实测。
2. **先 ETA 再长跑**：预计 >3 分钟的命令，开跑前基于已实测锚点外推并告知用户预估时长；>10 分钟拆步执行或先征询。
3. **单一数据源**：结果只追加到 `$LAB/RESULTS.md`（私有台账，永不进 git），不改写历史批次。
4. **如实登记**：失败、中止、未测项写进 RESULTS.md §4，不隐藏。
5. **计量纪律（B7 实证）**：吞吐/token 数以 SSE 自计为准，服务端 `usage` 字段仅作审计（分歧 >15% 工具自动标记）；任何间接推断（chunk→token 比例、速率外推）必须经 tiktoken 真值交叉验证才可入档；引用 TTFT 须注明口径（不可见 reasoning 模型的实测 TTFT=首可见 content，含隐藏推理时长）。
6. **三重防污染（B6/B7 实证）**：吞吐测试①测前卸双侧引擎驻留（Ollama `keep_alive:0` + `lms unload --all`）；②每测试块前后 `lms ps` + `/api/ps` 快照比对；③多模型对比同批交错而非顺序执行——残留驻留可压低吞吐 7–27%（ornith 69GB 残留压低 qwen3.6 7%；B5 累积驻留压低三模型 14–27%）。

## 三位置布局（canonical，勿建副本）

- **工具+方法论+本 skill 正本（开源仓库，private 勿转 Public）**：`$FITBENCH/`（github.com/newdeme/llm-fitbench）
  - `scripts/` — bench.py（Ollama）/ bench_lms.py（LM Studio, OpenAI 兼容）五子命令；quality_v2.py（72 题场景化，`--no-think` 支持）
  - `skill/` — **本 skill 唯一正本**；`~/.agents/skills/local-model-bench` 为指向此目录的 symlink，改动只改仓库版
  - `docs/METHODOLOGY.md` — 完整方法论（七偏差控制、七定律、失败甄别）。**做全量评测前先读它**
- **私有数据层（本机台账，永不进 git）**：`$LAB/`
  - `AGENTS.md`（工作空间协议+快速命令）、`LOCAL_NOTES.md`（本机基线+锚点+本机坑）、`RESULTS.md`（结果总档，**出报告前先读**）、`bench_results/`
- 跑评测必设：`export BENCH_DATA_DIR=$LAB/bench_results`

## 新模型 30 分钟初筛流程

1. **P0 元数据**：确认模型真实身份（量化/架构/声明窗口）。
   - Ollama: `curl -s localhost:11434/api/show -d '{"model":"NAME"}'`
   - LM Studio: `curl -s localhost:1234/api/v0/models`（看 state/quantization/loaded_context_length）
2. **环境清理**：卸载双侧引擎驻留模型（128GB 只容一主一辅）：
   `curl -s localhost:11434/api/generate -d '{"model":"NAME","keep_alive":0}'`（`/api/stop` 在 Ollama 0.32.x 返回 404）或 `lms unload --all`
3. **P1 基线**（~5 min）：`python3 bench.py|bench_lms.py baseline -m 模型 --runs 3`
   门槛：decode <15 tok/s → 交互不可用，可直接判"不推荐"并停止。
4. **P2 阶梯**（~10 min）：`... ladder -m 模型 --ctxs 2048 8192 32768`
   看 TTFT 在用户真实工作长度是否可接受（>5 min 即长文不可用）。
5. **P5 质量筛查**（~10 min）：`... quality -m 模型 --limit 12`（24 题通用快筛）。
   转正候选或需深度对比时 → 场景化 v2（72 题六场景，出题原则与操作见 **references/quality-v2.md**，出题前必读 METHODOLOGY.md §5 七定律）。
6. **对比裁决**：读 RESULTS.md，新数据与 §1 场景选型表对比，更新推荐或淘汰。

初筛有亮点（更快/窗口更长/质量更好）→ 补全量：P3 去热排名（`athermal`，多模型打乱×3组，两引擎均支持）、P4 极限窗口（`stress --ctxs 65536 131072`，先报 ETA；LMS 须先 `lms load --context-length N` 显式加载，JIT 默认 8K 窗超载会静默空流）。

## 常见失败 → 甄别（详见 references/troubleshooting.md）

| 现象 | 判定 | 速查 |
|---|---|---|
| HTTP 400 Bad Request | 超窗拒绝（≠OOM） | §失败甄别表 |
| prompt_eval_count / actual 不随输入增长 | 静默截断（声明窗口不可信） | 双探针法 |
| **秒回空流**（<10s，无 prefill） | 真超窗拒绝（LMS 超 loaded_context_length 静默空流） | wall 时间判别 |
| **慢空流**（prefill 全时长后无输出） | ①预算饥饿：harmony/thinking 模型 reasoning 计入 max_tokens 且不可见，小预算（≤96）content 永不启动，≥4096 全通；②裸填充文本×对话格式退化：仅生成不可见通道 | 加大预算 / 追加指令分别复测鉴别 |
| usage 与 SSE 自计分歧 >15% | 计量口径坑（LMS gpt-oss 类 completion 虚增 ~2×：幻影 reasoning 不流出却计费） | 以 SSE 自计为准，工具已自动标记 |
| prefill 速率出现天文数字 | prompt 缓存命中，该值作废 | §坑清单 |
| 加载报 draft model 错误 | LM Studio 投机解码挑中损坏草稿 | references/lms-notes.md |
| 超窗行为（两引擎均静默无 HTTP 错） | **Ollama：丢头保尾（num_ctx/2）+ 编造丢失内容（危险）；LMS：秒回空流（可检测）**——上层应用必须自防 | §超窗行为对比 |

## 报告规范

- 结论先行 + 表格；每项数据标注实测批次/条件；跨引擎对比须声明含后端差异（含 tokenizer/量化差异）。
- 报告落盘 RESULTS.md（按 §5 追加协议），关键决策同步 nmem 记忆。
