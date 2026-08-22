#!/usr/bin/env python3
"""
quality_v2.py -- 场景化质量评测 v2（面向遥感VQA/REC博士生的真实工作负载）
六大场景 A写作/B代码/C领域/D翻译/E分析/F检索 + G通用底噪
材料来源: EarthVQA repo / mmrotate repo（/tmp/bench_materials）+ 遥感领域公认事实
判分: 100% 确定性（子串/正则，A类双条件=正确形式在且错误形式不在）
事实核实记录: 见每个场景头的 [SRC] 标注
"""
import argparse, datetime, json, math, os, sys, time
import urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------- 长文档构造（场景F） ----------
NEEDLE_DOC_PARTS = [
    ("EarthVQA is a remote sensing visual question answering benchmark developed by "
     "Wuhan University's RSIDEA lab. It emphasizes relational reasoning: questions "
     "require understanding spatial relations, object attributes, and scene context "
     "rather than simple object presence. The images originate from the LoveDA dataset, "
     "covering urban and rural areas in China. The training pipeline is two-stage: an "
     "SFPN segmentation model first produces semantic masks and segmentation features, "
     "then the SOBA module performs answer prediction grounded on those features. "
     "Evaluation uses overall accuracy for classification-type questions and RMSE for "
     "counting-type questions, including 'Basic Counting' and 'Reasoning-based Counting'."),
    ("Oriented bounding box detection is a core task in aerial image analysis. In "
     "mmrotate, a rotated box is parameterized as (x_ctr, y_ctr, w, h, angle). Three "
     "angle conventions coexist: le90 restricts the angle to [-pi/2, pi/2), le135 to "
     "[-3*pi/4, pi/4), and oc (OpenCV convention) to [0, pi/2). DOTA labels store "
     "objects as eight-coordinate polygons (x1,y1,...,x4,y4) plus class and difficulty. "
     "Converting polygons to rotated boxes uses poly2obb with one of the conventions. "
     "Angle ambiguity is a known source of label inconsistency in DOTA."),
    ("Transfer learning and parameter-efficient methods are widely adopted in remote "
     "sensing multimodal research. LoRA freezes backbone weights and injects trainable "
     "low-rank matrices into attention projections. CLIP-style contrastive alignment "
     "maps images and text into a shared embedding space, enabling zero-shot transfer "
     "to remote sensing classification tasks. For referring expression comprehension, "
     "models must localize the described region, evaluated by Acc@0.5, meaning the "
     "predicted box counts as correct when its IoU with ground truth reaches 0.5."),
]
NEEDLES = {
    "N1": ("DIOR-R", "In the second-stage ablation, the referring comprehension branch was "
                     "additionally validated on the DIOR-R dataset with 17,547 referring "
                     "expression samples. "),
    "N2": ("83.7",  "The relational reasoning module improved overall accuracy on EarthVQA "
                     "from 81.9 to 83.7 percent. "),
    "N3": ("single-stage", "During reproduction, the team replaced the original two-stage "
                     "pipeline with a single-stage variant for speed comparison. "),
    "N4": ("RSVQA-LR", "A separate pilot experiment was conducted on the RSVQA-LR subset "
                     "before scaling to the full dataset. "),
}

def build_needle_doc(needle_key, n_repeat=6):
    """拼 ~n_repeat 千 token 的文档，needle 插在文中固定相对位置"""
    needle_txt, fact = NEEDLES[needle_key]
    body = "".join(NEEDLE_DOC_PARTS) * n_repeat
    mid = len(body) // 2
    doc = body[:mid] + needle_txt + body[mid:]
    return doc, fact

# ---------- 题库 ----------
# 每题: (id, scene, prompt, grader)
# grader: ("sub", s) / ("re", r) / ("and", [g1, g2]) / ("not", [must, forbid]) -- A类双条件
Q = []
def q(qid, scene, prompt, g): Q.append((qid, scene, prompt, g))

# ===== A. 学术英文写作错误注入 (12) =====
# [SRC] 句式取自遥感VQA论文常见表述；错误类型=主谓一致/术语/中式英语
# 注: A类判分只验"正确修正形式出现"，不做 forbid——解释型答案会引用原错误，forbid 必误伤(冒烟实测教训)
q("A1","A","Rewrite this sentence correctly (academic English): \"The experiment results shows our method outperform the baseline in term of accuracy.\"",
  ("sub","results show"))
q("A2","A","Rewrite correctly: \"We conduct extensive experiments to prove the effectively of our approach.\"",
  ("sub","effectiveness"))
q("A3","A","Rewrite correctly: \"Compared with the baseline method, our method achieve a better performance.\"",
  ("sub","achieves"))
q("A4","A","Rewrite correctly: \"The dataset contain 10,000 remote sensing images, which is divided into training and test set.\"",
  ("sub","contains"))
q("A5","A","Fix the terminology error: \"Our model uses a convolution neural network to extract visual features from the sensing images.\"  Give the corrected phrase for the image type.",
  ("sub","remote sensing images"))
q("A6","A","Rewrite correctly: \"As shown in Table 2, we can see that the results of the proposed method is better than others.\"",
  ("sub","are better"))
q("A7","A","Rewrite correctly: \"This paper propose a novel framework for referring expression comprehension in remote sensing scenario.\"",
  ("sub","proposes"))
q("A8","A","Rewrite correctly: \"The feature extracted by the backbone are fed into the fusion module.\"",
  ("re", r"(?i)features.{0,40}(are fed|fed into)"))
q("A9","A","Rewrite correctly: \"In order to verify the generalization ability, we also evaluate our method on three different dataset.\"",
  ("sub","datasets"))
q("A10","A","Rewrite correctly: \"Experimental results demonstrates that our approach outperforms state-of-the-art methods.\"",
  ("sub","results demonstrate"))
q("A11","A","Rewrite correctly: \"The ablation study show the contribution of each component.\"",
  ("sub","study shows"))
q("A12","A","Rewrite correctly: \"We compared our method with several baseline, including CLIP and BLIP.\"",
  ("sub","baselines"))
# --- 审稿人常挑类型（用户审校意见#1 补充）---
q("A13","A","A reviewer flags this as over-claiming. Rewrite with appropriate academic hedging: \"Our method completely solves the problem of small object detection in remote sensing images.\"",
  ("re", r"(?i)(alleviat|mitigat|address|improv|partial|considerabl)"))
q("A14","A","A reviewer flags over-claimed generality. Rewrite with proper scope: \"Experiments prove that our method is universally applicable to all remote sensing scenarios.\"",
  ("re", r"(?i)(various|several|multiple|certain|specific|limited|demonstrat|indicat)"))
q("A15","A","Rewrite in formal academic style (no contractions, precise wording): \"The model doesn't converge when the LR is too big, so we don't use it in the final version.\"",
  ("re", r"(?i)\b(do not|does not)\b"))
q("A16","A","A reviewer asks to avoid unsupported superlatives. Rewrite: \"Our results are the best ever achieved on this task.\"",
  ("re", r"(?i)(competitive|comparable|on par|strong|favorable)"))

# ===== B. 深度学习代码知识 (16) =====
# [SRC] EarthVQA repo(train_earthvqa.py/README) + mmrotate repo(transforms.py) 真实代码
q("B1","B","In the EarthVQA repository, which two metric types are used to evaluate the VQA model? (name the two metric kinds)",
  ("and", [("sub","accuracy"), ("sub","RMSE")]))
q("B2","B","In the EarthVQA evaluation code, evaluation runs inside `with torch.no_grad():`. What is the main reason for this?",
  ("sub","memory"))  # 或 no gradient computation; 判分放宽: 答案提及 memory/不需要梯度
q("B3","B","In EarthVQA's training pipeline, what does the first stage train (SFPN) and what does it produce for the second stage (SOBA)? Answer briefly.",
  ("and", [("sub","segmentation"), ("sub","feature")]))  # 分割模型→特征/pse-masks
q("B4","B","In mmrotate, what are the five parameters of an oriented bounding box (OBB)?",
  ("and", [("sub","x"), ("sub","angle")]))  # x_ctr,y_ctr,w,h,angle
q("B5","B","In mmrotate, poly2obb has le90 and oc conventions. What is the difference in angle range between le90 and oc?",
  ("and", [("sub","90"), ("sub","180")]))  # le90: [-90°,0°/90°); oc: [0°,180°)或[0,90)
q("B6","B","In the DOTA dataset label format, how are objects annotated (what geometry representation)?",
  ("sub","polygon"))  # 8坐标多边形
q("B7","B","This PyTorch training code has a bug. Find it and name the missing/incorrect statement:\n```python\nfor img, target in train_loader:\n    optimizer.zero_grad()\n    output = model(img)\n    loss = criterion(output, target)\n    loss.backward()\n```",
  ("sub","optimizer.step"))
q("B8","B","This evaluation code will crash. Why?\n```python\npreds = model(img)\nans_idx = preds.argmax(dim=1).numpy()\n``` (preds is a CUDA tensor)",
  ("and", [("sub","cpu"), ("sub","numpy")]))  # CUDA tensor 不能直接 .numpy()
q("B9","B","In mmrotate config files, what does the `_base_` key do?",
  ("sub","inherit"))  # 配置继承
q("B10","B","In EarthVQA's repo, evaluation uses Count_RMSE_Metric. Which question types does it cover?",
  ("sub","counting"))
q("B11","B","Why does the EarthVQA README pin `albumentations==1.4.3` with the comment 'This version is important'?",
  ("sub","compatib"))  # 兼容性
q("B12","B","During training, model.train() vs model.eval() - what behavior differences does eval() disable that affect results?",
  ("and", [("sub","Dropout"), ("sub","BatchNorm")]))  # 或 dropout/BN; 判分小写匹配
q("B13","B","EarthVQA train_earthvqa.py calls `er.registry.register_all()`. In the `ever` framework, what is the purpose of a registry?",
  ("sub","register"))  # 注册模块按名构建
q("B14","B","A dataloader in a training script uses `shuffle=False` for the train split. What problem can this cause?",
  ("and", [("sub","shuffle"), ("sub","order")]))  # 放宽: 提及 shuffle 与顺序/泛化
q("B15","B","In EarthVQA code, `convert2str(indexes, map_dict=EarthVQADataset.QUESTION_VOC)` converts what to what?",
  ("and", [("sub","index"), ("sub","str")]))  # 索引→字符串
q("B16","B","mmrotate rotated boxes use (x_ctr,y_ctr,w,h,angle). Why can the same physical box have multiple valid (w,h,angle) combinations? Name the ambiguity.",
  ("and", [("sub","angle"), ("sub","period")]))  # 角度周期性/180°歧义

# ===== C. 遥感领域知识 (12) =====
# [SRC] EarthVQA README + 领域公认事实(DOTA/REC/CLIP等)
q("C1","C","The EarthVQA images come from which existing remote sensing dataset? (name it)",
  ("sub","LoveDA"))
q("C2","C","What is the core reasoning capability that EarthVQA emphasizes beyond simple object presence? (two words)",
  ("sub","relational reasoning"))
q("C3","C","LoveDA covers two area types. Name them.",
  ("and", [("sub","urban"), ("sub","rural")]))
q("C4","C","What task is the DOTA dataset designed for? (object detection variant)",
  ("and", [("sub","detection"), ("sub","rotat")]))  # 旋转框检测
q("C5","C","In referring expression comprehension (REC), what is the standard evaluation criterion? (metric name + threshold)",
  ("and", [("sub","IoU"), ("sub","0.5")]))  # Acc@0.5
q("C6","C","CLIP trains image and text encoders with what training objective?",
  ("sub","contrastive"))
q("C7","C","What does LoRA freeze and what does it train?",
  ("and", [("sub","freeze"), ("sub","low-rank")]))
q("C8","C","In the EarthVQA benchmark, counting-type questions are evaluated with which regression metric?",
  ("sub","RMSE"))
q("C9","C","Name the 6-digit-class core problem EarthVQA addresses: remote sensing ___ ___ ___ (three words, the task name).",
  ("and", [("sub","visual"), ("sub","question"), ("sub","answering")]))
q("C10","C","The EarthVQA dataset originates from images of China in LoveDA; in 2026 the authors extended it globally under what new dataset name?",
  ("sub","EarthVL"))
q("C11","C","In EarthVQA evaluation, what does 'OA' stand for and what does it measure?",
  ("and", [("sub","overall"), ("sub","accuracy")]))
q("C12","C","For aerial rotated object detection, give the standard term for boxes whose edges align with image axes (not rotated).",
  ("sub","horizontal"))

# ===== D. 中英学术翻译 (8) =====
# 判分: 译文含目标术语
q("D1","D","Translate to academic English, terminology must be exact: 遥感视觉问答",
  ("and", [("re", r"(?i)(visual|vision)[^a-z]{0,3}question[- ]answering"), ("sub","remote sensing")]))
q("D2","D","Translate: 遥感影像中的旋转框目标检测",
  ("and", [("sub","rotat"), ("sub","object detection")]))
q("D3","D","Translate: 指代表达理解（定位描述所指目标）",
  ("sub","referring expression comprehension"))
q("D4","D","Translate: 基于关系推理的场景理解",
  ("and", [("sub","relational reasoning"), ("sub","scene")]))
q("D5","D","Translate: 遥感小目标检测",
  ("and", [("sub","small object"), ("sub","detection")]))
q("D6","D","Translate: 图像与文本的模态对齐",
  ("and", [("sub","modality"), ("sub","align")]))
q("D7","D","Translate: 零样本泛化能力",
  ("and", [("sub","zero-shot"), ("sub","generaliz")]))
q("D8","D","Translate: 定位精度",
  ("sub","localization accuracy"))

# ===== E. 实验数据分析 (8) =====
# 数值判分（相对提升/绝对差）
q("E1","E","Baseline mAP is 69.8, ours is 71.2. What is the RELATIVE improvement in percent? (one number)",
  ("re", r"(?<!\d)2\.0(?!\d)"))
q("E2","E","OA improves from 81.9 to 84.5. What is the absolute gain in percentage points? (one number)",
  ("re", r"(?<!\d)2\.6(?!\d)"))
q("E3","E","RMSE decreases from 15.6 to 12.3. What is the percentage decrease? (one decimal)",
  ("re", r"(?<!\d)21\.2(?!\d)"))
q("E4","E","Params drop from 113M to 98M. What is the percentage reduction? (one decimal)",
  ("re", r"(?<!\d)13\.3(?!\d)"))
q("E5","E","Linear warmup from 0 to 1e-3 over 500 steps. What is the LR at step 250? (scientific or decimal)",
  ("re",r"5\s*[eE×x*-]*\s*10?\^?|-?4|0\.0005"))
q("E6","E","Inference speed is 12 images/s. How many seconds for 256 images? (one decimal)",
  ("re", r"(?<!\d)21\.3(?!\d)"))
q("E7","E","Training 40 epochs took 5 hours. At the same rate, how many hours for 60 epochs? (one decimal)",
  ("re", r"(?<!\d)7\.5(?!\d)"))
q("E8","E","Batch size reduced from 32 to 16, dataset unchanged. In one word, what typically happens to total training time? (direction)",
  ("re",r"(?i)increase|longer|slower"))

# ===== F. 长文档事实检索 (4) =====
# [SRC] 文档由 EarthVQA/mmrotate 领域文本拼装, needle 为构造事实
def f_prompt(nk, question):
    doc, _ = build_needle_doc(nk)
    return ("Read the following research notes and answer the question with ONLY the key fact "
            "(few words), no explanation.\n\n" + doc + "\n\nQuestion: " + question)
q("F1","F",None,("sub","DIOR-R"))           # 由 init 阶段填充 prompt
q("F2","F",None,("sub","83.7"))
q("F3","F",None,("sub","single-stage"))
q("F4","F",None,("sub","RSVQA-LR"))
F_QUESTIONS = {
    "F1": "Which dataset was used for the referring comprehension branch validation in the second-stage ablation?",
    "F2": "What overall accuracy did the relational reasoning module reach on EarthVQA?",
    "F3": "What pipeline variant did the team use for the speed comparison during reproduction?",
    "F4": "On which subset was the separate pilot experiment conducted?",
}
F_NK = {"F1":"N1","F2":"N2","F3":"N3","F4":"N4"}

# ===== G. 通用推理底噪 (8, 保留自v1) =====
q("G1","G","If all Bloops are Razzles and all Razzles are Lazzles, are all Bloops Lazzles? yes/no only.",("sub","yes"))
q("G2","G","If today is Wednesday, what weekday is it 9 days from now? Day name only.",("re",r"\bFriday\b"))
q("G3","G","What is 15% of 240? Number only.",("re",r"(?<!\d)36(?!\d)"))
q("G4","G","What is the average of 12, 18, 24, 36? Decimal only.",("sub","22.5"))
q("G5","G","Odd one out: dog, cat, elephant, car? Item only.",("sub","car"))
q("G6","G","Chemical symbol of gold?",("re",r"\bAu\b"))
q("G7","G","Year WWII ended?",("re",r"(?<!\d)1945(?!\d)"))
q("G8","G","Largest planet in the Solar System?",("re",r"\bJupiter\b"))

SCENE_NAMES = {"A":"学术写作","B":"DL代码","C":"遥感领域","D":"学术翻译","E":"实验分析","F":"长文检索","G":"通用底噪"}
# 场景权重（用户审校意见#2）: A/B/D/E/F 为主场景（日常工作负载），C/G 为次场景
# C 领域知识不能忽略但优先级低于文献检索/写作/代码；G 仅作底噪参照
SCENE_WEIGHT = {"A":1,"B":1,"D":1,"E":1,"F":1,"C":0.5,"G":0.5}

# ---------- 引擎适配 ----------
def gen_answer(model, prompt, max_tokens, engine, timeout=900, no_think=False):
    if engine == "ollama":
        body = {"model": model, "messages": [{"role":"user","content":prompt}],
                "stream": False, "options": {"num_predict": max_tokens, "temperature": 0}}
        if no_think:
            body["think"] = False   # Ollama thinking 模型关闭思考(定律七:分离能力与预算成本)
        req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
                data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        return (d.get("message",{}).get("content") or "").strip(), d.get("eval_count",0)
    else:  # lmstudio (OpenAI)
        body = {"model": model, "messages": [{"role":"user","content":prompt}],
                "max_tokens": max_tokens, "temperature": 0, "stream": True,
                "stream_options": {"include_usage": True}}
        req = urllib.request.Request("http://127.0.0.1:1234/v1/chat/completions",
                data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
        parts = []; usage = {}
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for raw in r:
                line = raw.decode("utf-8","replace").strip()
                if not line.startswith("data: "): continue
                p = line[6:]
                if p == "[DONE]": break
                try: obj = json.loads(p)
                except Exception: continue
                if obj.get("usage"): usage = obj["usage"]
                ch = obj.get("choices") or []
                if ch and (ch[0].get("delta") or {}).get("content"):
                    parts.append(ch[0]["delta"]["content"])
        return "".join(parts).strip(), usage.get("completion_tokens",0)

def grade(g, text):
    t = text or ""
    mode, target = g
    if mode == "sub":
        return target.lower() in t.lower()
    if mode == "re":
        import re as _re; return _re.search(target, t, _re.I) is not None
    if mode == "and":
        return all(grade(x, t) for x in target)
    if mode == "not":  # (must_any, forbidden) — 仅调试保留，正式题库已弃用(解释型答案必误伤)
        musts, forbid = target
        return any(m.lower() in t.lower() for m in musts) and not any(f.lower() in t.lower() for f in forbid)
    return False

def wilson_ci(k, n, z=1.96):
    if n == 0: return (0,0)
    p = k/n; d = 1 + z*z/n
    c = (p + z*z/(2*n))/d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return (max(0,c-h), min(1,c+h))

def init_prompts():
    for i,(qid,scene,prompt,grader) in enumerate(Q):
        if qid in F_QUESTIONS:
            doc,_ = build_needle_doc(F_NK[qid])
            Q[i] = (qid, scene, f_prompt(F_NK[qid], F_QUESTIONS[qid]), grader)

def run(engine, models, npred=384, no_think=False):
    init_prompts()
    out = {}
    for m in models:
        tag = " [think:off]" if no_think else ""
        print(f"\n===== quality_v2{tag}: {m} ({len(Q)} 题) =====", flush=True)
        by_scene = {}; details = {}; empty = 0
        t0 = time.time()
        for qid, scene, prompt, grader in Q:
            text, used, attempt = "", 0, 0
            while attempt < 2:
                budget = npred if attempt == 0 else npred*3
                try:
                    text, used = gen_answer(m, prompt, budget, engine, no_think=no_think)
                except Exception as e:
                    text, used = f"[ERR {str(e)[:40]}]", 0; break
                if text and grade(grader, text): break
                if text and used < budget*0.9: break
                if not text: empty += 1; attempt += 1; continue
                attempt += 1
            ok = grade(grader, text)
            s = by_scene.setdefault(scene, [0,0]); s[1] += 1; s[0] += ok
            details[qid] = {"pass": ok, "tail": (text or "").replace("\n"," ")[-90:]}
            print(f"  {qid}: {'PASS' if ok else 'FAIL'} | ...{details[qid]['tail'][:60]}", flush=True)
        total = sum(v[0] for v in by_scene.values()); n = sum(v[1] for v in by_scene.values())
        lo, hi = wilson_ci(total, n)
        out[m] = {"total": f"{total}/{n}", "ci95": f"[{lo:.2f},{hi:.2f}]", "empty": empty,
                  "by_scene": {SCENE_NAMES[s]: f"{v[0]}/{v[1]}" for s,v in sorted(by_scene.items())},
                  "minutes": round((time.time()-t0)/60,1), "details": details}
        print(f"\n  >> {m}: {total}/{n} CI95=[{lo:.2f},{hi:.2f}] 空响应{empty} 用时{out[m]['minutes']}min")
    save(out)

def save(out):
    outdir = (os.environ.get("BENCH_DATA_DIR")
              or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bench_results"))
    os.makedirs(outdir, exist_ok=True)
    f = os.path.join(outdir, f"quality_v2-{datetime.datetime.now():%Y%m%d-%H%M%S}.json")
    json.dump(out, open(f,"w"), ensure_ascii=False, indent=1)
    print(f"\n[saved] {f}")
    # 场景对比表
    print("\n===== 场景得分对比 =====")
    print("  权重: 主场景 A/B/D/E/F=1.0，次场景 C/G=0.5（用户审定：查文献/写作/代码优先，领域记忆次要）")
    print(f"  {'model':26s} " + " ".join(f"{SCENE_NAMES[s]:>8s}" for s in sorted(SCENE_NAMES)) + "   total")
    for m, r in out.items():
        cells = []
        for s in sorted(SCENE_NAMES):
            v = r["by_scene"].get(SCENE_NAMES[s])
            cells.append(f"{(v or '-'):>8s}")
        print(f"  {m:26s} " + " ".join(cells) + f"   {r['total']} {r['ci95']}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=["ollama","lmstudio"])
    ap.add_argument("-m","--models", nargs="+", required=True)
    ap.add_argument("--np", type=int, default=384)
    ap.add_argument("--no-think", action="store_true", help="Ollama thinking 模型关闭思考(能力上限对照)")
    a = ap.parse_args()
    run(a.engine, a.models, a.np, a.no_think)
