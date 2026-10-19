"""API 測試（Flask test client，作答紀錄寫到暫存目錄）。

    python -m unittest discover -s tests
"""
import importlib
import os
import tempfile
import unittest
from pathlib import Path


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["PROGRESS_DB"] = str(Path(self.tmp.name) / "progress.db")
        import app as app_module
        self.mod = importlib.reload(app_module)
        self.client = self.mod.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def answer(self, qid, choice):
        return self.client.post("/api/answer", json={"id": qid, "choice": choice})

    def test_pages(self):
        for path in ("/", "/stats", "/static/img/q0001_1.png", "/static/practice.js"):
            with self.client.get(path) as r:
                self.assertEqual(r.status_code, 200, path)

    def test_next_hides_answer(self):
        d = self.client.get("/api/next").get_json()
        self.assertNotIn("answer", d["question"])
        self.assertEqual(d["pool_size"], 1090)
        self.assertEqual(d["stat"]["attempts"], 0)
        self.assertGreater(d["probability"], 0)

    def test_next_section_and_exclude(self):
        for _ in range(30):
            d = self.client.get("/api/next?section=3").get_json()
            self.assertTrue(d["question"]["section"].startswith("架構三"))
            self.assertEqual(d["pool_size"], 436)
        d = self.client.get("/api/next?section=all&exclude=5").get_json()
        self.assertNotEqual(d["question"]["id"], 5)
        self.assertEqual(self.client.get("/api/next?section=9").status_code, 400)

    def test_answer_updates_stats(self):
        q = self.mod.QUESTIONS[523]          # 圖片選項題，答案 (3)
        wrong = 1 if q["answer"] != 1 else 2
        r = self.answer(523, q["answer"]).get_json()
        self.assertEqual(r, {"correct": True, "answer": 3, "stat": r["stat"]})
        self.assertEqual((r["stat"]["attempts"], r["stat"]["correct"], r["stat"]["streak"]), (1, 1, 1))
        r = self.answer(523, q["answer"]).get_json()
        self.assertEqual((r["stat"]["attempts"], r["stat"]["correct"], r["stat"]["streak"]), (2, 2, 2))
        r = self.answer(523, wrong).get_json()
        self.assertFalse(r["correct"])
        self.assertEqual((r["stat"]["attempts"], r["stat"]["correct"], r["stat"]["streak"]), (3, 2, 0))
        self.assertAlmostEqual(r["stat"]["accuracy"], 0.6667, places=4)

    def test_answer_validation(self):
        self.assertEqual(self.answer(0, 1).status_code, 400)
        self.assertEqual(self.answer(1091, 1).status_code, 400)
        self.assertEqual(self.answer(1, 4).status_code, 400)
        self.assertEqual(self.answer(1, "1").status_code, 400)
        self.assertEqual(self.client.post("/api/answer", data="x").status_code, 400)

    def test_stats_consistent(self):
        plays = [(1, True), (1, False), (2, True), (500, False), (700, True), (700, True)]
        for qid, ok in plays:
            a = self.mod.QUESTIONS[qid]["answer"]
            self.answer(qid, a if ok else a % 3 + 1)
        d = self.client.get("/api/stats").get_json()
        o = d["overall"]
        self.assertEqual((o["questions"], o["practiced"], o["attempts"], o["correct"]), (1090, 4, 6, 4))
        rows = {r["id"]: r for r in d["rows"]}
        self.assertEqual(len(rows), 1090)
        self.assertEqual((rows[1]["attempts"], rows[1]["correct"], rows[1]["streak"]), (2, 1, 0))
        self.assertEqual(sum(r["attempts"] for r in rows.values()), o["attempts"])
        self.assertEqual(sum(s["attempts"] for s in d["sections"]), o["attempts"])
        self.assertEqual([s["questions"] for s in d["sections"]], [424, 230, 436])
        self.assertEqual([s["practiced"] for s in d["sections"]], [2, 1, 1])
        self.assertAlmostEqual(sum(r["probability"] for r in rows.values()), 1.0, places=6)
        # 最近練過的題目在冷卻中，機率為 0
        self.assertEqual(rows[700]["probability"], 0)

    def test_persists_across_restart(self):
        self.answer(10, self.mod.QUESTIONS[10]["answer"])
        import app as app_module
        mod = importlib.reload(app_module)
        d = mod.app.test_client().get("/api/stats").get_json()
        self.assertEqual(d["overall"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
