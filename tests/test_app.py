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
        return self.client.post("/driver-test/api/answer", json={"id": qid, "choice": choice})

    def test_pages(self):
        for path in ("/driver-test/", "/driver-test/stats", "/driver-test/static/img/q0001_1.png",
                     "/driver-test/static/practice.js", "/driver-test/static/style.css"):
            with self.client.get(path) as r:
                self.assertEqual(r.status_code, 200, path)

    def test_canonical_trailing_slash(self):
        # /driver-test 補上結尾斜線（和 nginx 同方向，不能反過來，否則會和 proxy 互相轉址）
        # Location 必須是相對路徑，不能帶 container 收到的 Host（經過 proxy 會是內部位址）
        with self.client.get("/driver-test", headers={"Host": "internal:8000"}) as r:
            self.assertEqual((r.status_code, r.headers["Location"]), (308, "/driver-test/"))
        with self.client.get("/driver-test/") as r:
            self.assertEqual(r.status_code, 200)

    def test_proxy_strips_prefix(self):
        # proxy_pass 帶結尾斜線時，/driver-test/xxx 進到 app 變成 /xxx，要對到同一個 route
        for stripped, full in (("/", "/driver-test/"), ("/stats", "/driver-test/stats"),
                               ("/static/style.css", "/driver-test/static/style.css"),
                               ("/static/img/q0001_1.png", "/driver-test/static/img/q0001_1.png")):
            with self.client.get(stripped) as a, self.client.get(full) as b:
                self.assertEqual((a.status_code, a.data), (b.status_code, b.data), stripped)
        d = self.client.get("/api/next?section=2").get_json()
        self.assertEqual(d["pool_size"], 230)
        with self.client.post("/api/answer", json={"id": 1, "choice": 2}) as r:
            self.assertEqual(r.status_code, 200)
        with self.client.get("/driver-test-stats") as r:
            self.assertEqual(r.status_code, 404)

    def test_page_links_use_prefix(self):
        for page in ("/driver-test/", "/driver-test/stats"):
            html = self.client.get(page).get_data(as_text=True)
            for ref in ('href="/driver-test/static/style.css"', 'href="/driver-test/"',
                        'href="/driver-test/stats"', 'const API_BASE = "/driver-test/api"',
                        'const IMG_BASE = "/driver-test/static/img/"'):
                self.assertIn(ref, html, page)

    def test_next_hides_answer(self):
        d = self.client.get("/driver-test/api/next").get_json()
        self.assertNotIn("answer", d["question"])
        self.assertEqual(d["pool_size"], 1090)
        self.assertEqual(d["stat"]["attempts"], 0)
        self.assertGreater(d["probability"], 0)

    def test_next_section_and_exclude(self):
        for _ in range(30):
            d = self.client.get("/driver-test/api/next?section=3").get_json()
            self.assertTrue(d["question"]["section"].startswith("架構三"))
            self.assertEqual(d["pool_size"], 436)
        d = self.client.get("/driver-test/api/next?section=all&exclude=5").get_json()
        self.assertNotEqual(d["question"]["id"], 5)
        self.assertEqual(self.client.get("/driver-test/api/next?section=9").status_code, 400)

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
        self.assertEqual(self.client.post("/driver-test/api/answer", data="x").status_code, 400)

    def test_stats_consistent(self):
        plays = [(1, True), (1, False), (2, True), (500, False), (700, True), (700, True)]
        for qid, ok in plays:
            a = self.mod.QUESTIONS[qid]["answer"]
            self.answer(qid, a if ok else a % 3 + 1)
        d = self.client.get("/driver-test/api/stats").get_json()
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
        d = mod.app.test_client().get("/driver-test/api/stats").get_json()
        self.assertEqual(d["overall"]["attempts"], 1)


if __name__ == "__main__":
    unittest.main()
