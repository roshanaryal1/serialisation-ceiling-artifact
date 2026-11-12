// Grading UI for the hand-adjudication sample (RESEARCH_PLAN.md Phase 3).
// Served by research/harness/server.js -- open:
//   http://localhost:8743/research/queries/grading_ui.html
//
// Deliberately does NOT load or display `first_pass_grade` from the CSV. The
// whole point of this exercise is to compare an independent human judgement
// against the rubric program; showing the rubric's answer first would anchor
// the grader and inflate Cohen's kappa toward agreement that isn't real.
// The column is stripped at parse time, not merely hidden in the DOM, so it
// can't leak via devtools either.

// Both are overridable by query string so a second, independent grading pass
// can run without clobbering the first:
//   grading_ui.html?csv=adjudication_sample_v2.csv&key=careful
const _params = new URLSearchParams(location.search);
const CSV_URL = "/research/queries/" + (_params.get("csv") || "adjudication_sample.csv");
const STORAGE_KEY = "rentmate-grading-progress-" + (_params.get("key") || "v1");

// Per-query-type rubric text, lifted from labelling_protocol.md so the grader
// applies the same written criteria the protocol pre-committed to, rather
// than drifting toward whatever feels right by row 200.
const RUBRIC = {
  exact: `<p><b>2</b> — same equipment type, spec at or near the queried figure.</p>
          <p><b>1</b> — same category but wrong type, or spec far off.</p>
          <p><b>0</b> — different category, or fundamentally different function.</p>`,
  paraphrase: `<p><b>2</b> — a standard tool for the described task, whatever its exact type.</p>
               <p><b>1</b> — tangentially related; plausible but not the direct answer.</p>
               <p><b>0</b> — unrelated category.</p>`,
  attribute: `<p><b>2</b> — correct category <i>and</i> the stated constraint (price ceiling / location) is satisfied.</p>
              <p><b>1</b> — correct category, constraint not satisfied.</p>
              <p><b>0</b> — wrong category, regardless of the constraint.</p>`,
  vague: `<p><b>2</b> — plausibly what the person is after, given how underspecified the query is.</p>
          <p><b>1</b> — adjacent category that could resolve the same need.</p>
          <p><b>0</b> — unrelated category.</p>`,
};

let rows = [];
let grades = {}; // rowKey -> 0|1|2
let order = []; // rowKeys in presentation order
let cursor = 0;

function rowKey(r) {
  return `${r.query_id}::${r.doc_id}`;
}

// Minimal CSV parser handling the quoted fields our writer emits (doc names
// contain commas, e.g. "Screw Gun (Heavy-Duty, 76 mm)").
function parseCSV(text) {
  const lines = [];
  let field = "";
  let row = [];
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQuotes = false;
      } else field += c;
    } else if (c === '"') inQuotes = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); lines.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); lines.push(row); }
  const header = lines.shift();
  return lines
    .filter((l) => l.length === header.length && l.some((v) => v !== ""))
    .map((l) => Object.fromEntries(header.map((h, i) => [h, l[i]])));
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ grades, cursor }));
}

function load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    grades = parsed.grades || {};
    cursor = parsed.cursor || 0;
  } catch {
    /* corrupt storage: start fresh rather than crash */
  }
}

function render() {
  const total = order.length;
  const graded = Object.keys(grades).length;
  document.getElementById("progress").style.width = `${(graded / total) * 100}%`;
  document.getElementById("counter").textContent =
    `${graded} of ${total} graded${graded < total ? ` · on row ${cursor + 1}` : ""}`;

  if (cursor >= total) {
    document.getElementById("grading").style.display = "none";
    document.getElementById("done").style.display = "block";
    return;
  }
  document.getElementById("grading").style.display = "block";
  document.getElementById("done").style.display = "none";

  const r = rows[order[cursor]];
  document.getElementById("query").textContent = r.query_text;
  document.getElementById("qtype").textContent = r.query_category;
  document.getElementById("doc").textContent = r.doc_name;
  // Location and price are shown for every row, not only attribute queries, so
  // the card layout does not itself hint at which rows carry a constraint.
  document.getElementById("doccat").textContent =
    `${r.doc_category}  ·  ${r.doc_location || "?"}  ·  $${r.doc_price_per_day || "?"}/day`;
  document.getElementById("rubric").innerHTML =
    RUBRIC[r.query_category] || "<p>(no rubric for this query type)</p>";
}

function grade(g) {
  if (cursor >= order.length) return;
  grades[order[cursor]] = g;
  cursor++;
  save();
  render();
}

function undo() {
  if (cursor === 0) return;
  cursor--;
  delete grades[order[cursor]];
  save();
  render();
}

function download() {
  const out = {
    generated: new Date().toISOString(),
    source_csv: CSV_URL,
    n_graded: Object.keys(grades).length,
    n_total: order.length,
    judgments: order
      .filter((k) => k in grades)
      .map((k) => {
        const r = rows[k];
        return {
          query_id: r.query_id,
          doc_id: r.doc_id,
          query_category: r.query_category,
          hand_grade: grades[k],
        };
      }),
  };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `hand_grades_${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function init() {
  const res = await fetch(CSV_URL);
  const parsed = parseCSV(await res.text());

  rows = {};
  order = [];
  for (const p of parsed) {
    // first_pass_grade is dropped here, on purpose -- see the header comment.
    const k = rowKey(p);
    rows[k] = {
      query_id: p.query_id,
      query_text: p.query_text,
      query_category: p.query_category,
      doc_id: p.doc_id,
      doc_name: p.doc_name,
      doc_category: p.doc_category,
      doc_location: p.doc_location,
      doc_price_per_day: p.doc_price_per_day,
    };
    order.push(k);
  }

  load();
  // Guard against a stale cursor if the sample was regenerated with a
  // different size since the last session.
  if (cursor > order.length) cursor = order.length;
  render();
}

document.querySelectorAll("button.grade").forEach((b) => {
  b.addEventListener("click", () => grade(Number(b.dataset.g)));
});
document.getElementById("undo").addEventListener("click", undo);
document.getElementById("download").addEventListener("click", download);
document.getElementById("reset").addEventListener("click", () => {
  if (!confirm("Discard all grading progress and start over?")) return;
  grades = {};
  cursor = 0;
  save();
  render();
});
window.addEventListener("keydown", (e) => {
  if (e.key === "0" || e.key === "1" || e.key === "2") grade(Number(e.key));
  else if (e.key.toLowerCase() === "u") undo();
});

init();
