#!/usr/bin/env python3
"""
bench_lms.py -- LM Studio (OpenAI-compatible) 评测适配器
方法论同 METHODOLOGY.md；复用 bench.py 的题库/判分/存档。
测量口径（自测，不依赖服务端自报速度）：
  TTFT   = 首 content chunk 到达时间（含 prefill）
  decode = completion_tokens / (总时长 - TTFT)
  prompt_tokens / completion_tokens 采信 usage 字段（缺省时以 chunk 数近似）
"""
import argparse, datetime, json, os, sys, time
import urllib.request, urllib.error

# 复用 bench.py 的公共部件（题库/判分/prompt构造/存档）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench import BANK, grade, build_prompt, save

BASE = "http://127.0.0.1:1234/v1"

def chat_stream(model, prompt, max_tokens, temperature=0.0, timeout=3600, stream_opts=True):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temperature,
            "stream": True}
    if stream_opts:
        body["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(BASE + "/chat/completions",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time(); ttft = None; chunks = 0; parts = []; usage = {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "): continue
                payload = line[6:]
                if payload == "[DONE]": break
                try: obj = json.loads(payload)
                except Exception: continue
                if obj.get("usage"): usage = obj["usage"]
                ch = obj.get("choices") or []
                if ch:
                    delta = ch[0].get("delta") or {}
                    c = delta.get("content")
                    rc = delta.get("reasoning_content")   # thinking 模型的推理流
                    if c or rc:
                        if ttft is None: ttft = time.time() - t0
                        if c:
                            parts.append(c); chunks += 1
    except urllib.error.HTTPError as e:
        if stream_opts and e.code == 400:          # 服务端不认 stream_options → 去掉重试
            return chat_stream(model, prompt, max_tokens, temperature, timeout, False)
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:120]}")
    t_end = time.time()
    text = "".join(parts)
    comp = usage.get("completion_tokens") or chunks
    ptok = usage.get("prompt_tokens")
    gen = (t_end - t0) - (ttft or 0)
    return {"text": text, "prompt_tokens": ptok, "completion_tokens": comp,
            "ttft": ttft, "total": t_end - t0,
            "decode": comp / gen if gen > 0 and comp else 0,
            "prefill": (ptok / ttft) if ttft and ptok else 0,
            "cache_hit": bool(ptok and ptok > 1000 and ttft and ttft < 0.5)}

def warmup(model):
    r = chat_stream(model, "Hello.", 8)
    return r

# ---------- P1 baseline ----------
def cmd_baseline(a):
    out = {}
    for m in a.models:
        print(f"\n===== baseline: {m} =====")
        w = warmup(m)
        print(f"  warmup ok (prompt_tokens={w['prompt_tokens']})")
        runs = []
        for i in range(a.runs):
            r = chat_stream(m, "Explain the theory of relativity in detail, step by step.", a.np)
            runs.append(r)
            print(f"  run{i+1}: decode {r['decode']:5.1f} tok/s | TTFT {r['ttft']:5.2f}s | "
                  f"total {r['total']:6.1f}s | {r['completion_tokens']} tok")
        steady = [r["decode"] for r in runs[1:]] or [r["decode"] for r in runs]
        mean = sum(steady) / len(steady)
        print(f"  >> steady decode = {mean:.1f} tok/s")
        out[m] = {"runs": [{k: r[k] for k in ('decode','ttft','total','completion_tokens')} for r in runs],
                  "steady_decode": mean}
    save("lms-baseline", out)

# ---------- P2 ladder ----------
def cmd_ladder(a):
    out = {}
    for m in a.models:
        print(f"\n===== ladder: {m} =====")
        warmup(m)
        curve = []
        for ctx in a.ctxs:
            p = build_prompt(ctx)
            try:
                r = chat_stream(m, p, a.np)
            except Exception as e:
                print(f"  ~{ctx}: FAILED [{str(e)[:80]}]")
                curve.append({"target": ctx, "status": f"FAIL {str(e)[:60]}"}); continue
            flag = "  [CACHE-HIT: prefill 弃用]" if r["cache_hit"] else ""
            print(f"  target {ctx:>6} -> actual {r['prompt_tokens'] or '?':>6} | prefill {r['prefill']:6.1f}/s "
                  f"| TTFT {r['ttft']:6.1f}s | decode {r['decode']:5.1f}/s{flag}")
            curve.append({"target": ctx, "actual": r["prompt_tokens"], "prefill": r["prefill"],
                          "ttft": r["ttft"], "decode": r["decode"], "status": "OK"})
        out[m] = curve
    save("lms-ladder", out)

# ---------- P4 stress（双探针截断检测） ----------
def cmd_stress(a):
    out = {}
    for m in a.models:
        warmup(m)
        probes = []
        prev_rate = a.rate  # 可选锚点：--rate 传入已实测 prefill tok/s
        for idx, ctx in enumerate(sorted(a.ctxs)):
            if prev_rate:
                eta = ctx / prev_rate / 60
                print(f"  [ETA] {m} @{ctx}: 预计 prefill ~{eta:.0f} 分钟（按 {prev_rate:.0f} tok/s 外推，实际会随长度衰减→取保守值，更长）")
            p = build_prompt(ctx)
            try:
                r = chat_stream(m, p, 64)
                if r["ttft"] and r["prompt_tokens"]:
                    prev_rate = r["prompt_tokens"] / r["ttft"]  # 用实测更新下一个探针的 ETA 锚点
                probes.append({"target": ctx, "actual": r["prompt_tokens"], "ttft": r["ttft"],
                               "decode": r["decode"], "status": "OK"})
            except Exception as e:
                probes.append({"target": ctx, "status": f"FAIL {str(e)[:60]}"})
            pr = probes[-1]
            print(f"  {m} @{ctx:>6}: {pr['status']}"
                  + (f" actual={pr['actual']} TTFT={pr['ttft']:.0f}s decode={pr['decode']:.1f}"
                     if pr["status"] == "OK" else ""))
        oks = [x for x in probes if x["status"] == "OK" and x.get("actual")]
        verdict = "OK"
        if len(oks) >= 2 and oks[-1]["actual"] < oks[0]["actual"] * 1.05:
            verdict = f"SILENT_TRUNCATION(有效窗口≈{oks[-1]['actual']})"
        print(f"  >> {m}: {verdict}")
        out[m] = {"probes": probes, "verdict": verdict}
    save("lms-stress", out)

# ---------- P5 quality ----------
def cmd_quality(a):
    bank = BANK[: a.limit] if a.limit else BANK
    out = {}
    for m in a.models:
        print(f"\n===== quality: {m} ({len(bank)} 题) =====")
        score, empties, detail = 0, 0, {}
        for qid, cat, prompt, grader in bank:
            text, attempt, used = "", 0, 0
            while attempt < 2:
                budget = a.np if attempt == 0 else a.np * 3
                try:
                    r = chat_stream(m, prompt, budget)
                except Exception as e:
                    text, used = f"[ERR {str(e)[:40]}]", 0; break
                text = (r["text"] or "").strip()
                used = r["completion_tokens"] or 0
                if text and grade(grader, text): break
                if text and used < budget * 0.9: break
                if not text: empties += 1; attempt += 1; continue
                attempt += 1
            ok = grade(grader, text)
            score += ok
            detail[qid] = {"pass": ok, "cat": cat, "tail": text.replace("\n", " ")[-100:]}
            print(f"  {qid}: {'PASS' if ok else 'FAIL'}{' (复测)' if attempt else '':6s} | ...{detail[qid]['tail'][:70]}")
        print(f"  >> {m}: {score}/{len(bank)} | 空响应 {empties}")
        out[m] = {"score": score, "total": len(bank), "empties": empties, "detail": detail}
    save("lms-quality", out)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("baseline"); p.add_argument("-m", "--models", nargs="+", required=True)
    p.add_argument("--runs", type=int, default=3); p.add_argument("--np", type=int, default=300)
    p.set_defaults(f=cmd_baseline)
    p = sub.add_parser("ladder"); p.add_argument("-m", "--models", nargs="+", required=True)
    p.add_argument("--ctxs", nargs="+", type=int, default=[2048, 8192, 32768])
    p.add_argument("--np", type=int, default=256); p.set_defaults(f=cmd_ladder)
    p = sub.add_parser("stress"); p.add_argument("-m", "--models", nargs="+", required=True)
    p.add_argument("--ctxs", nargs="+", type=int, default=[65536, 131072])
    p.add_argument("--rate", type=float, default=0, help="已实测 prefill 速率锚点(tok/s)，用于开跑前 ETA 外推")
    p.set_defaults(f=cmd_stress)
    p = sub.add_parser("quality"); p.add_argument("-m", "--models", nargs="+", required=True)
    p.add_argument("--np", type=int, default=256)
    p.add_argument("--limit", type=int, default=0); p.set_defaults(f=cmd_quality)
    a = ap.parse_args(); a.f(a)
