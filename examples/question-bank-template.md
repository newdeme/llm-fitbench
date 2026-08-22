# 自建题库模板（question-bank template）

> 题库 = 一个 JSON 文件。`quality_v2.py --bank your-bank.json` 加载。
> 脚本本体不含任何真实题库（只有 6 题中性演示）。完整示例：`examples/remote-sensing-researcher/bank.json`（遥感科研工作者 72 题）。
> 出题前先读 `docs/METHODOLOGY.md` §5 七定律。

## 第一步：列你的场景清单（效度定律）

先回答："我日常到底让模型干什么？"按场景配额出题，不按学科配额。示例（科研工作者）：

| 场景 | 题型 | 判分方式 |
|---|---|---|
| A 学术写作 | 错误注入（往正确句子植入典型错误） | 修正形式出现（`sub`/`re`） |
| B 代码知识 | 从你领域真实开源仓库取材的知识题 + bug 定位 | 术语组合（`and`） |
| C 领域事实 | 可溯源事实 + **幻觉探针**（冷僻但可验证） | 子串/正则 |
| D 术语翻译 | 译文必须含标准术语集 | `and` |
| E 实验分析 | 可验证数值（相对提升/降幅，考分母错误） | 数值正则 |
| F 长文检索 | needle-in-haystack（领域文档埋构造事实） | needle 子串 |
| G 通用底噪 | 少量通用推理题作参照基线 | 同上 |

权重按你的优先级设定（如主场景 1.0 / 次场景 0.5）。

## 第二步：写题（判定先行定律）

**先有可机器验证的 key，后有题**。key 从材料核实，不从记忆书写。

### 题库 JSON 结构

```json
{
  "name": "my-bank-v1",
  "scenes": {
    "A": {"name": "学术写作", "weight": 1.0},
    "G": {"name": "通用底噪", "weight": 0.5}
  },
  "haystack": ["长文检索场景的领域段落一", "段落二…"],
  "needles": {
    "N1": {"text": "埋入文档正中的构造事实句…", "answer": "DIOR-R"}
  },
  "questions": [
    {"id": "A1", "scene": "A",
     "prompt": "Rewrite this sentence correctly: \"The experiment results shows…\"",
     "grader": {"mode": "sub", "target": "results show"}},
    {"id": "E1", "scene": "E",
     "prompt": "Baseline mAP is 69.8, ours is 71.2. RELATIVE improvement in percent?",
     "grader": {"mode": "re", "target": "(?<!\\d)2\\.0(?!\\d)"}},
    {"id": "F1", "scene": "F", "needle": "N1",
     "question": "第二阶段消融用了哪个数据集？",
     "grader": {"mode": "sub", "target": "DIOR-R"}}
  ]
}
```

### 判分器模式

| mode | 语义 | 注意 |
|---|---|---|
| `sub` | 大小写不敏感子串 | 最宽松，适合术语 |
| `re` | 正则（忽略大小写） | 数值题必加 `(?<!\d)X(?!\d)` 边界断言 |
| `and` | `targets` 数组全部满足（可嵌套） | 术语组合题 |
| ⚠️ `not` | `must_any` + `forbid` | **禁用于解释型答案**——模型答题会引用原错误形式，forbid 必误伤 |

### 题型配方

- **错误注入**（写作）：选你真实会犯的错误类型植入正确句；key = 修正后的形式。
- **幻觉探针**（必配 2–4 题）：问冷僻但可 100% 核实的事实（如"某数据集第二阶段用了哪个子集"），模型没见过 → 答对=真知识，编造=幻觉信号，拒答=诚实信号。**单独成轴报告，不并入知识分**。
- **needle-in-haystack**：`haystack` 数组存领域段落（运行时循环拼接成长文档），`needles` 存埋入正中的事实句；题目用 `needle` 键 + `question` 引用，运行时自动渲染 prompt。
- **代码知识**：从你领域真实开源仓库 README/代码取材（只静态取材出题，不要在错误环境执行训练代码）。

## 第三步：审校与校准

1. 冒烟 `--limit 4` → 修判分器；
2. 请目标用户审：错误类型是否典型、场景权重是否符合优先级；
3. 校准跑 2 个模型 → **双挂题（全模型失败）逐题审计**：先怀疑判分器 bug，再定性真难度或幻觉；
4. 结果按场景剖面报告 + 各场景 95% 置信区间（Wilson）；**总分 CI 重叠不得宣称排名**。

## 第四步：运行

```bash
python3 scripts/quality_v2.py ollama   -m 模型 --bank your-bank.json --np 512
python3 scripts/quality_v2.py lmstudio -m 模型 --bank your-bank.json
python3 scripts/quality_v2.py ollama   -m 模型 --bank your-bank.json --no-think  # thinking 模型对照
```

每场景 8–16 题即有分档意义；样本小时只分档、不分名次。

## 反面案例（为什么要有定律）

- v1 通用 24 题：四模型全满分，零区分度——违反效度定律；
- forbid 判分全线误伤解释型答案——违反判分容错定律；
- 只报总分不报剖面：两模型总分打平，但检索场景 4/4 vs 1/4 的决策信息被淹没——违反剖面定律。
