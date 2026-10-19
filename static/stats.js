const $ = (id) => document.getElementById(id);
const pct = (v, d = 0) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(d)}%`);
let data = null;
let sortKey = "id";
let sortDir = 1;
const expanded = new Set();

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c);
  return e;
}

function renderSummary() {
  const o = data.overall;
  const tiles = [
    ["已練習題數", `${o.practiced} / ${o.questions}`],
    ["覆蓋率", pct(o.practiced / o.questions, 1)],
    ["總作答次數", String(o.attempts)],
    ["總答對率", pct(o.accuracy, 1)],
  ];
  $("tiles").replaceChildren(...tiles.map(([k, v]) =>
    el("div", { class: "tile" }, el("div", { class: "tile-label" }, k), el("div", { class: "tile-value" }, v))));

  $("sections").replaceChildren(...data.sections.map((s) => el("tr", {},
    el("td", {}, s.name),
    el("td", { class: "n" }, String(s.questions)),
    el("td", { class: "n" }, String(s.practiced)),
    el("td", { class: "n" }, pct(s.practiced / s.questions, 1)),
    el("td", { class: "n" }, String(s.attempts)),
    el("td", { class: "n" }, pct(s.accuracy, 1)),
  )));
}

function filtered() {
  const sec = $("f-section").value;
  const status = $("f-status").value;
  const text = $("f-text").value.trim();
  return data.rows.filter((r) => {
    if (sec && String(r.section) !== sec) return false;
    if (status === "unseen" && r.attempts) return false;
    if (status === "seen" && !r.attempts) return false;
    if (status === "weak" && !(r.attempts && r.accuracy < 0.6)) return false;
    if (status === "lastwrong" && !(r.attempts && r.streak === 0)) return false;
    if (text && !(String(r.id) === text || r.stem.includes(text) || r.options.some((o) => o.includes(text)))) return false;
    return true;
  });
}

function compare(a, b) {
  let x = a[sortKey], y = b[sortKey];
  // 沒資料的（未練習）一律排最後
  const nx = x === null || x === undefined, ny = y === null || y === undefined;
  if (nx || ny) return nx === ny ? a.id - b.id : nx ? 1 : -1;
  if (typeof x === "string") return x.localeCompare(y) * sortDir || a.id - b.id;
  return (x - y) * sortDir || a.id - b.id;
}

function detailRow(r) {
  const box = el("div", { class: "detail" });
  if (r.stem) box.append(el("p", {}, r.stem));
  for (const name of r.images) box.append(el("img", { src: IMG_BASE + name, alt: "" }));
  const ol = el("ol", { class: "detail-options" });
  r.options.forEach((text, i) => {
    const li = el("li", { class: i + 1 === r.answer ? "correct" : "" });
    li.append(`(${i + 1}) `);
    if (r.option_images) li.append(el("img", { src: IMG_BASE + r.option_images[i], alt: "" }));
    else li.append(text);
    ol.append(li);
  });
  box.append(ol, el("p", { class: "muted" }, `分類：${r.subsection}　正確答案：(${r.answer})　連續答對：${r.streak}`));
  return el("tr", { class: "detail-row" }, el("td", { colspan: "8" }, box));
}

function renderRows() {
  const rows = filtered().sort(compare);
  $("count").textContent = `${rows.length} 題`;
  const out = [];
  for (const r of rows) {
    const stem = r.stem || (r.option_images ? "（圖片選項題）" : "（看圖作答）");
    const tr = el("tr", { class: "qrow" + (r.attempts && r.accuracy < 0.6 ? " weak" : "") },
      el("td", { class: "n" }, String(r.id)),
      el("td", {}, `架構${"一二三"[r.section - 1]}`),
      el("td", { class: "stem-cell" }, stem),
      el("td", { class: "n" }, String(r.attempts)),
      el("td", { class: "n" }, String(r.correct)),
      el("td", { class: "n" }, pct(r.accuracy)),
      el("td", {}, r.last_at ? r.last_at.replace("T", " ").slice(0, 16) : "—"),
      el("td", { class: "n" }, pct(r.probability, 3)),
    );
    tr.addEventListener("click", () => {
      expanded.has(r.id) ? expanded.delete(r.id) : expanded.add(r.id);
      renderRows();
    });
    out.push(tr);
    if (expanded.has(r.id)) out.push(detailRow(r));
  }
  $("rows").replaceChildren(...out);
  for (const th of document.querySelectorAll("th[data-sort]")) {
    th.classList.toggle("sorted", th.dataset.sort === sortKey);
    th.dataset.dir = th.dataset.sort === sortKey ? (sortDir > 0 ? "▲" : "▼") : "";
  }
}

for (const th of document.querySelectorAll("th[data-sort]")) {
  th.addEventListener("click", () => {
    if (sortKey === th.dataset.sort) sortDir = -sortDir;
    else { sortKey = th.dataset.sort; sortDir = 1; }
    renderRows();
  });
}
for (const id of ["f-section", "f-status", "f-text"]) $(id).addEventListener("input", renderRows);

fetch("/api/stats").then((r) => r.json()).then((d) => {
  data = d;
  renderSummary();
  renderRows();
});
