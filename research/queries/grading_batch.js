// Batch grading view: one query, all of its candidates at once.
//
// Same job as grading_ui.js, different pacing. The row-by-row view re-displays
// the query for every candidate, so with a median of 6 candidates per query the
// grader reads each query about six times. Here the query and its rubric are
// shown once and every candidate is rated against it in one pass.
//
// Deliberately shares STORAGE_KEY and the query_id::doc_id row key with
// grading_ui.js, so a session started in one view continues in the other and
// grades already recorded are shown as selected rather than asked again.
//
// The rubric's own first-pass grade is dropped at parse time here too. Same
// reason: seeing it would anchor the grader and inflate the agreement statistic
// this exercise exists to measure.

// Overridable by query string, matching grading_ui.js, so an independent
// second pass can run without clobbering the first:
//   grading_batch.html?csv=adjudication_sample_v2.csv&key=careful
const _params = new URLSearchParams(location.search);
const CSV_URL = "/research/queries/" + (_params.get("csv") || "adjudication_sample.csv");
const STORAGE_KEY = "rentmate-grading-progress-" + (_params.get("key") || "v1");

// One question, asked the same way for every query type.
//
// The previous design showed a different 0/1/2 rubric per query category and
// asked the grader to hold the right one in mind while working. That failed in
// practice: two passes came back uncorrelated with the rubric, and the grader
// identified the cause as applying the wrong standard to a row. Four shifting
// definitions of the same three buttons is too much to carry.
//
// So the numbers are gone from the interface. The grader answers a single
// concrete question in plain language, and the mapping back to 0/1/2 happens
// here, invisibly. The underlying scale is unchanged, so results remain
// comparable to the rubric program's output.
const ANSWERS = [
  { g: 2, label: "Yes — that's what I wanted",      hint: "the search worked" },
  { g: 1, label: "Close, but not quite",            hint: "right sort of thing, misses something" },
  { g: 0, label: "No — wrong thing",                hint: "not what I was looking for" },
];

// Kept only as a quiet reference line, not as the instruction.
const RUBRIC = {
  exact: `This search names a specific tool and size.`,
  paraphrase: `This search describes a job to be done, not a tool name.`,
  attribute: `This search has a condition attached (a price limit or a place).`,
  vague: `This search is deliberately woolly. Judge it generously.`,
};

let rows = {};
let queryOrder = [];
let byQuery = new Map();
let grades = {};
let cursorRow = 0;
let qi = 0;

const rowKey = (r) => `${r.query_id}::${r.doc_id}`;

function parseCSV(text) {
  const lines = [];
  let field = "", row = [], inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false; }
      else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); lines.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); lines.push(row); }
  const header = lines.shift();
  return lines.filter((l) => l.length === header.length && l.some((v) => v !== ""))
              .map((l) => Object.fromEntries(header.map((h, i) => [h, l[i]])));
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ grades, cursor: cursorRow }));
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const p = JSON.parse(raw);
    grades = p.grades || {};
    cursorRow = p.cursor || 0;
  } catch { /* corrupt storage: start fresh rather than crash */ }
}

function totalRows() {
  return Object.keys(rows).length;
}

function renderProgress() {
  const graded = Object.keys(grades).length;
  const total = totalRows();
  document.getElementById("progress").style.width = `${(graded / total) * 100}%`;
  document.getElementById("counter").textContent =
    `${graded} of ${total} graded · query ${Math.min(qi + 1, queryOrder.length)} of ${queryOrder.length}`;
}

function render() {
  if (qi >= queryOrder.length) {
    document.getElementById("main").style.display = "none";
    document.getElementById("done").style.display = "block";
    renderProgress();
    return;
  }
  document.getElementById("main").style.display = "block";
  document.getElementById("done").style.display = "none";

  const qid = queryOrder[qi];
  const list = byQuery.get(qid);
  const first = rows[list[0]];

  document.getElementById("query").textContent = first.query_text;
  document.getElementById("qtype").textContent = first.query_category;
  document.getElementById("rubric").innerHTML = RUBRIC[first.query_category] || "";

  const t = document.getElementById("cands");
  t.innerHTML = "";
  for (const k of list) {
    const r = rows[k];
    const tr = document.createElement("tr");
    if (k in grades) tr.className = "done";
    const meta = `${r.doc_category} · ${r.doc_location || "?"} · $${r.doc_price_per_day || "?"}/day`;
    tr.innerHTML =
      `<td><div class="cand">${r.doc_name}</div><div class="meta">${meta}</div></td>` +
      `<td class="btns">${ANSWERS.map((a) =>
        `<button data-k="${k}" data-g="${a.g}" title="${a.hint}"` +
        `${grades[k] === a.g ? ' class="sel"' : ""}>${a.label}</button>`
      ).join("")}</td>`;
    t.appendChild(tr);
  }

  t.querySelectorAll("button").forEach((b) => {
    b.addEventListener("click", () => {
      grades[b.dataset.k] = Number(b.dataset.g);
      save();
      render();
      // Auto-advance removed. It fired 180ms after the last candidate in a
      // query was rated, which meant a click already in flight could land on
      // the next query's freshly rendered rows. Advancing is now explicit.
    });
  });

  const remaining = list.filter((k) => !(k in grades)).length;
  document.getElementById("navinfo").textContent =
    remaining ? `${remaining} left in this query` : "query complete";
  renderProgress();
}

function download() {
  const out = {
    generated: new Date().toISOString(),
    source_csv: CSV_URL,
    n_graded: Object.keys(grades).length,
    n_total: totalRows(),
    judgments: Object.keys(rows).filter((k) => k in grades).map((k) => ({
      query_id: rows[k].query_id,
      doc_id: rows[k].doc_id,
      query_category: rows[k].query_category,
      hand_grade: grades[k],
    })),
  };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `hand_grades_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function init() {
  const parsed = parseCSV(await (await fetch(CSV_URL)).text());
  for (const p of parsed) {
    // first_pass_grade intentionally not carried over -- see header comment.
    const k = rowKey(p);
    rows[k] = {
      query_id: p.query_id, query_text: p.query_text, query_category: p.query_category,
      doc_id: p.doc_id, doc_name: p.doc_name, doc_category: p.doc_category,
      doc_location: p.doc_location, doc_price_per_day: p.doc_price_per_day,
    };
    if (!byQuery.has(p.query_id)) { byQuery.set(p.query_id, []); queryOrder.push(p.query_id); }
    byQuery.get(p.query_id).push(k);
  }

  load();
  // Open on the first query that still has ungraded candidates, so resuming
  // from the row-by-row view lands where the work actually stopped.
  const firstUnfinished = queryOrder.findIndex((q) => byQuery.get(q).some((k) => !(k in grades)));
  qi = firstUnfinished === -1 ? queryOrder.length : firstUnfinished;
  render();
}

document.getElementById("next").addEventListener("click", () => {
  if (qi < queryOrder.length) { qi++; render(); }
});
document.getElementById("prev").addEventListener("click", () => {
  if (qi > 0) { qi--; render(); }
});
document.getElementById("download").addEventListener("click", download);

init();
