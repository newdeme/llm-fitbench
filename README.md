# llm-fitbench

> 本地大模型"适配性"实证评测工具箱——用一套可复现的流程，回答"**这个模型在我的电脑上、对我的工作，到底行不行**"。

[English](README.en.md) | 中文

## 适合谁

- 在 Apple Silicon Mac（或统一内存机器）上跑 Ollama / LM Studio 本地模型的人
- 新模型下了一堆，反复"感觉哪个快哪个好"却拿不出依据的人
- 想把选型决策建立在**本机实测**而非网上跑分上的人

## 它解决什么问题

本地模型选型的四个经典陷阱，本工具全部有对应手段：

| 陷阱 | 表象 | llm-fitbench 的答案 |
|---|---|---|
| 静默截断 | 声明 128K 窗口，实际 >64K 就悄悄丢前文 | 双探针法（P4）自动检测 |
| 热节流污染 | 模型排名随测试顺序漂移 | 打乱×多组×冷却的去热排名（P3） |
| 通用基准失真 | 跑分很高，你的活干不了 | 场景化题库（quality_v2，按你的工作负载出题） |
| 幻觉不可见 | 答案自信但编造 | 幻觉探针题，测"编造 vs 拒答"品格 |

## 五分钟上手

```bash
git clone https://github.com/newdeme/llm-fitbench.git
cd llm-fitbench

# 1) 基线吞吐（Ollama）——decode < 15 tok/s 可直接淘汰
python3 scripts/bench.py baseline -m 你的模型:tag --runs 3

# 2) 上下文阶梯 + TTFT（看真实工作长度可不可用）
python3 scripts/bench.py ladder -m 你的模型:tag --ctxs 2048 8192 32768

# 3) 质量快筛（24 题通用）
python3 scripts/bench.py quality -m 你的模型:tag

# LM Studio 引擎用 bench_lms.py（OpenAI 兼容端口 1234），子命令相同
```

结果 JSON 自动写入 `bench_results/`（或 `BENCH_DATA_DIR` 环境变量指定的目录）。

## 核心理念（为什么这样测）

1. **六大偏差控制**：冷加载/名义长度/缓存命中/热节流/失败混淆/判分错误——每一个都有实测翻车案例，全部固化在工具里。
2. **题库构建七定律**：效度（测你的工作负载）> 难度；私有材料出题天然免疫数据污染；判分器是最大错误源，双挂题先审判分器；场景剖面 > 总分排名；幻觉探针单列；thinking 预算饥饿是成本不是噪声。
3. **失败甄别**：400 ≠ OOM ≠ 静默截断——三种"死法"不同药方。

详见 [docs/METHODOLOGY.md](docs/METHODOLOGY.md)。

## 场景化质量评测（quality_v2）

通用跑分测不出"适不适合你"。`scripts/quality_v2.py` 内置一套**遥感科研工作者六场景 72 题示例**（学术写作纠错 / DL 代码知识 / 领域事实+幻觉探针 / 术语翻译 / 实验数值分析 / 长文事实检索），每题确定性判分。

**换成你自己的题库**：题库就是脚本顶部的一个 Python 列表——复制脚本、替换题目列表即可。模板与判分指南：[examples/question-bank-template.md](examples/question-bank-template.md)。

```bash
python3 scripts/quality_v2.py ollama -m 模型 --np 512          # 场景剖面 + 95% CI
python3 scripts/quality_v2.py ollama -m 模型 --no-think        # thinking 模型关思考对照
```

## 数据隐私

- 全部评测在你的本机执行，与 Ollama/LM Studio 本地 API 通信；
- 无遥测、无外部上传；评测结果默认写本地目录；
- 建议把私有结果目录与方法论分开维护（`BENCH_DATA_DIR` 外置），不要把个人实验数据提交进任何仓库。

## 项目结构

```
llm-fitbench/
├── scripts/            # bench.py / bench_lms.py / quality_v2.py
├── docs/METHODOLOGY.md # 方法论：偏差控制、七定律、失败甄别
├── examples/           # 题库模板 + 遥感科研示例说明
└── tests/              # 核心逻辑单元测试（CI 运行，无需引擎）
```

## 路线图

- [ ] 外置题库文件加载（--bank path.json）
- [ ] 更多引擎适配（llama.cpp server / vLLM）
- [ ] 结果汇总报告自动生成（RESULTS.md 模板化）

## 许可

Apache-2.0。见 [LICENSE](LICENSE)。
