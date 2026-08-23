# 场景化质量评测 v2 操作指南（quality_v2.py）

适用：评估本地模型对**用户真实工作负载**的胜任度（区别于 bench.py quality 的 24 题通用快筛）。
原则与规律见 `$FITBENCH/docs/METHODOLOGY.md` §5「题库构建七定律」——出题前必读。

## 工具位置（canonical，勿建副本）

`$FITBENCH/scripts/quality_v2.py`（结果写入 `BENCH_DATA_DIR`，本机设 `$LAB/bench_results`）

**题库外置（v0.2.0 起）**：题库是独立 JSON，`--bank` 加载；脚本只内置 6 题中性演示。本机遥感题库：`$FITBENCH/examples/remote-sensing-researcher/bank.json`

```bash
export BENCH_DATA_DIR=$LAB/bench_results
BANK=$FITBENCH/examples/remote-sensing-researcher/bank.json
python3 $FITBENCH/scripts/quality_v2.py ollama   -m qwen3.6:35b-mlx --bank $BANK --np 512 --no-think
python3 $FITBENCH/scripts/quality_v2.py lmstudio -m ornith-1.5-35b-a3b-mlx --bank $BANK
# 冒烟：--limit 4
# 跑前遵守 128GB 内存纪律：卸载对侧引擎
# thinking 模型注意：--np 384 会因推理耗尽预算产生空 content，脚本自动 3x 复测；
# 若仍大量空响应（如 qwen3.6 的病理性长思考），如实记录为"预算饥饿"特性
```

## 题库结构（72 题，六场景+底噪）

| 场景 | 题数 | 题型 | 判分方式 |
|---|---|---|---|
| A 学术写作 | 16 | 错误注入（主谓一致/术语/中式英语/审稿人常挑：over-claim、泛化、缩写、最高级） | 正确修正形式出现（`sub`/`re`） |
| B DL 代码 | 16 | 源自用户领域真实仓库（EarthVQA/mmrotate）的代码知识 + bug 定位 | 术语组合（`and`） |
| C 遥感领域 | 12 | 可溯源事实题 + **幻觉探针**（冷僻但可验证） | 子串/正则 |
| D 学术翻译 | 8 | 术语匹配（译文须含标准术语集） | `and` |
| E 实验分析 | 8 | 可验证数值（相对提升/降幅——考分母错误） | 数值正则 |
| F 长文检索 | 4 | needle-in-haystack（~5K 领域文档埋构造事实） | needle 子串 |
| G 通用底噪 | 8 | 保留自 v1（参照基线） | 同 v1 |

**场景权重**：主场景 A/B/D/E/F=1.0，次场景 C/G=0.5（由用户工作优先级审定，非均权）。

## 判分器模式与禁忌

- `("sub", s)` 大小写不敏感子串；`("re", r)` 正则（容 Unicode 连字符/LaTeX）；`("and", [g...])` 全部满足
- ⚠️ **禁用 `not/forbid` 模式判 A 类**：解释型答案会引用原错误形式，forbid 必误伤（B4 实证教训）
- 数值题用 `(?<!\d)X(?!\d)` 防子串误匹配（"36" 不得命中 "360"）

## 出题流程（新题/换领域时）

1. 取真实材料（用户 Zotero 文献、领域开源 repo）→ 从材料**核实**每个事实，标注 [SRC]，**先有 key 后有题**；
2. 按 §5 七定律自检（尤其：效度、材料免疫、判定先行）；
3. 冒烟 4 题（A/B/D/E 各 1）→ 修判分器 → 用户审校（错误类型典型性/权重）→ 校准跑；
4. 双挂题（全模型失败）逐题审计：先怀疑判分器，再定性真难度；幻觉探针的编造/拒答单独记录；
5. 结果按场景落 RESULTS.md，登记判分修正审计链。

## 已知模型特性（影响判读）

- **thinking 模型预算饥饿**：ornith @384 空响应 27 次（3x 复测全恢复）；qwen3.6 思考可极长（B3/B5 三次实证：小预算必 `--no-think`，默认模式 @1024 仍 39 次空响应）。空 content ≠ 不可靠，但要如实计数；
- **幻觉风格轴**：gpt-oss 倾向自信编造（C1/C10 双例），ornith 倾向诚实拒答——通用基准测不到的选型维度。
