# 评测坑清单与失败甄别（B1–B7 实测批次提炼）

来源：`$FITBENCH/docs/METHODOLOGY.md` 的浓缩 + 本机实战案例。完整版以仓库 docs 为准。

## 八大偏差控制（测速前自查）

| # | 偏差 | 实战案例 | 控制 |
|---|---|---|---|
| 1 | 冷加载 | run1 墙上 20.5s vs 服务端 8.3s | 预热 1 次丢弃；稳态取 run2+ |
| 2 | 名义≠实际长度 | 目标"4K"实测 18K；"64K"实测 48K | 一律报 `prompt_eval_count` / `prompt_tokens`（注意 tokenizer 差异，见计量三坑） |
| 3 | prompt 缓存命中 | prefill 算出 5.9 亿 tok/s | 同 prompt 只信首次 prefill；工具已自动标记 cache_hit |
| 4 | 热节流 | 同模型 35.9→28.6 tok/s（排在末位被热惩罚） | 组内随机打乱×3组×15–20s冷却，报均值±std |
| 5 | 失败类型混淆 | 400 ≠ OOM ≠ 静默截断 ≠ 空流（三病因） | 见下表 |
| 6 | 判分者出错 | key 错 2 题、正则漏 U+2011 连字符/LaTeX | 原始输出必展示；可疑失败 3 倍预算复测 |
| 7 | **驻留污染（B5–B7）** | ornith 69GB 残留压低 qwen3.6 首测 -7%；B5 累积驻留压低 muse/qwen3.8/gpt-oss ladder **14–27%** | 三重防污染：①测前卸双侧（`keep_alive:0` + `lms unload --all`）②每块前后 `lms ps`+`/api/ps` 快照比对 ③多模型同批**交错**而非顺序 |
| 8 | **计量口径偏差（B7）** | usage 虚增 ~2× / tokenizer 少计 ~2× / chunk 比例假设错（详见下方计量三坑） | SSE 自计为准 + usage_divergence 标记；自然文本交叉验证；间接推断必经 tiktoken 仲裁 |

## 失败甄别表

| 现象 | 判定 | 实战案例 |
|---|---|---|
| HTTP 400 | 超窗拒绝（明确报错） | muse:30b @138K |
| prompt_eval_count / actual 停在某值不随输入增长 | **静默截断**（元数据声明的窗口不可信） | gpt-oss:120b 声明 131072 实收 65538 |
| 连接断/超时/加载失败 | 疑似 OOM/加载失败 | B2: ornith 被 qwen-Q8 挤出内存（insufficient resources） |
| **秒回空流**（<10s，无 prefill） | 真超窗拒绝（静默，无 HTTP 错） | LMS gpt-oss @131072 真实 token 之上（1.6M 字符文本） |
| **慢空流**（prefill 全时长后无输出） | 预算饥饿或裸文本退化（见下） | LMS gpt-oss：32/64/96 预算全灭、4096 全通 |
| usage 与 SSE 自计分歧 >15% | 计量口径坑（见计量三坑） | LMS gpt-oss completion 虚增 2.03× |

**双探针法**（发现静默截断的唯一可靠手段）：同一模型分别灌 ~64K 和 ~128K，若第二次实际处理量相比第一次几乎不增（<+5%）→ 窗口静默截断。单看一个长度无法发现（eval_count 看起来"正常"）。

## 空流三病因鉴别（B7，200 但无 content）

| 症状 | 病因 | 判别法 |
|---|---|---|
| 秒回空流（<10s，无 prefill） | 真超窗拒绝 | wall 时间 |
| 慢空流（prefill 全时长后无输出） | **预算饥饿**：harmony 类模型 reasoning 计入 max_tokens 且不流出，小预算 content 永不启动 | 加大预算复测（4096 通即坐实） |
| 慢空流（裸填充文本输入） | 裸文本 × 对话格式退化（无指令时仅生成不可见通道） | 追加指令复测（好转即坐实） |

另有第四种"空响应"：Ollama 裸 `/api/generate` 口径对部分模型出空响应假象（muse 实证）——改用 chat 口径即好，属工具口径问题非模型问题。

## 计量三坑（B7 tiktoken o200k_base 仲裁实证）

| # | 坑 | 实证 | 对策 |
|---|---|---|---|
| M1 | LMS `usage.completion_tokens` 虚增 ~2×（幻影 reasoning：生成了不流出却计费）；prompt 侧≈真值 | completion 真值 110 vs 自报 223 | bench_lms 已改 SSE 自计 + `usage_divergence` 自动标记；引用 LMS usage 前先看分歧标记 |
| M2 | Ollama gpt-oss tokenizer 对高重复文本少计 ~2×（自然文本正常，疑似 pre-tokenizer 差异） | prompt 真值 8,376 vs 自报 4,098 | 关键测量用自然文本交叉验证；gpt-oss(Ollama) 在合成填充文本上的 "actual ctx" 为半价单位 |
| M3 | 间接推断的 chunk→token 比例假设错误（曾假设每 chunk 1 token，实际 ~2 → 143 tok/s 假值，真值 79.2） | 节奏探针单点结论被 SSE 自计推翻 | **任何间接推断必须经 tiktoken 真值交叉验证才可入档**；prefill 跨引擎对比用字符/秒口径（prefill_cps） |

## 超窗行为对比（两引擎均静默，无 HTTP 错误，上层必须自防）

| 引擎 | 超窗行为 | 危险度 |
|---|---|---|
| Ollama（gpt-oss 实证） | 丢头保尾（截前 num_ctx/2）+ **模型编造丢失内容**（NIAH 实证） | 高（答案看起来正常，内容是编的） |
| LM Studio（gpt-oss 实证） | 秒回空流（200 + 0 chunks，1s） | 低（可检测，但无提示） |

## 评测口径（两引擎差异）

- Ollama（bench.py）：`eval_count/eval_duration`=解码，`prompt_eval_*`=预填充，非流式。
- LM Studio（bench_lms.py）：OpenAI 流式**SSE 自计**（每 delta≈1 token，tiktoken 实证一致）；usage 仅审计并记 `usage_divergence`；prefill 双口径（tok/s + `prefill_cps` 字符/秒，跨 tokenizer 公平）；TTFT=任意类型首 token（**含 reasoning_content**，thinking 模型必须计入，否则吞吐算出天文数字）。
- **TTFT 口径注记（B7）**：不可见 reasoning 模型（LMS gpt-oss harmony）实测 TTFT=首**可见** content，含隐藏 reasoning 时长——引用时注明，勿与"用户感知首字延迟"混同。

## 128GB 内存纪律

- 同一时刻只跑一个大模型：Ollama `keep_alive:0` 逐模型卸载（`/api/stop` 在 0.32.x 返回 404）↔ LM Studio `lms unload --all`。
- 切换引擎前先卸对侧再加载，否则 insufficient resources（B2 实战：ornith 64.58GiB 被 qwen-Q8 挤掉）。
- **LM Studio JIT 默认 8K 窗口**：prompt 超载返回 200+空流（不报 400）→ 测前必须 `lms load --context-length N` 显式加载。
- **LM Studio JIT 切换不驱逐旧模型**：大模型驻留时换载 → HTTP 400 加载失败连环 → 换模型必先 `lms unload`。
- **吞吐测试期间关闭 Cherry Studio 等后台客户端的快速模型自动调用**（幽灵加载：周期性 JIT 加载挤占内存，B5 实害一处）；质量判分不受影响。
- 长上下文压测额外吃 KV cache 内存，加载窗口越大越要先清理。

## 19 条坑速查

1. run1 含冷加载，弃之
2. 长度以实际 token 计数为准（且防 tokenizer 计量坑 M1/M2）
3. 同 prompt 复用毁 prefill 数据
4. 固定顺序测多模型 = 热偏差，打乱+冷却+多组
5. 400 ≠ OOM ≠ 静默截断 ≠ 空流三病因
6. 声明的 context_length 不可信
7. 双探针才能发现静默截断
8. 截断失败用 3 倍预算复测再判（话痨模型如 laguna 简单题烧 768 tok）
9. 空响应先查口径（裸 generate → chat）与预算饥饿，再谈可靠性
10. 判分 key 自己也会错，须审计
11. 正则要容 Unicode 连字符（U+2011）、LaTeX、中文标点
12. 改配置先查真实归属（全局默认≠会话模型）再备份增量
13. 测前卸双侧 + ps 快照 + 同批交错（驻留污染压值 7–27%）
14. LMS JIT 默认 8K 窗超载 = 静默空流，先 `lms load --context-length`
15. LMS JIT 切换不驱逐旧模型，换模型先 `lms unload`
16. 吞吐测试关后台客户端幽灵加载（Cherry Studio 快速模型）
17. Ollama 0.32.x `/api/stop` 404 → 卸载用 `keep_alive:0`
18. 间接推断（chunk 比例外推）必须 tiktoken 真值交叉验证
19. 超窗两引擎均静默：Ollama 丢头+编造（危险），LMS 秒空流（可检测）——上层自防
