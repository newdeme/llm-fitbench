"""核心逻辑单元测试（无需任何推理引擎，CI 可跑）。
运行: python3 -m unittest discover -s tests -v"""
import json, os, sys, unittest

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import bench  # noqa: E402
import quality_v2 as qv  # noqa: E402

RS_BANK = os.path.join(REPO, "examples", "remote-sensing-researcher", "bank.json")


class TestGrader(unittest.TestCase):
    def test_sub_case_insensitive(self):
        self.assertTrue(qv.grade({"mode": "sub", "target": "LoveDA"}, "images from loveda"))

    def test_numeric_boundary(self):
        g = {"mode": "re", "target": r"(?<!\d)36(?!\d)"}
        self.assertTrue(qv.grade(g, "answer: 36"))
        self.assertFalse(qv.grade(g, "answer: 360"))
        self.assertFalse(qv.grade(g, "answer: 136"))

    def test_and_mode_recursive(self):
        g = {"mode": "and", "targets": [
            {"mode": "sub", "target": "remote sensing"},
            {"mode": "re", "target": r"(?i)(visual|vision)"}]}
        self.assertTrue(qv.grade(g, "Remote Sensing Visual QA"))
        self.assertFalse(qv.grade(g, "Visual QA"))

    def test_regex_allows_unicode_hyphen(self):
        self.assertTrue(qv.grade({"mode": "re", "target": r"(?i)near.{0,3}infrared"}, "Near‑Infrared band"))


class TestBanks(unittest.TestCase):
    def test_demo_bank_builtin(self):
        bank, qs = qv.load_bank(None)
        self.assertEqual(len(qs), 6)
        self.assertEqual(bank["name"], "demo-neutral-6")

    def test_rs_bank_json_integrity(self):
        """示例题库必须是独立 JSON（不再内嵌于脚本）；B8 起 F 扩到 8 题、共 76 题"""
        self.assertTrue(os.path.exists(RS_BANK), "bank.json 不存在")
        bank, qs = qv.load_bank(RS_BANK)
        from collections import Counter
        c = Counter(q["scene"] for q in qs)
        self.assertEqual(len(qs), 76)
        self.assertEqual(c["A"], 16); self.assertEqual(c["B"], 16)
        self.assertEqual(c["C"], 12); self.assertEqual(c["D"], 8)
        self.assertEqual(c["E"], 8); self.assertEqual(c["F"], 8); self.assertEqual(c["G"], 8)
        self.assertEqual(bank["name"], "remote-sensing-researcher-76")

    def test_rs_bank_needle_rendering(self):
        bank, qs = qv.load_bank(RS_BANK)
        f1 = [q for q in qs if q["id"] == "F1"][0]
        self.assertIn("DIOR-R", f1["prompt"])
        self.assertGreater(len(f1["prompt"]), 8000)  # 长文档已渲染

    def test_rs_bank_needle_position(self):
        """B8 位置维度：F5(pos=0.15) needle 应在文档前段，F8(pos=0.85) 在后段；
        并验证插入的是完整事实句（B8 修复：旧版裸插关键词粘在接缝）"""
        bank, qs = qv.load_bank(RS_BANK)
        for qid, pos, frag in (("F5", 0.15, "codename AURORA"), ("F8", 0.85, "recorded 47 milliseconds")):
            q = [x for x in qs if x["id"] == qid][0]
            doc = q["prompt"]
            idx = doc.find(frag)
            self.assertGreater(idx, 0, f"{qid} needle 事实句未渲染")
            frac = idx / len(doc)
            self.assertLess(abs(frac - pos), 0.1, f"{qid} needle 位置 {frac:.2f} 偏离声明 {pos}")
        f1 = [x for x in qs if x["id"] == "F1"][0]["prompt"]
        self.assertIn("additionally validated on the DIOR-R dataset", f1)

    def test_script_has_no_private_bank(self):
        """脚本本体不得内嵌私人题库（题库外置原则）"""
        src = open(os.path.join(REPO, "scripts", "quality_v2.py"), encoding="utf-8").read()
        self.assertNotIn("LoveDA", src)
        self.assertNotIn("referring expression comprehension in remote sensing", src)

    def test_limit_smoke_selection(self):
        bank, qs = qv.load_bank(RS_BANK)
        # limit 由 run() 处理，这里验证题目列表可切片
        self.assertEqual(len(qs[:8]), 8)


class TestUtilities(unittest.TestCase):
    def test_build_prompt_length(self):
        self.assertGreater(len(bench.build_prompt(2048)), 1000)

    def test_wilson_ci_bounds(self):
        lo, hi = qv.wilson_ci(8, 8)
        self.assertGreaterEqual(lo, 0); self.assertLessEqual(hi, 1)
        lo2, hi2 = qv.wilson_ci(0, 8)
        self.assertEqual(lo2, 0)
        self.assertGreater(hi2, 0)

    def test_outdir_env_override(self):
        import importlib
        os.environ["BENCH_DATA_DIR"] = "/tmp/bench-data-test"
        try:
            importlib.reload(bench)
            self.assertEqual(bench.OUTDIR, "/tmp/bench-data-test")
        finally:
            del os.environ["BENCH_DATA_DIR"]
            importlib.reload(bench)


if __name__ == "__main__":
    unittest.main()
