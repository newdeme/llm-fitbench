# llm-fitbench

> An evidence-based toolbox for benchmarking **local LLMs on your own machine** — answering "does this model actually fit my hardware and my work?"

[![CI](https://github.com/newdeme/llm-fitbench/actions/workflows/ci.yml/badge.svg)](https://github.com/newdeme/llm-fitbench/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](CONTRIBUTING.md)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Release](https://img.shields.io/github/v/release/newdeme/llm-fitbench?include_prereleases)](https://github.com/newdeme/llm-fitbench/releases)

English | [中文](README.md)

## Who is this for

- People running Ollama / LM Studio local models on Apple Silicon Macs (or unified-memory machines)
- Anyone tired of "feels faster" comparisons and wanting reproducible evidence
- Anyone who wants selection decisions based on **local measurement**, not leaderboard numbers from someone else's hardware

## What problems it solves

| Trap | Symptom | llm-fitbench's answer |
|---|---|---|
| Silent truncation | Claims 128K context, silently drops everything past 64K | Dual-probe detection (P4) |
| Thermal throttling bias | Rankings drift with test order | Shuffled multi-group cooled ranking (P3) |
| Generic-benchmark mismatch | Great scores, bad at *your* job | Workload-scenario question bank (quality_v2) |
| Invisible hallucination | Confident but fabricated answers | Hallucination-probe questions (fabricate vs. refuse) |

## Quick start (5 min)

```bash
git clone https://github.com/newdeme/llm-fitbench.git
cd llm-fitbench

# 1) Baseline throughput (Ollama) — decode < 15 tok/s is unusable interactively
python3 scripts/bench.py baseline -m your-model:tag --runs 3

# 2) Context ladder + TTFT
python3 scripts/bench.py ladder -m your-model:tag --ctxs 2048 8192 32768

# 3) Quality quick screen (24 general questions)
python3 scripts/bench.py quality -m your-model:tag

# LM Studio engine: bench_lms.py (OpenAI-compatible :1234), same subcommands
```

Results are written to `bench_results/` (or the directory in `BENCH_DATA_DIR`).

## Core ideas

1. **Six bias controls** — cold-load, nominal-vs-actual length, prompt-cache hits, thermal throttling, failure-type confusion, grader bugs. Each backed by real failures, all encoded in the tools.
2. **Seven laws of question-bank construction** — validity (your workload) over difficulty; private-material questions are structurally immune to data contamination; the grader is the biggest error source; scenario profiles over total scores; hallucination probes as a separate axis; thinking-budget starvation is a cost, not noise.
3. **Failure triage** — HTTP 400 ≠ OOM ≠ silent truncation. Different failures, different remedies.

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Workload-scenario quality evaluation (quality_v2)

Generic benchmarks can't tell whether a model fits *you*. `scripts/quality_v2.py` evaluates your real workload via **external question-bank JSON files** (`--bank`); the script itself ships only a 6-question neutral demo bank.

A complete example bank is included: **72 questions across six scenarios for a remote-sensing researcher** (academic writing fixes / DL code knowledge / domain facts + hallucination probes / terminology translation / experiment number analysis / long-doc fact retrieval), all deterministically graded.

**Bring your own bank**: it's just a JSON file — no Python knowledge required. Template: [examples/question-bank-template.md](examples/question-bank-template.md).

```bash
# with the example bank
python3 scripts/quality_v2.py ollama -m model --bank examples/remote-sensing-researcher/bank.json
# your own bank / thinking-off control / smoke
python3 scripts/quality_v2.py ollama -m model --bank my-bank.json --np 512
python3 scripts/quality_v2.py ollama -m model --bank my-bank.json --no-think
python3 scripts/quality_v2.py ollama -m model --bank my-bank.json --limit 4
```

## Privacy

- Everything runs locally against your Ollama/LM Studio APIs; no telemetry, no uploads.
- Keep personal experiment data out of the repo via `BENCH_DATA_DIR`.

## Roadmap

- [ ] External question-bank loading (--bank path.json)
- [ ] More engines (llama.cpp server / vLLM)
- [ ] Automated RESULTS.md report generation

## License

Apache-2.0. See [LICENSE](LICENSE).
