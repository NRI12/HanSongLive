"use strict";
/* Trang /plan: xem trước lộ trình học theo ngày, xoá câu, soạn buổi mới, chọn buổi để chạy trên live. */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const KIND = { ko2vi: "Hàn → Việt", vi2ko: "Việt → Hàn", cloze: "🧩 Điền từ", trans: "📝 Dịch câu", hanviet: "🈶 Hán Việt",
  gram: "📘 Điền ngữ pháp", gfix: "✅ Câu đúng ngữ pháp" };
const KO_OPT = new Set(["vi2ko", "cloze", "gram", "gfix"]);
let S = null, openId = null;

function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove("show"), 2200); }
async function api(path, method = "GET", body) {
  const r = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin" });
  if (r.status === 401) { $("#login").classList.remove("hidden"); $("#app").classList.add("hidden"); throw new Error("Cần đăng nhập"); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
const run = (fn) => async (e) => { if (e && e.preventDefault) e.preventDefault(); try { await fn(e); } catch (er) { toast("⚠️ " + er.message); } };

$("#login").addEventListener("submit", run(async () => {
  try { await api("/api/login", "POST", { password: $("#pw").value }); } catch (er) { $("#loginErr").textContent = er.message; return; }
  $("#login").classList.add("hidden"); refresh();
}));

const ptChip = (p) => `<span class="chip${p.new === false ? " rev" : ""}">${p.new === false ? "ôn · " : ""}<span class="ko">${esc(p.form)}</span> · ${esc(p.vi)}</span>`;

function renderRun() {
  const a = S.active, box = $("#run");
  if (!a) { box.innerHTML = `<span>⏸ Chưa chạy buổi nào · live đang ra câu hỏi thường</span>`; return; }
  const p = S.plans.find((x) => x.id === a.id);
  const total = p ? p.total : 0;
  box.innerHTML = `<span>▶ Đang chạy <b>buổi #${a.id}</b> ${p ? esc(p.title) : ""}</span>
    <div class="bar"><i style="width:${total ? (a.pos / total) * 100 : 0}%"></i></div><span>${a.pos}/${total} câu</span>
    <button id="stop" class="danger">⏹ Dừng</button>`;
  $("#stop").onclick = run(async () => { await api("/api/plans/stop", "POST"); toast("Đã dừng lộ trình"); refresh(); });
}

let picked = new Set();
function renderCreate() {
  const next = S.next.map((n) => S.syllabus.find((p) => p.no === n));
  $("#nextPts").innerHTML = picked.size ? `<span class="muted">Đã chọn ${picked.size} điểm:</span>` +
    [...picked].map((n) => ptChip(S.syllabus.find((p) => p.no === n))).join("")
    : `<span class="muted">Mặc định 3 điểm kế tiếp:</span>` + next.map(ptChip).join("");
  if (!$("#syllabus")._done) {
    $("#syllabus")._done = true;
    let stage = "";
    $("#syllabus").innerHTML = S.syllabus.map((p) => {
      const h = p.stage !== stage ? `<div class="stage">${esc((stage = p.stage))}</div>` : "";
      return h + `<label class="pt${p.taught ? " done" : ""}"><input type="checkbox" value="${p.no}"><span class="n">${p.no}.</span>
        <span class="ko">${esc(p.form)}</span><small>${esc(p.vi)}${p.taught ? " · đã học" : ""}</small></label>`;
    }).join("");
    $("#syllabus").addEventListener("change", (e) => {
      const n = +e.target.value;
      if (e.target.checked) { if (picked.size >= 6) { e.target.checked = false; return toast("Tối đa 6 điểm"); } picked.add(n); } else picked.delete(n);
      renderCreate();
    });
  }
  const j = S.job;
  $("#create").disabled = j.running || !S.has_key;
  $("#job").textContent = !S.has_key ? "⚠️ Chưa có API key AI, vào Admin để nhập." : j.detail || "";
}

function renderPlans() {
  const a = S.active;
  $("#plans").innerHTML = S.plans.map((p) => `<div class="plan${a && a.id === p.id ? " on" : ""}">
      <div class="hd"><b>#${p.id} · ${esc(p.day)}</b><span class="muted">${p.total} câu · ${p.grammar} câu ngữ pháp</span></div>
      <div class="chips">${p.points.map(ptChip).join("")}</div>
      <div class="acts">
        <button data-view="${p.id}">👁 Xem ${openId === p.id ? "(đang mở)" : ""}</button>
        <button data-run="${p.id}" class="primary">▶ Chạy buổi này</button>
        <button data-del="${p.id}" class="danger">🗑 Xoá</button>
      </div></div>`).join("") || `<p class="muted">Chưa có buổi nào. Bấm "Soạn buổi mới".</p>`;
}
$("#plans").addEventListener("click", run(async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.view) { openId = +b.dataset.view; await showDetail(openId); renderPlans(); $("#detail").scrollIntoView({ behavior: "smooth" }); }
  if (b.dataset.run) { await api(`/api/plans/${b.dataset.run}/run`, "POST", { pos: 0 }); toast("▶ Live sẽ ra câu của buổi này từ câu kế tiếp"); refresh(); }
  if (b.dataset.del && confirm(`Xoá buổi #${b.dataset.del}?`)) { await api(`/api/plans/${b.dataset.del}`, "DELETE"); if (openId === +b.dataset.del) { openId = null; $("#detail").classList.add("hidden"); } refresh(); }
}));

function qHtml(q, i, cur) {
  const opts = q.options.map((o, k) => `<li class="${k === q.answer ? "ok" : ""}"><b>${"ABCD"[k]}.</b> <span class="${KO_OPT.has(q.mode) ? "ko" : ""}">${esc(o)}</span>${k === q.answer ? " ✓" : ""}</li>`).join("");
  const g = q.mode === "gram" || q.mode === "gfix";
  return `<div class="q${cur ? " cur" : ""}">
    <div class="meta"><b>${i + 1}.</b><span class="kind${g ? " g" : ""}">${KIND[q.mode] || q.mode}</span>
      ${q.point_form ? `<span class="ko">${esc(q.point_form)}</span>` : ""}${cur ? "<b>· câu kế tiếp trên live</b>" : ""}</div>
    <div class="prompt ${q.prompt_lang === "ko" ? "ko" : ""}">${esc(q.prompt)}</div>
    ${q.hint ? `<div class="hint">💬 ${esc(q.hint)}</div>` : ""}
    <ol>${opts}</ol>
    ${q.note ? `<div class="note">📘 ${esc(q.note)}</div>` : ""}
    <div class="acts"><button data-from="${i}">▶ Chạy từ câu này</button><button data-delq="${i}" class="danger">✕ Bỏ câu</button></div>
  </div>`;
}
async function showDetail(pid) {
  const p = await api(`/api/plans/${pid}`), a = S.active, box = $("#detail");
  box.classList.remove("hidden");
  box.innerHTML = `<h2>👁 Buổi #${p.id} · ${esc(p.day)}</h2><div class="chips">${p.points.map(ptChip).join("")}</div>
    <p class="muted">${p.questions.length} câu, chạy đúng thứ tự dưới đây. Đáp án đúng tô xanh.</p>
    ${p.questions.map((q, i) => qHtml(q, i, a && a.id === p.id && a.pos === i)).join("")}`;
  box.dataset.pid = p.id;
}
$("#detail").addEventListener("click", run(async (e) => {
  const b = e.target.closest("button"), pid = +$("#detail").dataset.pid;
  if (!b) return;
  if (b.dataset.delq) { await api(`/api/plans/${pid}/q/${b.dataset.delq}`, "DELETE"); toast("Đã bỏ câu"); await refresh(); await showDetail(pid); }
  if (b.dataset.from) { await api(`/api/plans/${pid}/run`, "POST", { pos: +b.dataset.from }); toast(`▶ Live chạy từ câu ${+b.dataset.from + 1}`); await refresh(); await showDetail(pid); }
}));

$("#create").addEventListener("click", run(async () => {
  await api("/api/plans", "POST", { points: picked.size ? [...picked] : null });
  toast("✨ Đang soạn buổi mới, khoảng 1 phút…"); picked.clear();
  $("#syllabus").querySelectorAll("input").forEach((x) => (x.checked = false));
  refresh();
}));

async function refresh() {
  S = await api("/api/plans");
  $("#app").classList.remove("hidden");
  renderRun(); renderCreate(); renderPlans();
}
refresh().catch(() => {});
setInterval(() => { if (S && (S.job.running || S.active)) refresh().catch(() => {}); }, 4000);
