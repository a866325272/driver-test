"""把汽車筆試題庫 PDF 轉成 data/questions.json + static/img/*.png（只需跑一次）。

用法：
    python -I tools/parse_pdf.py <題庫.pdf> <專案根目錄>

解析方式：
1. 左側（x0 < LEFT_COL）的行解析成「題號 / 答案 / 題目開頭」，三者可能在同一行，
   例如 "141 (1)"、"(3) 駕車於上坡…"、"1090 (3) 駕車行經…"。不是題號也不是答案的左側行
   就是分類標題（架構、小分類）。
2. 題目文字與圖片依垂直間距分群（表格線存在時也當成分界），每一群對應到
   y 範圍內的那個題號（表格內容是垂直置中，題號落在群的中間）。
3. 沒有題號的群：在頁首就是上一題跨頁的接續，在頁尾就是下一題跨頁的開頭。
4. 選項文字全空、剛好 3 張圖的題目（例：「以下何者圖示為『狹路』？」）視為圖片選項。
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

LEFT_COL = 112        # 題號/答案欄：x0 小於此值（答案 x0 約 96~104，選項標籤 "(1)" 都在 120 以右）
GAP = 9               # 同一題內相鄰行的間距約 2~7，不同題之間約 12 以上
TABLE_LEFT = (56, 60) # 表格左框線 x 範圍（用來認列分隔線，排除頁首的全寬框）
IMG_ZOOM = 3

FULLWIDTH = str.maketrans("０１２３４５６７８９（）", "0123456789()")
SECTION_RE = re.compile(r"^架構([一二三])\s*(\S+)")
SKIP_RE = re.compile(r"^(新版汽車筆試題庫|第\s*\d+\s*頁|▎?題號|答$|案$|圖\s*示$|題\s*目$|架構.「.*」合計)")
LEFT_RE = re.compile(r"^\s*(?P<num>\d{1,4})?\s*(?:\((?P<ans>[123])\))?\s*(?P<rest>.*)$")


def norm(s):
    # 只把全形數字/括號轉半形，方便切選項；中文標點保留
    return s.translate(FULLWIDTH).strip()


def join_lines(lines):
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if out and out[-1].isascii() and out[-1].isalnum() and ln[0].isascii() and ln[0].isalnum():
            out += " "
        out += ln
    return out


def split_options(text):
    """找最後一組依序出現的 (1)(2)(3)，前面是題幹。"""
    p3 = text.rfind("(3)")
    p2 = text.rfind("(2)", 0, p3)
    p1 = text.rfind("(1)", 0, p2)
    if min(p1, p2, p3) < 0:
        return None
    stem = text[:p1].strip()
    opts = [text[p1 + 3:p2], text[p2 + 3:p3], text[p3 + 3:]]
    return stem, [o.strip() for o in opts]


def row_lines(page):
    ys = set()
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 1 and TABLE_LEFT[0] <= min(a.x, b.x) <= TABLE_LEFT[1]:
                    ys.add(a.y)
            elif it[0] == "re":
                r = it[1]
                if r.height < 1 and TABLE_LEFT[0] <= r.x0 <= TABLE_LEFT[1] and r.width > 10:
                    ys.add(r.y0)
    return sorted(ys)


def read_page(page):
    """回傳 (anchors, headings, items)。item = {y0, y1, x0, text|img}。"""
    anchors, headings, items, loose_ans, lines = [], [], [], [], []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] == 1:
            x0, y0, x1, y1 = b["bbox"]
            items.append({"x0": x0, "y0": y0, "y1": y1, "img": pymupdf.Rect(b["bbox"])})
            continue
        for ln in b["lines"]:
            t = norm("".join(s["text"] for s in ln["spans"]))
            if t and not SKIP_RE.match(t):
                lines.append((ln["bbox"], t))

    # 題目欄左緣 = 右側各行 x0 的眾數；答案欄有時偏右（x0 約 114），只要在題目欄左緣之前就算答案欄
    body_x = Counter(round(bb[0]) for bb, _ in lines if bb[0] >= LEFT_COL).most_common(1)
    body_left = body_x[0][0] if body_x else 999

    for (x0, y0, x1, y1), t in lines:
        if x0 < LEFT_COL:
            m = LEFT_RE.match(t)
            num, ans, rest = m.group("num"), m.group("ans"), m.group("rest")
            if num or ans:
                anchors.append({"y": (y0 + y1) / 2, "num": num, "ans": ans})
                if rest:
                    items.append({"x0": x0, "y0": y0, "y1": y1, "text": rest})
            else:
                headings.append((y0, t))
        elif x0 < body_left - 5 and (m := re.match(r"\(([123])\)\s*(.*)$", t)):
            loose_ans.append({"y": (y0 + y1) / 2, "ans": m.group(1), "rest": m.group(2),
                              "item": {"x0": x0, "y0": y0, "y1": y1, "text": t}})
        else:
            items.append({"x0": x0, "y0": y0, "y1": y1, "text": t})

    # 題號和答案可能各自一行（同一高度），合併；沒配對到的放回題目文字
    for a in anchors:
        if a["ans"]:
            continue
        near = [c for c in loose_ans if abs(c["y"] - a["y"]) < 6]
        if near:
            c = near[0]
            a["ans"] = c["ans"]
            loose_ans.remove(c)
            if c["rest"]:
                items.append(dict(c["item"], text=c["rest"]))
    items.extend(c["item"] for c in loose_ans)
    merged = []
    for a in sorted(anchors, key=lambda a: a["y"]):
        if merged and abs(merged[-1]["y"] - a["y"]) < 6 and bool(merged[-1]["num"]) != bool(a["num"]):
            merged[-1]["num"] = merged[-1]["num"] or a["num"]
            merged[-1]["ans"] = merged[-1]["ans"] or a["ans"]
        else:
            merged.append(a)
    return merged, headings, items


def cluster(items, lines):
    items = sorted(items, key=lambda it: it["y0"])
    groups = []
    for it in items:
        if groups:
            g = groups[-1]
            crosses = any(g["y1"] - 1 < ly < it["y0"] + 1 for ly in lines)
            if it["y0"] - g["y1"] <= GAP and not crosses:
                g["items"].append(it)
                g["y1"] = max(g["y1"], it["y1"])
                continue
        groups.append({"y0": it["y0"], "y1": it["y1"], "items": [it]})
    return groups


def reading_order(imgs):
    """圖片依列排序：y0 相差 10 以內算同一列，同列由左到右。"""
    rows = []
    for it in sorted(imgs, key=lambda it: (it["page"], it["y0"])):
        if rows and rows[-1][0]["page"] == it["page"] and it["y0"] - rows[-1][0]["y0"] < 10:
            rows[-1].append(it)
        else:
            rows.append([it])
    return [it for row in rows for it in sorted(row, key=lambda it: it["x0"])]


def main(pdf_path, root):
    root = Path(root)
    img_dir = root / "static" / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)

    questions = []
    section = subsection = None
    carry = []  # 頁尾沒有題號的群，屬於下一題

    for pno, page in enumerate(doc):
        anchors, headings, items = read_page(page)
        for a in anchors:
            if not a["num"] or not a["ans"]:
                raise SystemExit(f"p{pno + 1} y={a['y']:.0f}: 題號/答案不完整 {a}")
        groups = cluster(items, row_lines(page))

        # 先依 y 順序建立題目（標題決定 section/subsection）
        events = [(y, 0, "h", t) for y, t in headings] + [(a["y"], 1, "a", a) for a in anchors]
        events.sort(key=lambda e: (e[0], e[1]))
        for _, _, kind, obj in events:
            if kind == "h":
                m = SECTION_RE.match(obj)
                if m:
                    section, subsection = f"架構{m.group(1)} {m.group(2)}", None
                else:
                    subsection = re.sub(r"^分類\s*", "", obj)
            else:
                q = {"id": int(obj["num"]), "answer": int(obj["ans"]),
                     "section": section, "subsection": subsection,
                     "_items": [it for g in carry for it in g["items"]]}
                carry = []
                obj["q"] = q
                questions.append(q)
        prev_q = questions[-len(anchors) - 1] if len(questions) > len(anchors) else None

        first_y = anchors[0]["y"] if anchors else 1e9
        last_y = anchors[-1]["y"] if anchors else -1e9
        for g in groups:
            hits = [a for a in anchors if g["y0"] - 4 <= a["y"] <= g["y1"] + 4]
            tagged = [dict(it, page=pno) for it in g["items"]]
            if len(hits) > 1:
                raise SystemExit(f"p{pno + 1}: 一群對到多個題號 {[a['num'] for a in hits]}")
            if hits:
                hits[0]["q"]["_items"].extend(tagged)
            elif g["y1"] < first_y and prev_q is not None:
                prev_q["_items"].extend(tagged)   # 上一頁的題目跨頁接續
            elif g["y0"] > last_y:
                carry.append({"items": tagged})   # 下一頁的題目在這頁先開頭
            else:
                raise SystemExit(f"p{pno + 1} y={g['y0']:.0f}: 找不到題號的群: "
                                 f"{[it.get('text', 'IMG') for it in g['items']][:3]}")

    out = []
    for q in questions:
        its = sorted(q.pop("_items"), key=lambda it: (it["page"], round(it["y0"]), it["x0"]))
        text = join_lines(it["text"] for it in its if "text" in it)
        parsed = split_options(text)
        if parsed is None:
            raise SystemExit(f"Q{q['id']}: 切不出選項: {text!r}")
        q["stem"], q["options"] = parsed
        names = []
        for i, it in enumerate(reading_order([it for it in its if "img" in it])):
            name = f"q{q['id']:04d}_{i + 1}.png"
            pix = doc[it["page"]].get_pixmap(matrix=pymupdf.Matrix(IMG_ZOOM, IMG_ZOOM), clip=it["img"])
            pix.save(img_dir / name)
            names.append(name)
        if not any(q["options"]):
            if len(names) != 3:
                raise SystemExit(f"Q{q['id']}: 選項無文字但圖片數 {len(names)} != 3")
            q["images"], q["option_images"] = [], names
        else:
            q["images"], q["option_images"] = names, None
        out.append(q)

    (root / "data").mkdir(exist_ok=True)
    with open(root / "data" / "questions.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"{len(out)} questions, {sum(len(q['images']) + len(q['option_images'] or []) for q in out)} images")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
