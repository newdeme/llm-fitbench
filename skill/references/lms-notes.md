# LM Studio 特有操作与坑（B2/B5–B7 实战）

## lms CLI 常用

```bash
lms ls                                  # 模型库 + 加载态（✓ LOADED）+ 体积
lms ps                                  # 当前加载实例快照（防污染纪律：每测试块前后各拍一次）
lms load <model-key> -c 262144 -y       # 指定上下文窗口加载（JIT 默认仅 8K，必须显式给）
lms load <model-key> --speculative-draft-mtp -y   # MTP 投机解码（+21% 短文/+49% 长文解码，temp=0 不损正确性）
lms unload --all                        # 卸载全部（测前清场必做）
lms load <model-key> --estimate-only    # 只估算内存不加载
curl -s localhost:1234/api/v0/models    # 加载态 + loaded_context_length + quantization（真实身份以此为准）
```

## JIT 两大坑（B5 实证）

1. **JIT 默认 8K 窗口**：不显式 `lms load --context-length N` 时按 8K 加载；prompt 超载**返回 200 + 空流**（不报 400）→ 极易误判为模型坏/窗口不可用。测长上下文前必显式加载目标窗口。
2. **JIT 切换不驱逐旧模型**：请求另一模型时旧驻留不卸 → 内存挤占 → HTTP 400 加载失败连环。换模型必先 `lms unload`。

## 模型身份陷阱

- `qwen/qwen3.8-27b` 这类 hub 短名是**别名**，实体可能是 `lmstudio-community/Qwen3.8-27B-GGUF/*.gguf`（llama.cpp 后端）。判后端看格式：gguf→llama.cpp，mlx→MLX。
- 同名模型不同后端速度差 2 倍+（Q8 GGUF 17 tok/s vs MLX 39 tok/s）——**选型时后端匹配 > 量化位宽**。

## Draft 模型连锁故障（重要坑）

**症状**：加载主模型报 `failed to load draft model ... wrong number of tensors`，主模型本身完好。

**根因**：模型默认配置 `draftMtp:true` + 空 draftModel → LM Studio 自动从库内挑"兼容"草稿模型；若挑中的草稿文件损坏（如下载不完整的 DFlash2 GGUF，58/81 tensors）→ 整个加载失败。

**修复**（备份先行）：
```bash
CFG=~/.lmstudio/.internal/user-concrete-model-default-config/<org>/<model>.json
cp "$CFG" "$CFG.bak-$(date +%Y%m%d-%H%M%S)"
# 将 llm.load.llama.speculativeDecoding.draftMtp 改为 false
```
更好的方案：显式 MTP（`--speculative-draft-mtp`），不依赖外部草稿文件。
注意 `--no-speculative-draft-mtp` CLI 标志可能不覆盖已存默认配置（B2 实测），要改配置文件。

## thinking 模型解析

ornith 等模型流式输出分 `content` 与 `reasoning_content` 两个字段：
- TTFT 必须以**任意类型首 token** 计时
- 解码吞吐按 completion_tokens（含 reasoning）算
- 只解析 content 会得到天文数字速率（B2 实战：23 万 tok/s 假值）

## gpt-oss（harmony 格式）专项坑（B6/B7 三层）

1. **计量**：`usage.completion_tokens` 虚增 ~2×（reasoning 生成了但不流出却计费）；`usage.prompt_tokens`≈tiktoken 真值。→ 用 SSE 自计（bench_lms 已内置 `usage_divergence` 标记）。
2. **窗口**：131,072 为**真实 token** 上限（98,304 ✅）；超窗秒回空流（200+0 chunks，<10s，可检测）。
3. **空流三病因**：秒空=真超窗；慢空=预算饥饿（reasoning 计入 max_tokens 不可见，预算 ≥4096 才能落 content）或裸文本退化（加指令即好）。鉴别：wall 时间 + 加预算/加指令复测。
4. **TTFT 口径**：实测 TTFT=首**可见** content，含隐藏 reasoning 时长，引用须注明。
5. **跨引擎定案（B7）**：短中 ctx LMS 版 decode 比Ollama +21~23%（baseline 79.2 vs 64.5）；~30K 交叉后 Ollama 反超；长 ctx 重 prefill 场景 Ollama 2.4×（字符/秒口径）；溢出安全 LMS 更好。

## 后台客户端幽灵加载（B5 实证）

Cherry Studio 等客户端的"快速模型"自动命名调用会周期性 JIT 加载模型（如 qwen3.6-35b-a3b, 20.4GB）挤占内存污染吞吐测试——**跑吞吐前关闭该功能或指向云端模型**；质量判分不受影响。

## OpenAI 兼容端点注意

- baseUrl `http://127.0.0.1:1234/v1`，apiKey 任意非空值即可（如 "lm-studio"）
- 模型加载失败时返回 HTTP 400，错误体在 response.error.message（B2：insufficient system resources）
- 流式 + `stream_options: {"include_usage": true}` 可拿 usage（**仅审计用**，见计量坑；工具已自动降级重试）
