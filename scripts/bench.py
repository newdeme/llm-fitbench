#!/usr/bin/env python3
"""
bench.py -- 本机 Ollama 模型评测工具（方法论固化版）
用法见文件底部 USAGE 或 python3 bench.py --help
偏差控制已内置：预热丢弃、实际长度报告、缓存命中过滤、组内打乱+冷却、
失败分类（400/截断/空响应）、截断自动复测。
"""
import argparse, datetime, json, os, random, re, sys, time
import urllib.request, urllib.error

DEFAULT_HOST = "http://127.0.0.1:11434"
HERE = os.path.dirname(os.path.abspath(__file__))
# 结果目录：优先 BENCH_DATA_DIR 环境变量（私有数据外置），否则落在仓库默认位置（已被 .gitignore 忽略）
OUTDIR = os.environ.get("BENCH_DATA_DIR") or os.path.join(HERE, "..", "bench_results")
os.makedirs(OUTDIR, exist_ok=True)

PASSAGE = (
    "The quick brown fox jumps over the lazy dog while researchers explore "
    "multimodal remote sensing, object evidence enhancement, and scene prior "
    "modeling for visual question answering and referring expression "
    "comprehension across aerial imagery and satellite scenes. "
    "These tasks blend object detection, counting of small targets, and "
    "language reasoning into unified frameworks. We compare backbones, heads, "
    "and fusion modules to measure how context length affects throughput, "
    "prefill latency, and memory pressure on a unified-memory accelerator. "
)
TOK_PER_REP = 89  # 实测每复读约 89 token；最终以 prompt_eval_count 为准

# ---------------- 基础设施 ----------------
def call(host, path, data, timeout):
    req = urllib.request.Request(host + path, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def stop_all(host, sleep_after):
    try:
        call(host, "/api/stop", {"all": True}, 20)
    except Exception:
        pass
    time.sleep(sleep_after)

def gen(host, model, prompt, num_predict, num_ctx=None, timeout=3600):
    opts = {"num_predict": num_predict, "temperature": 0}
    if num_ctx:
        opts["num_ctx"] = num_ctx
    return call(host, "/api/generate",
                {"model": model, "prompt": prompt, "stream": False, "options": opts},
                timeout)

def rates(d):
    dec = d.get("eval_count", 0); dt = d.get("eval_duration", 0)
    pre = d.get("prompt_eval_count", 0); pt = d.get("prompt_eval_duration", 0)
    return {
        "ctx": pre,
        "decode": dec / (dt / 1e9) if dt else 0,
        "decode_tokens": dec,
        "prefill": pre / (pt / 1e9) if pt else 0,
        "ttft": pt / 1e9,
        "cache_hit": bool(pre > 1000 and pt / 1e9 < 0.5),  # 偏差#3：缓存命中检测
    }

def build_prompt(approx_tokens):
    reps = max(1, approx_tokens // TOK_PER_REP + 2)
    return (PASSAGE * reps).strip()

def save(cmd, payload):
    f = os.path.join(OUTDIR, f"{cmd}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json")
    json.dump(payload, open(f, "w"), ensure_ascii=False, indent=1)
    print(f"[saved] {f}")

def warmup(host, model, sleep_after=5):
    stop_all(host, sleep_after)
    gen(host, model, "Hello.", 16, timeout=1800)

# ---------------- P1 基线 ----------------
def cmd_baseline(a):
    out = {}
    for m in a.models:
        print(f"\n===== baseline: {m} =====")
        warmup(a.host, m)
        runs = []
        for i in range(a.runs):
            t0 = time.time()
            d = rates(gen(a.host, m, "Explain the theory of relativity in detail, step by step.",
                          a.np))
            d["wall"] = time.time() - t0
            runs.append(d)
            print(f"  run{i+1}: decode {d['decode']:5.1f} tok/s | wall {d['wall']:5.1f}s | "
                  f"server {d['decode_tokens']/max(d['decode'],1e-9):5.1f}s")
        steady = runs[1:] or runs
        vals = [r["decode"] for r in steady]
        mean = sum(vals) / len(vals)
        print(f"  >> steady decode = {mean:.1f} tok/s (n={len(vals)})")
        out[m] = {"runs": runs, "steady_decode": mean}
    save("baseline", out)

# ---------------- P2 阶梯 ----------------
def cmd_ladder(a):
    out = {}
    for m in a.models:
        print(f"\n===== ladder: {m} =====")
        warmup(a.host, m)
        curve = []
        for ctx in a.ctxs:
            p = build_prompt(ctx)
            try:
                d = rates(gen(a.host, m, p, a.np, num_ctx=ctx))
            except Exception as e:
                print(f"  ~{ctx}: FAILED [{str(e)[:70]}]")
                curve.append({"target": ctx, "status": f"FAIL {str(e)[:60]}"})
                continue
            print(f"  target {ctx:>6} -> actual ctx={d['ctx']:>6} | prefill {d['prefill']:6.1f}/s "
                  f"| TTFT {d['ttft']:6.1f}s | decode {d['decode']:5.1f}/s"
                  + ("  [CACHE-HIT: prefill 无效]" if d["cache_hit"] else ""))
            curve.append({"target": ctx, **d, "status": "OK"})
        out[m] = curve
    save("ladder", out)

# ---------------- P3 去热排名 ----------------
def cmd_athermal(a):
    data = {m: [] for m in a.models}
    random.seed()
    for g in range(1, a.groups + 1):
        order = a.models[:]
        random.shuffle(order)
        print(f"\n===== group {g}/{a.groups} order={order} =====")
        for m in order:
            stop_all(a.host, a.cooldown)
            try:
                gen(a.host, m, "Hello.", 16, timeout=1800)  # 预热（加载）
                d = rates(gen(a.host, m, build_prompt(a.ctx), a.np))
            except Exception as e:
                print(f"  {m:24s} FAILED [{str(e)[:60]}]"); continue
            print(f"  {m:24s} decode {d['decode']:5.1f} | TTFT {d['ttft']:6.1f}s"
                  + ("  [cache-hit→prefill弃用]" if d["cache_hit"] else ""))
            data[m].append(d)
    print("\n===== 去热排名（decode 均值±std；prefill 仅采信非缓存命中） =====")
    rows = []
    for m in a.models:
        if not data[m]:
            rows.append((m, 0, 0, 0, 0)); continue
        vals = [x["decode"] for x in data[m]]
        mean = sum(vals) / len(vals)
        std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5 if len(vals) > 1 else 0
        pre = [x["prefill"] for x in data[m] if not x["cache_hit"]]
        pmean = sum(pre) / len(pre) if pre else 0
        rows.append((m, mean, std, pmean, len(vals)))
        print(f"  {m:24s} decode {mean:5.1f} ± {std:4.1f} tok/s | prefill(有效) {pmean:6.1f}/s | n={len(vals)}")
    for i, r in enumerate(sorted(rows, key=lambda x: -x[1]), 1):
        print(f"  #{i} {r[0]:24s} {r[1]:5.1f} ± {r[2]:4.1f}")
    save("athermal", {m: data[m] for m in a.models})

# ---------------- P4 极限窗口 ----------------
def cmd_stress(a):
    out = {}
    print(f"\n===== stress | ctxs={a.ctxs} =====")
    for m in a.models:
        stop_all(a.host, 15)
        probes = []
        for ctx in a.ctxs:
            p = build_prompt(ctx)
            try:
                d = rates(gen(a.host, m, p, 64, num_ctx=ctx))
                probes.append({"target": ctx, "ctx": d["ctx"], "ttft": d["ttft"],
                               "decode": d["decode"], "status": "OK"})
            except urllib.error.HTTPError as e:
                probes.append({"target": ctx, "status": f"WINDOW_REJECT({e.code})"})
            except Exception as e:
                probes.append({"target": ctx, "status": f"LOAD_FAIL({str(e)[:50]})"})
            pr = probes[-1]
            print(f"  {m:24s} @{ctx:>6}: {pr['status']}"
                  + (f" actual={pr['ctx']} TTFT={pr['ttft']:.0f}s decode={pr['decode']:.1f}"
                     if pr["status"] == "OK" else ""))
        # 双探针截断检测（偏差#5）
        oks = [p_ for p_ in probes if p_["status"] == "OK"]
        verdict = "OK"
        if len(oks) >= 2 and oks[-1]["ctx"] < oks[0]["ctx"] * 1.05:
            verdict = f"SILENT_TRUNCATION(有效窗口≈{oks[-1]['ctx']})"
        elif any("WINDOW_REJECT" in p_["status"] for p_ in probes):
            verdict = "WINDOW_REJECT"
        print(f"  >> {m}: {verdict}")
        out[m] = {"probes": probes, "verdict": verdict}
    save("stress", out)

# ---------------- P5 质量 ----------------
BANK = [
 ("M1","math","What is 27 * 8? Answer with only the number.",("re",r"(?<!\d)216(?!\d)")),
 ("M2","math","What is 15% of 240? Answer with only the number.",("re",r"(?<!\d)36(?!\d)")),
 ("M3","math","What is 3 to the 5th power (3^5)? Number only.",("re",r"(?<!\d)243(?!\d)")),
 ("M4","math","Square root of 1444 as an integer. Number only.",("re",r"(?<!\d)38(?!\d)")),
 ("M5","math","Average of 12, 18, 24, 36. Answer as a decimal.",("sub","22.5")),
 ("M6","math","1000 divided by 8? Number only.",("re",r"(?<!\d)125(?!\d)")),
 ("L1","logic","All Bloops are Razzles, all Razzles are Lazzles. Are all Bloops Lazzles? yes/no only.",("sub","yes")),
 ("L2","logic","Continue: 2, 4, 8, 16, ? Next number only.",("re",r"(?<!\d)32(?!\d)")),
 ("L3","logic","If today is Wednesday, what weekday is it 9 days from now? Day name only.",("re",r"\bFriday\b")),
 ("L4","logic","Odd one out: dog, cat, elephant, car? Item only.",("sub","car")),
 ("F1","fact","Capital of Australia? City only.",("re",r"\bCanberra\b")),
 ("F2","fact","Capital of France? City only.",("re",r"\bParis\b")),
 ("F3","fact","Year WWII ended? Year only.",("re",r"(?<!\d)1945(?!\d)")),
 ("F4","fact","Chemical symbol of gold? Symbol only.",("re",r"\bAu\b")),
 ("F5","fact","Largest planet in the Solar System? Name only.",("re",r"\bJupiter\b")),
 ("F6","fact","Who wrote Romeo and Juliet? Surname only.",("re",r"(?i)shakespeare")),
 ("R1","rs","NDVI is computed from which two spectral bands?",("re",r"(?i)near.{0,2}infrared|\bnir\b")),
 ("R2","rs","Typical spatial resolution of Landsat 8 OLI panchromatic, in meters? Number only.",("re",r"(?<!\d)15(?!\d)")),
 ("R3","rs","What does RGB stand for? The three color words.",("sub","blue")),
 ("R4","rs","Higher spatial resolution: close-range aerial photo or satellite image? Answer one.",("re",r"(?i)aerial")),
 ("C1","cn","水的化学式是什么？只回答化学式。",("re",r"(?i)h2o|h₂o")),
 ("C2","cn","一年有多少个月？只回答数字。",("re",r"(?<!\d)12(?!\d)")),
 ("C3","cn","圆的面积公式是什么？用 π 和半径 r 表示。",("re",r"(?i)(\\pi|π|pi)[\s\^{}*]{0,8}r[\s\^{}*]{0,8}(2|²)")),
 ("C4","cn","北京是中国的首都吗？只回答“是”或“否”。",("sub","是")),
]

def grade(grader, text):
    mode, t = grader
    if mode == "re":
        return re.search(t, text or "") is not None
    return t.lower() in (text or "").lower()

def cmd_quality(a):
    bank = BANK[: a.limit] if a.limit else BANK
    out = {}
    for m in a.models:
        print(f"\n===== quality: {m} ({len(bank)} 题, 筛查级) =====")
        stop_all(a.host, 3)
        empties, score, detail = 0, 0, {}
        for qid, cat, prompt, grader in bank:
            text, used, attempt = "", 0, 0
            while attempt < 2:  # 截断/空响应自动复测一次（3 倍预算）
                budget = a.np if attempt == 0 else a.np * 3
                try:
                    d = gen(a.host, m, prompt, budget)
                except Exception as e:
                    text, used = f"[ERR {str(e)[:40]}]", 0; break
                text = (d.get("response") or "").strip()
                used = d.get("eval_count", 0)
                if text and grade(grader, text): break
                if text and used < budget * 0.9: break       # 真失败，非截断
                if not text: empties += 1; attempt += 1; continue
                attempt += 1                                   # 截断嫌疑 → 加预算
            ok = grade(grader, text)
            score += ok
            detail[qid] = {"pass": ok, "cat": cat, "tail": text.replace("\n", " ")[-100:]}
            print(f"  {qid}: {'PASS' if ok else 'FAIL'}{' (复测)' if attempt else '':6s} | ...{detail[qid]['tail'][:80]}")
        print(f"  >> {m}: {score}/{len(bank)} | 空响应 {empties} 次(可靠性)")
        out[m] = {"score": score, "total": len(bank), "empties": empties, "detail": detail}
    print("\n===== 排名（正确率 → 空响应升序） =====")
    for i, (m, r) in enumerate(sorted(out.items(), key=lambda kv: (-kv[1]["score"], kv[1]["empties"])), 1):
        print(f"  #{i} {m:24s} {r['score']}/{r['total']}  empties={r['empties']}")
    save("quality", out)

# ---------------- CLI ----------------
def pcommon(p):
    p.add_argument("-m", "--models", nargs="+", required=True)
    p.add_argument("--host", default=DEFAULT_HOST)

USAGE = """本机模型评测（配合 METHODOLOGY.md 使用）
  bench.py baseline -m 模型 [--runs 3] [--np 300]      P1 基线吞吐
  bench.py ladder   -m 模型 --ctxs 2048 8192 32768      P2 上下文阶梯+TTFT
  bench.py athermal -m 模型们 --groups 3 --cooldown 20  P3 去热排名
  bench.py stress   -m 模型 --ctxs 65536 131072         P4 极限窗口+截断检测
  bench.py quality  -m 模型 [--np 256] [--limit 12]     P5 质量筛查
"""
if __name__ == "__main__":
    ap = argparse.ArgumentParser(usage=USAGE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("baseline"); pcommon(p)
    p.add_argument("--runs", type=int, default=3); p.add_argument("--np", type=int, default=300)
    p.set_defaults(f=cmd_baseline)
    p = sub.add_parser("ladder"); pcommon(p)
    p.add_argument("--ctxs", nargs="+", type=int, default=[2048, 8192, 32768])
    p.add_argument("--np", type=int, default=256); p.set_defaults(f=cmd_ladder)
    p = sub.add_parser("athermal"); pcommon(p)
    p.add_argument("--groups", type=int, default=3)
    p.add_argument("--cooldown", type=int, default=20)
    p.add_argument("--ctx", type=int, default=4800)
    p.add_argument("--np", type=int, default=256); p.set_defaults(f=cmd_athermal)
    p = sub.add_parser("stress"); pcommon(p)
    p.add_argument("--ctxs", nargs="+", type=int, default=[65536, 131072])
    p.set_defaults(f=cmd_stress)
    p = sub.add_parser("quality"); pcommon(p)
    p.add_argument("--np", type=int, default=256)
    p.add_argument("--limit", type=int, default=0); p.set_defaults(f=cmd_quality)
    a = ap.parse_args()
    a.f(a)
