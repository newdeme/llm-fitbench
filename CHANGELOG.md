# Changelog

本项目的所有显著变更都记录在此文件中。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [0.1.0] - 2026-08-22

### Added

- **bench.py**：Ollama 原生 API 评测器——baseline / ladder / athermal / stress / quality 五个子命令，内置六大偏差控制（预热丢弃、实际长度报告、缓存命中检测、组内打乱冷却、双探针截断检测、截断自动复测）。
- **bench_lms.py**：LM Studio（OpenAI 兼容）评测器，流式自测 TTFT/解码吞吐，正确处理 thinking 模型的 reasoning_content；stress 支持 `--rate` ETA 锚点外推。
- **quality_v2.py**：场景化质量评测——内置遥感科研工作者六场景 72 题示例题库，确定性判分（sub/re/and），场景剖面 + Wilson 95% 置信区间，`--no-think` 对照模式。
- **docs/METHODOLOGY.md**：方法论通用版——六大偏差控制、七步流程、ETA 规则、失败甄别表、题库构建七定律、裁决矩阵。
- **examples/**：自建题库模板 + 遥感示例说明。
- **tests/**：核心逻辑单元测试（判分器边界行为、题库完整性、置信区间），CI 无需引擎。
- GitHub Actions CI：Python 3.10/3.12 矩阵，编译 + 单测。
