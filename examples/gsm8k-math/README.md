# GSM8K 分层数学推理题库（gsm8k-math-12）

从 GSM8K（Grade School Math 8K，OpenAI）test 集构建的**分层数学推理**示例题库，用于补足遥感科研题库（`../remote-sensing-researcher/`）在通用推理/数学维度的区分度。

## 数据来源与许可

- 来源：[openai/gsm8k](https://huggingface.co/datasets/openai/gsm8k)（HuggingFace），`main` 配置 `test` 分片前 300 行
- 许可：**MIT**（数据集原许可）。本仓库再分发其子集，遵循原许可
- 原论文：*Cobbe et al., "Training Verifiers to Solve Math Word Problems", 2021*

## 选法（完全可复现）

1. 取 test 分片前 300 行；
2. 筛最终答案为**纯正整数**者（剔除逗号分隔大数/小数/负数，286 题可用）；
3. 按答案区推理步数（非 `####` 行数）分层：易 ≤2 步 / 中 3–4 步 / 难 ≥5 步；
4. 每层按源索引升序取前 4 题，共 12 题。

| 层 | 题号 | 步数范围 | 答案范围 |
|---|---|---|---|
| 易 | H1–H4 | 2 | 3–540 |
| 中 | H5–H8 | 3–4 | 13–694 |
| 难 | H9–H12 | 5–7 | 45–460 |

## 判分

- 判分器：`re` 模式 + 数字边界守卫（`(?<!\d)N(?!\d)`，防 "36" 命中 "360"）
- 提示词要求模型逐步推理后**末行单独给出整数**；解释中出现正确数同样判过（宽松口径，注重能力而非格式服从）

## 用法

```bash
python3 scripts/quality_v2.py ollama -m 模型:tag --bank examples/gsm8k-math/bank.json --np 512
python3 scripts/quality_v2.py lmstudio -m 模型 --bank examples/gsm8k-math/bank.json
# 冒烟：--limit 4
```

判读建议：按层报告（易/中/难剖面），总分意义有限；与遥感题库**分开跑、分开比**（场景权重体系不同）。
