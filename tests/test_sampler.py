"""抽題演算法模擬：用真的 Store（暫存 SQLite）模擬長時間練習。

    python -m unittest discover -s tests
"""
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import sampler
from store import Store

BASE = Path(__file__).resolve().parent.parent
with open(BASE / "data" / "questions.json", encoding="utf-8") as f:
    QUESTIONS = json.load(f)
ALL_IDS = [q["id"] for q in QUESTIONS]


def simulate(n, ids, always_wrong=(), p_correct=0.8, seed=1):
    """模擬作答 n 次，回傳 (抽到順序, 每 100 次的覆蓋數)。"""
    rng = random.Random(seed)
    tmp = tempfile.TemporaryDirectory()
    store = Store(Path(tmp.name) / "p.db")
    drawn, coverage, seen = [], [], set()
    for i in range(n):
        qid, _ = sampler.pick(ids, store.all_stats(), store.seq(), rng=rng)
        ok = qid not in always_wrong and rng.random() < p_correct
        store.record(qid, 1, ok)
        drawn.append(qid)
        seen.add(qid)
        if (i + 1) % 100 == 0:
            coverage.append(len(seen))
    tmp.cleanup()
    return drawn, coverage


class SamplerSimulation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(42)
        cls.weak = set(rng.sample(ALL_IDS, 50))
        cls.drawn, cls.coverage = simulate(3000, ALL_IDS, always_wrong=cls.weak)
        print(f"\n[模擬] 每 100 次的覆蓋題數：{cls.coverage}")

    def test_coverage_grows(self):
        # 覆蓋率單調上升；1100 次時至少 75%（均勻隨機抽約 63%，這裡同時還要重練答錯的題目）；
        # 3000 次時全部練過
        self.assertEqual(self.coverage, sorted(self.coverage))
        self.assertGreaterEqual(self.coverage[10], 0.75 * len(ALL_IDS))
        self.assertEqual(self.coverage[-1], len(ALL_IDS))

    def test_weak_questions_drawn_more(self):
        c = Counter(self.drawn)
        weak_avg = sum(c[q] for q in self.weak) / len(self.weak)
        other_avg = sum(c[q] for q in ALL_IDS if q not in self.weak) / (len(ALL_IDS) - len(self.weak))
        print(f"[模擬] 一定答錯的題目平均被抽 {weak_avg:.2f} 次，其他題 {other_avg:.2f} 次")
        self.assertGreater(weak_avg, 1.5 * other_avg)

    def test_cooldown(self):
        last = {}
        for i, q in enumerate(self.drawn):
            if q in last:
                self.assertGreaterEqual(i - last[q], sampler.COOLDOWN, f"Q{q} 在 {i - last[q]} 次內重複")
            last[q] = i

    def test_section_scope(self):
        sec2 = [q["id"] for q in QUESTIONS if q["section"].startswith("架構二")]
        drawn, _ = simulate(300, sec2, seed=3)
        self.assertTrue(set(drawn) <= set(sec2))

    def test_small_pool_does_not_stall(self):
        # 題目池比冷卻次數還小時，仍要能一直抽下去
        drawn, _ = simulate(30, [1, 2, 3], seed=5)
        self.assertEqual(len(drawn), 30)


class WeightFormula(unittest.TestCase):
    def test_unseen_weight_grows_with_practice(self):
        self.assertGreater(sampler.weight(None, 500), sampler.weight(None, 0))

    def test_wrong_beats_right(self):
        right = {"attempts": 3, "correct": 3, "last_seq": 0}
        wrong = {"attempts": 3, "correct": 0, "last_seq": 0}
        self.assertGreater(sampler.weight(wrong, 100), sampler.weight(right, 100))

    def test_mastered_never_zero(self):
        mastered = {"attempts": 50, "correct": 50, "last_seq": 0}
        self.assertGreater(sampler.weight(mastered, 100), 0)


if __name__ == "__main__":
    unittest.main()
