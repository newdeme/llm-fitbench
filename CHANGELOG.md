# Changelog

本项目的所有显著变更都记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.4.0] - 2026-08-23

### Added

- **遥感题库 F 场景 4→8 题 + needle 位置维度**：新增可选 `pos` 字段（0–1 相对位置，默认 0.5 正中）；F5–F8 分布 0.15/0.3/0.7/0.85。题库更名 `remote-sensing-researcher-72` → **`-76`**（F 扩容后新旧 F 成绩不可直比；A–E/G 未动可延续）。
- **GSM8K 分层数学题库** `examples/gsm8k-math/`（12 题：易≤2步/中3–4步/难≥5步各 4 题；源 openai/gsm8k test 前 300 行節选，MIT；选法可复现见其 README）。
- 单测新增 needle 位置渲染断言（共 13 项）。

### Fixed

- **F 场景 needle 渲染缺陷（B8 发现）**：旧版把判分关键词裸插文档（而非完整事实句），且 `n_repeat=6` 时插入点恰落在重复接缝（无空格粘连）——旧 F 成绩可能含领域先验成分。修复：needle 按题库模板契约插入完整事实句（`text` 字段），并吸附到最近句边界；`remote-sensing-researcher` 题库 needles 字段语义归正（text=事实句， answer=关键词）。

## [0.3.0] - 2026-08-23

### Added

- **`skill/` 目录：Agent Skill 正本**（SKILL.md + references 三篇）。本地 `~/.agents/skills/local-model-bench` 改为指向此目录的 symlink，skill 与工具/方法论同仓库同版本演进，消除双位置失同步漂移。内容同步至 B7：空流三病因甄别、计量三坑（usage 虚增/tokenizer 少计/间接推断假设错）、三重防污染纪律、超窗行为对比。
- `bench_lms.py stress --instruction`：追加到填充文本尾部的指令（防裸文本×对话格式模型空流假象，B7 实证；传空串可禁用）。

### Changed

- **`bench_lms.py stress` 默认生成预算 64 → 4096**：harmony/thinking 模型 reasoning 计入 max_tokens 且不可见，小预算会产生空流假象（B7 实证 32/64/96 全灭、4096 全通），旧默认会误判窗口为不可用。
- **METHODOLOGY v1.3**：六大 → 八大偏差控制（新增驻留污染、计量口径偏差）；失败甄别表升级空流三病因；超窗行为对比（Ollama 丢头+编造 vs LMS 秒空流）；统一内存纪律补 JIT 两坑/幽灵加载/`/api/stop` 404；坑清单 12 → 19 条。

### Fixed

- `bench_lms.py` 模块 docstring 计量口径描述过时（仍称"采信 usage 字段"，实际已 SSE 自计 + usage 审计）。

## [0.2.0] - 2026-08-22

### Changed

- **题库外置重构（不兼容变更）**：`quality_v2.py` 不再内嵌私人题库——真实题库全部为独立 JSON 文件（`--bank` 指定），脚本只内置 6 题中性演示题库（仅验证链路）。遥感科研 72 题移至 `examples/remote-sensing-researcher/bank.json`。
- 新增 `--limit N`（只跑前 N 题，冒烟用）。
- 结果文件名含题库名，便于多题库区分。

## [0.1.0] - 2026-08-22

### Added

- **bench.py**：Ollama 原生 API 评测器——baseline / ladder / athermal / stress / quality 五个子命令，内置六大偏差控制（预热丢弃、实际长度报告、缓存命中检测、组内打乱冷却、双探针截断检测、截断自动复测）。
- **bench_lms.py**：LM Studio（OpenAI 兼容）评测器，流式自测 TTFT/解码吞吐，正确处理 thinking 模型的 reasoning_content；stress 支持 `--rate` ETA 锚点外推。
- **quality_v2.py**：场景化质量评测——内置遥感科研工作者六场景 72 题示例题库，确定性判分（sub/re/and），场景剖面 + Wilson 95% 置信区间，`--no-think` 对照模式。
- **docs/METHODOLOGY.md**：方法论通用版——六大偏差控制、七步流程、ETA 规则、失败甄别表、题库构建七定律、裁决矩阵。
- **examples/**：自建题库模板 + 遥感示例说明。
- **tests/**：核心逻辑单元测试（判分器边界行为、题库完整性、置信区间），CI 无需引擎。
- GitHub Actions CI：Python 3.10/3.12 矩阵，编译 + 单测。
