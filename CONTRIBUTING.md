# Contributing / 贡献指引

Thanks for helping! 欢迎反馈与改进。这个项目很小：纯 Python 标准库、不依赖任何第三方包。

## Report a problem / 反馈问题（最欢迎）

Open a GitHub Issue with: your machine (chip, RAM, OS), the engine (Ollama / LM Studio) and its version, the exact command, and the full output. 请附完整输出；**不要粘贴任何密钥或私人数据**。

## Share measurements / 分享实测

Real-world evidence is the point of this project. Share new pitfalls, engine quirks, or question banks (see `examples/question-bank-template.md`). Please state the protocol you used (warm-up, temperature, `BENCH_DATA_DIR` layout); numbers without protocol details cannot be compared.

## Pull requests

1. Fork and branch: `fix-xxx` / `feat-xxx`.
2. Keep the constraints: standard library only; deterministic scoring for banks; no private data or personal paths in the repo.
3. Run before submitting:
   ```bash
   python3 -m py_compile scripts/bench.py scripts/bench_lms.py scripts/quality_v2.py
   python3 -m unittest discover -s tests -v
   ```
4. Update `CHANGELOG.md` for user-visible changes.

## Question banks / 题库

Contributed banks must be your own work or carry a compatible license, with the source stated (see how `examples/gsm8k-math/README.md` documents provenance).
