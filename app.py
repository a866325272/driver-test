"""汽車筆試題庫練習 web app。

    python app.py          # 開發模式，http://localhost:5000/driver-test/

路徑都在 /driver-test 底下，reverse proxy 只要設一條規則：
    /driver-test/          練習頁（/driver-test 會轉址補上結尾斜線）
    /driver-test/stats     統計頁
    /driver-test/api/...   API
    /driver-test/static/.. 靜態檔與題目圖片
proxy 轉進來時有沒有拿掉 /driver-test 都可以（見 PrefixFallback）。
環境變數：
    PROGRESS_DB  作答紀錄 SQLite 檔路徑（預設 ./var/progress.db）
"""
import json
import os
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request

import sampler
from store import Store

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("PROGRESS_DB", BASE / "var" / "progress.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

with open(BASE / "data" / "questions.json", encoding="utf-8") as f:
    QUESTIONS = {q["id"]: q for q in json.load(f)}
# 依題號出現順序：架構一、二、三（不能用字串排序，「三」會排在「二」前面）
SECTIONS = list(dict.fromkeys(q["section"] for q in QUESTIONS.values()))

PREFIX = "/driver-test"
API = f"{PREFIX}/api"



class PrefixFallback:
    """沒有 /driver-test 開頭的請求，補上 prefix 再交給 Flask。

    nginx 的 proxy_pass 若帶結尾斜線（proxy_pass http://app:8000/;）會把 prefix 拿掉再轉進來，
    例如 /driver-test/stats 進來時變成 /stats。補回 prefix 後，不管 proxy 有沒有拿掉都能對到同一組 route，
    頁面裡的連結一律用 /driver-test 開頭的絕對路徑，經過 proxy 也正確。
    """

    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path != PREFIX and not path.startswith(PREFIX + "/"):
            environ["PATH_INFO"] = PREFIX + path
        return self.wsgi_app(environ, start_response)


app = Flask(__name__, static_url_path=f"{PREFIX}/static")
app.wsgi_app = PrefixFallback(app.wsgi_app)
store = Store(DB_PATH)


def scope_ids(section):
    """section: "all" 或 1/2/3（對應架構一、二、三）。"""
    if section in (None, "", "all"):
        return list(QUESTIONS)
    try:
        name = SECTIONS[int(section) - 1]
    except (ValueError, IndexError):
        abort(400, "section 必須是 all 或 1~3")
    return [qid for qid, q in QUESTIONS.items() if q["section"] == name]


def stat_view(stat):
    attempts = stat["attempts"] if stat else 0
    correct = stat["correct"] if stat else 0
    return {
        "attempts": attempts,
        "correct": correct,
        "accuracy": round(correct / attempts, 4) if attempts else None,
        "streak": stat["streak"] if stat else 0,
        "last_at": stat["last_at"] if stat else None,
    }


def public_question(q):
    """不含答案的題目內容。"""
    return {k: q[k] for k in ("id", "section", "subsection", "stem", "options", "images", "option_images")}


@app.context_processor
def inject_api_base():
    return {"api_base": API}


# /driver-test 補上結尾斜線，和 nginx 同方向（反過來會和 proxy 互相轉址）。
# 自己寫而不靠 Flask 的自動轉址，因為 Flask 會產生帶內部 Host 的絕對網址，經過 proxy 會轉錯地方。
@app.get(PREFIX)
def practice_page_no_slash():
    return redirect(f"{PREFIX}/", code=308)


@app.get(f"{PREFIX}/")
def practice_page():
    return render_template("practice.html", sections=SECTIONS)


@app.get(f"{PREFIX}/stats")
def stats_page():
    return render_template("stats.html", sections=SECTIONS)


@app.get(f"{API}/next")
def api_next():
    ids = scope_ids(request.args.get("section"))
    # 前端會帶目前畫面上的題號，避免連續兩次抽到同一題（作答前按「換一題」時）
    exclude = request.args.get("exclude", type=int)
    if exclude in ids and len(ids) > 1:
        ids.remove(exclude)
    stats = store.all_stats()
    seq = store.seq()
    qid, ws = sampler.pick(ids, stats, seq)
    total = sum(ws.values())
    return jsonify({
        "question": public_question(QUESTIONS[qid]),
        "stat": stat_view(stats.get(qid)),
        "weight": round(ws[qid], 4),
        "probability": round(ws[qid] / total, 6) if total else None,
        "pool_size": len(ids),
    })


@app.post(f"{API}/answer")
def api_answer():
    body = request.get_json(silent=True) or {}
    qid, choice = body.get("id"), body.get("choice")
    if qid not in QUESTIONS or choice not in (1, 2, 3):
        abort(400, "需要 id（題號）與 choice（1~3）")
    q = QUESTIONS[qid]
    is_correct = choice == q["answer"]
    stat = store.record(qid, choice, is_correct)
    return jsonify({"correct": is_correct, "answer": q["answer"], "stat": stat_view(stat)})


@app.get(f"{API}/stats")
def api_stats():
    stats = store.all_stats()
    seq = store.seq()
    ws = sampler.weights(list(QUESTIONS), stats, seq)
    total_w = sum(ws.values()) or 1
    rows = []
    for qid, q in QUESTIONS.items():
        s = stat_view(stats.get(qid))
        rows.append({
            "id": qid,
            "section": SECTIONS.index(q["section"]) + 1,
            "subsection": q["subsection"],
            "stem": q["stem"],
            "options": q["options"],
            "images": q["images"],
            "option_images": q["option_images"],
            "answer": q["answer"],
            **s,
            "probability": ws[qid] / total_w,
        })

    def summary(ids):
        ss = [stats[i] for i in ids if i in stats]
        attempts = sum(s["attempts"] for s in ss)
        correct = sum(s["correct"] for s in ss)
        return {"questions": len(ids), "practiced": len(ss), "attempts": attempts,
                "correct": correct, "accuracy": round(correct / attempts, 4) if attempts else None}

    by_section = [dict(summary([i for i, q in QUESTIONS.items() if q["section"] == name]), name=name)
                  for name in SECTIONS]
    return jsonify({"overall": summary(list(QUESTIONS)), "sections": by_section, "rows": rows})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=True)
