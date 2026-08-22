# 示例题库：遥感科研工作者（remote-sensing-researcher）

题库文件：[bank.json](bank.json)（remote-sensing-researcher-72，72 题，独立 JSON，`--bank` 加载；脚本本体不含任何真实题库）。本目录说明其设计与出处，供替换为你自己的领域时参考。

## 场景与配额

| 场景 | 题数 | 说明 | 权重 |
|---|---|---|---|
| A 学术写作 | 16 | 主谓一致/术语/中式英语 + 审稿人常挑（over-claim、过度泛化、缩写、最高级） | 1.0 |
| B DL 代码 | 16 | 源自 EarthVQA 与 mmrotate 开源仓库的真实代码知识 + bug 定位 | 1.0 |
| C 遥感领域 | 12 | 可溯源事实 + 2 道幻觉探针（EarthVQA 图像源=LoveDA；全球扩展版=EarthVL） | 0.5 |
| D 学术翻译 | 8 | 中→英术语精确匹配（RS-VQA / REC / rotated detection…） | 1.0 |
| E 实验分析 | 8 | 相对提升/绝对差/降幅（考分母错误）、warmup 插值、吞吐换算 | 1.0 |
| F 长文检索 | 4 | ~5K tokens 领域文档 needle-in-haystack | 1.0 |
| G 通用底噪 | 8 | 通用推理参照基线 | 0.5 |

## 取材出处（全部公开仓库，仅静态出题）

- EarthVQA（Wang et al.）：README/训练脚本事实（LoveDA 图像源、SFPN→SOBA 两阶段、OA+RMSE 指标）
- mmrotate（OpenMMLab）：OBB 参数化、le90/le135/oc 角度定义、DOTA 多边形标注

未在任何 GPU 环境外执行过上述仓库代码——评测只把代码当"阅读材料"。

## 实测结论样例（Apple M4 Max 128GB）

三模型总分置信区间全部重叠（不判高下），但场景剖面分化显著：写作/翻译 ornith 最强、长文检索 qwen3.6 4/4 全场第一、实验数值分析三家满贯；幻觉探针上 ornith 双题诚实拒答、gpt-oss 双题自信编造——**这些决策信息只有场景剖面 + 探针才给得出**。

## 换领域指南

见 [../question-bank-template.md](../question-bank-template.md)。核心动作：列你的场景清单 → 从你的真实材料核实 key → 写 bank.json → 冒烟 `--limit 4` → 双挂审计 → 场景剖面报告。
