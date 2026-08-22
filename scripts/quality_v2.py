#!/usr/bin/env python3
"""
quality_v2.py -- 场景化质量评测（题库外置版）

题库是独立 JSON 文件（--bank 指定），本脚本只内置 6 题中性演示题库（仅验证链路，无选型意义）。
构建自己的题库：见 examples/question-bank-template.md；示例：examples/remote-sensing-researcher/bank.json

用法：
  python3 quality_v2.py ollama   -m 模型 --bank examples/remote-sensing-researcher/bank.json
  python3 quality_v2.py lmstudio -m 模型 --bank my-bank.json --np 512
  python3 quality_v2.py ollama   -m 模型 --bank ... --no-think   # thinking 模型关思考对照
  python3 quality_v2.py ollama   -m 模型 --bank ... --limit 8    # 只跑前 N 题(冒烟)

判分：100% 确定性（sub/re/and），temp=0；空响应自动 3x 预算复测。
结果写入 BENCH_DATA_DIR（或脚本仓库 bench_results/）。
"""
import argparse, datetime, json, math, os, re, sys, time
import urllib.request

# ---------- 中性演示题库（6 题，仅验证安装与链路） ----------
DEMO_BANK = {
    "name": "demo-neutral-6",
    "scenes": {"G": {"name": "通用底噪", "weight": 0.5}},
    "haystack": [],
    "needles": {},
    "questions": [
        {"id": "D1", "scene": "G", "prompt": "If all Bloops are Razzles and all Razzles are Lazzles, are all Bloops Lazzles? yes/no only.", "grader": {"mode": "sub", "target": "yes"}},
        {"id": "D2", "scene": "G", "prompt": "If today is Wednesday, what weekday is it 9 days from now? Day name only.", "grader": {"mode": "re", "target": r"\bFriday\b"}},
        {"id": "D3", "scene": "G", "prompt": "What is 15% of 240? Number only.", "grader": {"mode": "re", "target": r"(?<!\d)36(?!\d)"}},
        {"id": "D4", "scene": "G", "prompt": "What is the average of 12, 18, 24, 36? Decimal only.", "grader": {"mode": "sub", "target": "22.5"}},
        {"id": "D5", "scene": "G", "prompt": "Odd one out: dog, cat, elephant, car? Item only.", "grader": {"mode": "sub", "target": "car"}},
        {"id": "D6", "scene": "G", "prompt": "Largest planet in the Solar System? Name only.", "grader": {"mode": "re", "target": r"\bJupiter\b"}},
    ],
}

# ---------- 题库加载 ----------
def build_needle_doc(haystack_parts, needle_text, n_repeat=6):
    """拼接长文档并把 needle 插在正中（n_repeat 次循环 ≈ 数千 token）"""
    body = "".join(haystack_parts) * n_repeat
    mid = len(body) // 2
    return body[:mid] + needle_text + body[mid:]

def load_bank(path):
    """加载题库 JSON 并渲染 F 类 needle 题 → (bank, questions)
    questions 元素: {id, scene, prompt, grader(dict)}"""
    if path is None:
        return DEMO_BANK, DEMO_BANK["questions"]
    d = json.load(open(path, encoding="utf-8"))
    qs = []
    for q in d["questions"]:
        q = dict(q)
        if "needle" in q:  # F 类：运行时渲染长文档
            nd = d["needles"][q["needle"]]
            doc = build_needle_doc(d.get("haystack", []), nd["text"], q.get("repeat", 6))
            q["prompt"] = ("Read the following research notes and answer the question with ONLY "
                           "the key fact (few words), no explanation.\n\n" + doc +
                           "\n\nQuestion: " + q["question"])
        qs.append(q)
    return d, qs

# ---------- 引擎适配 ----------
def gen_answer(model, prompt, max_tokens, engine, timeout=900, no_think=False):
    if engine == "ollama":
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "stream": False, "options": {"num_predict": max_tokens, "temperature": 0}}
        if no_think:
            body["think"] = False   # thinking 模型关闭思考(定律七:分离能力与预算成本)
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        return (resp.get("message", {}).get("content") or "").strip(), resp.get("eval_count", 0)
    else:  # lmstudio (OpenAI 兼容流式)
        body = {"model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens, "temperature": 0, "stream": True,
                "stream_options": {"include_usage": True}}
        req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        parts = []; usage = {}
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: "): continue
                p = line[6:]
                if p == "[DONE]": break
                try: obj = json.loads(p)
                except Exception: continue
                if obj.get("usage"): usage = obj["usage"]
                ch = obj.get("choices") or []
                if ch and (ch[0].get("delta") or {}).get("content"):
                    parts.append(ch[0]["delta"]["content"])
        return "".join(parts).strip(), usage.get("completion_tokens", 0)

def grade(g, text):
    """判分器。模式: sub(子串) / re(正则) / and(全部满足)。
    ⚠️ 禁用 not/forbid 判解释型答案——解释会引用原错误形式，必误伤。"""
    t = text or ""
    mode = g["mode"]
    if mode == "sub":
        return g["target"].lower() in t.lower()
    if mode == "re":
        return re.search(g["target"], t, re.I) is not None
    if mode == "and":
        return all(grade(x, t) for x in g["targets"])
    if mode == "not":
        musts, forbid = g["must_any"], g["forbid"]
        return any(m.lower() in t.lower() for m in musts) and not any(f.lower() in t.lower() for f in forbid)
    return False

def wilson_ci(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))

# ---------- 主流程 ----------
def run(engine, models, bank_path, npred=384, no_think=False, limit=0):
    bank, questions = load_bank(bank_path)
    if limit:
        questions = questions[:limit]
    scenes = bank["scenes"]
    out = {}
    for m in models:
        tag = " [think:off]" if no_think else ""
        print(f"\n===== quality_v2{tag}: {m} | bank={bank.get('name', bank_path)} ({len(questions)} 题) =====", flush=True)
        by_scene = {}; details = {}; empty = 0
        t0 = time.time()
        for q_ in questions:
            text, used, attempt = "", 0, 0
            while attempt < 2:
                budget = npred if attempt == 0 else npred * 3
                try:
                    text, used = gen_answer(m, q_["prompt"], budget, engine, no_think=no_think)
                except Exception as e:
                    text, used = f"[ERR {str(e)[:40]}]", 0; break
                if text and grade(q_["grader"], text): break
                if text and used < budget * 0.9: break
                if not text: empty += 1; attempt += 1; continue
                attempt += 1
            ok = grade(q_["grader"], text)
            s = by_scene.setdefault(q_["scene"], [0, 0]); s[1] += 1; s[0] += ok
            details[q_["id"]] = {"pass": ok, "tail": (text or "").replace("\n", " ")[-90:]}
            print(f"  {q_['id']}: {'PASS' if ok else 'FAIL'} | ...{details[q_['id']]['tail'][:60]}", flush=True)
        total = sum(v[0] for v in by_scene.values()); n = sum(v[1] for v in by_scene.values())
        lo, hi = wilson_ci(total, n)
        # 加权分（场景权重来自题库声明）
        num = sum(scenes[s]["weight"] * v[0] for s, v in by_scene.items())
        den = sum(scenes[s]["weight"] * v[1] for s, v in by_scene.items())
        out[m] = {"bank": bank.get("name", bank_path), "total": f"{total}/{n}",
                  "weighted": round(num / den, 3) if den else 0,
                  "ci95": f"[{lo:.2f},{hi:.2f}]", "empty": empty,
                  "by_scene": {scenes[s]["name"]: f"{v[0]}/{v[1]}" for s, v in sorted(by_scene.items())},
                  "minutes": round((time.time() - t0) / 60, 1), "details": details}
        print(f"\n  >> {m}: {total}/{n} CI95=[{lo:.2f},{hi:.2f}] 加权{out[m]['weighted']} 空响应{empty} 用时{out[m]['minutes']}min")
    save(out, bank)
    report(out, scenes)

def save(out, bank):
    outdir = (os.environ.get("BENCH_DATA_DIR")
              or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bench_results"))
    os.makedirs(outdir, exist_ok=True)
    f = os.path.join(outdir, f"quality_v2-{bank.get('name', 'bank')}-{datetime.datetime.now():%Y%m%d-%H%M%S}.json")
    json.dump(out, open(f, "w"), ensure_ascii=False, indent=1)
    print(f"\n[saved] {f}")

def report(out, scenes):
    print("\n===== 场景得分对比 =====")
    w = " ".join(f"{v['name']}(w={v['weight']})" for _, v in sorted(scenes.items()))
    print(f"  场景: {w}")
    for m, r in out.items():
        cells = " ".join(f"{r['by_scene'].get(v['name'], '-'):>10s}" for _, v in sorted(scenes.items()))
        print(f"  {m:26s} {cells}  total {r['total']} 加权 {r['weighted']} {r['ci95']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=["ollama", "lmstudio"])
    ap.add_argument("-m", "--models", nargs="+", required=True)
    ap.add_argument("--bank", default=None, help="题库 JSON 路径；缺省用内置 6 题演示题库")
    ap.add_argument("--np", type=int, default=384)
    ap.add_argument("--no-think", action="store_true", help="Ollama thinking 模型关闭思考(能力上限对照)")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 题(冒烟)")
    a = ap.parse_args()
    run(a.engine, a.models, a.bank, a.np, a.no_think, a.limit)
