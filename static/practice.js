const $ = (id) => document.getElementById(id);
let current = null;      // 目前題目
let answered = false;
const session = { total: 0, correct: 0 };

function loadSection() {
  try { return localStorage.getItem("section") || "all"; } catch { return "all"; }
}
function saveSection(v) {
  try { localStorage.setItem("section", v); } catch { /* 無痕模式等情況忽略 */ }
}

function fmtStat(s) {
  if (!s.attempts) return "這題還沒練習過";
  const acc = Math.round(s.accuracy * 100);
  return `這題練過 ${s.attempts} 次，答對 ${s.correct} 次（${acc}%）`;
}

function renderSession() {
  const acc = session.total ? Math.round(session.correct / session.total * 100) : 0;
  $("session").textContent = `本次：${session.total} 題，答對 ${session.correct}（${acc}%）`;
}

async function next() {
  const params = new URLSearchParams({ section: $("section").value });
  if (current) params.set("exclude", current.id);
  const res = await fetch(`${API_BASE}/next?${params}`);
  const data = await res.json();
  current = data.question;
  answered = false;

  $("qid").textContent = `第 ${current.id} 題`;
  $("qsub").textContent = `${current.section}｜${current.subsection}`;
  $("stem").textContent = current.stem;
  $("stem").hidden = !current.stem;
  $("stem-images").innerHTML = "";
  for (const name of current.images) {
    const img = document.createElement("img");
    img.src = IMG_BASE + name;
    img.alt = `第 ${current.id} 題附圖`;
    $("stem-images").append(img);
  }

  $("options").innerHTML = "";
  current.options.forEach((text, i) => {
    const btn = document.createElement("button");
    btn.className = "option";
    btn.dataset.choice = i + 1;
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = `(${i + 1})`;
    btn.append(num);
    if (current.option_images) {
      const img = document.createElement("img");
      img.src = IMG_BASE + current.option_images[i];
      img.alt = `選項 ${i + 1}`;
      btn.append(img);
    } else {
      const span = document.createElement("span");
      span.textContent = text;
      btn.append(span);
    }
    btn.addEventListener("click", () => answer(i + 1));
    $("options").append(btn);
  });

  $("feedback").hidden = true;
  $("qstat").textContent = `${fmtStat(data.stat)}｜目前抽中機率 ${(data.probability * 100).toFixed(3)}%`;
  $("next").textContent = "換一題";
}

async function answer(choice) {
  if (answered || !current) return;
  answered = true;
  const res = await fetch(`${API_BASE}/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: current.id, choice }),
  });
  const data = await res.json();

  for (const btn of $("options").children) {
    const c = Number(btn.dataset.choice);
    btn.disabled = true;
    if (c === data.answer) btn.classList.add("correct");
    else if (c === choice) btn.classList.add("wrong");
  }
  const fb = $("feedback");
  fb.hidden = false;
  fb.className = "feedback " + (data.correct ? "ok" : "ng");
  fb.textContent = data.correct ? "答對了" : `答錯了，正確答案是 (${data.answer})`;
  $("qstat").textContent = fmtStat(data.stat);
  $("next").textContent = "下一題";

  session.total += 1;
  if (data.correct) session.correct += 1;
  renderSession();
}

$("next").addEventListener("click", next);
$("section").value = loadSection();
$("section").addEventListener("change", (e) => { saveSection(e.target.value); current = null; next(); });
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "SELECT") return;
  if (["1", "2", "3"].includes(e.key)) answer(Number(e.key));
  else if ((e.key === "Enter" || e.key === " ") && answered) { e.preventDefault(); next(); }
});
renderSession();
next();
