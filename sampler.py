"""抽題權重。

權重 = 久未練習加成 × 錯誤率加成，最近練過的題目暫時不抽（冷卻）。

- 久未練習加成：距離上次練習這題，中間又練了幾題（age）。age 越大權重越高，
  練過的題目加成有上限（AGE_CAP）。沒練過的題目 age = 目前總練習次數 + UNSEEN_BONUS_AGE
  而且不設上限，所以練得越多，剩下沒練過的題目越容易被抽到。
- 錯誤率加成：平滑錯誤率 (答錯 + 1) / (作答 + 2)，沒做過視為 0.5。
  答錯越多權重越高，一直答對會降低但不會歸零。
- 冷卻：最近 COOLDOWN 次練習中出現過的題目權重為 0（題目池太小時自動放寬）。
"""
import random

AGE_SCALE = 100          # age 每增加這麼多，加成 +1
AGE_CAP = 1000           # 練過的題目 age 加成上限（最多 1 + 1000/100 = 11 倍）；沒練過的不設上限
UNSEEN_BONUS_AGE = 100   # 沒練過的題目額外加的 age，讓新題一開始就略優先
ERR_FLOOR = 0.1          # 錯誤率加成 = 4 * (ERR_FLOOR + err)^2，err=0.5 時約 1.44
COOLDOWN = 20            # 最近 N 次練過的題目不抽


def age_of(stat, seq):
    if stat is None or stat["last_seq"] is None:
        return seq + UNSEEN_BONUS_AGE
    return seq - stat["last_seq"]


def weight(stat, seq, cooldown=COOLDOWN):
    age = age_of(stat, seq)
    if stat is not None and stat["last_seq"] is not None and age < cooldown:
        return 0.0
    attempts = stat["attempts"] if stat else 0
    correct = stat["correct"] if stat else 0
    err = (attempts - correct + 1) / (attempts + 2)
    unseen = stat is None or stat["last_seq"] is None
    age_factor = 1 + (age if unseen else min(age, AGE_CAP)) / AGE_SCALE
    err_factor = 4 * (ERR_FLOOR + err) ** 2
    return age_factor * err_factor


def weights(qids, stats, seq):
    """回傳 {qid: weight}。stats: {qid: row}，沒練過的題目不在 stats 裡。"""
    cooldown = min(COOLDOWN, max(0, len(qids) // 2))
    return {q: weight(stats.get(q), seq, cooldown) for q in qids}


def pick(qids, stats, seq, rng=random):
    ws = weights(qids, stats, seq)
    total = sum(ws.values())
    if total <= 0:
        return rng.choice(list(qids)), ws
    ids = list(ws)
    return rng.choices(ids, weights=[ws[i] for i in ids], k=1)[0], ws
