"""核心逻辑单元测试（无需任何推理引擎，CI 可跑）。
运行: python3 -m unittest discover -s tests -v"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import bench  # noqa: E402
import quality_v2 as qv  # noqa: E402


class TestGrader(unittest.TestCase):
    def test_sub_case_insensitive(self):
        self.assertTrue(qv.grade(("sub", "LoveDA"), "the images come from loveda dataset"))

    def test_sub_negative(self):
        self.assertFalse(qv.grade(("sub", "LoveDA"), "images come from BigEarthNet"))

    def test_numeric_boundary(self):
        # "36" 不得命中 "360"/"136"
        self.assertTrue(qv.grade(("re", r"(?<!\d)36(?!\d)"), "answer: 36"))
        self.assertFalse(qv.grade(("re", r"(?<!\d)36(?!\d)"), "answer: 360"))
        self.assertFalse(qv.grade(("re", r"(?<!\d)36(?!\d)"), "answer: 136"))

    def test_and_mode(self):
        g = ("and", [("sub", "remote sensing"), ("re", r"(?i)(visual|vision)")])
        self.assertTrue(qv.grade(g, "Remote Sensing Visual Question Answering"))
        self.assertFalse(qv.grade(g, "Visual Question Answering"))  # 缺 remote sensing

    def test_regex_allows_unicode_hyphen(self):
        # U+2011 连字符教训
        self.assertTrue(qv.grade(("re", r"(?i)near.{0,3}infrared"), "Near‑Infrared band"))

    def test_not_mode_forbidden_hits_explanation(self):
        # forbid 的误伤实证：解释型答案引用原错误
        g = ("not", (["results show"], ["shows"]))
        self.assertFalse(qv.grade(g, "Corrected: results show. (original wrongly used shows)"))


class TestBankIntegrity(unittest.TestCase):
    def test_bank_sizes(self):
        qv.init_prompts()
        from collections import Counter
        c = Counter(x[1] for x in qv.Q)
        self.assertEqual(sum(c.values()), 72)
        self.assertEqual(c["A"], 16); self.assertEqual(c["B"], 16)
        self.assertEqual(c["E"], 8); self.assertEqual(c["G"], 8)

    def test_f_questions_have_prompts(self):
        qv.init_prompts()
        for qid, scene, prompt, _ in qv.Q:
            if qid.startswith("F"):
                self.assertIsNotNone(prompt)
                self.assertIn("Question:", prompt)


class TestUtilities(unittest.TestCase):
    def test_build_prompt_length(self):
        p = bench.build_prompt(2048)
        self.assertGreater(len(p), 1000)

    def test_wilson_ci_bounds(self):
        lo, hi = qv.wilson_ci(8, 8)
        self.assertGreaterEqual(lo, 0); self.assertLessEqual(hi, 1)
        lo2, hi2 = qv.wilson_ci(0, 8)
        self.assertEqual(lo2, 0)            # 0 成功下界必为 0
        self.assertGreater(hi2, 0)          # Wilson 上界应大于 0（连续校正性质）

    def test_outdir_env_override(self):
        # 设置 BENCH_DATA_DIR 后重载模块，OUTDIR 应跟随环境变量
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
