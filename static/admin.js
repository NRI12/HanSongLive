"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const PHASE = { idle: "Đang dừng", question: "Đang hỏi", reveal: "Hiện đáp án", board: "Bảng xếp hạng" };
const MOCK_NAMES = ["Minh Anh", "Tuấn", "Hà Linh", "Bảo", "Thu Trang", "Khoa", "Ngọc", "Duy", "Mai", "Phúc", "Lan", "Quân"];
const SPECIAL = { boss: "👹 boss", listen: "🎧 nghe" };
const KIND = { ko2vi: "Hàn → Việt", vi2ko: "Việt → Hàn", listen: "🎧 Nghe", boss: "👹 Boss", cloze: "🧩 Điền chỗ trống", trans: "📝 Dịch câu", hanviet: "🈶 Hán Việt" };
let formLoaded = false;

function toast(m, ms = 2500) { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), ms); }

async function api(path, method = "GET", body) {
  const o = { method, headers: {}, credentials: "same-origin" };
  if (body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(body); }
  const r = await fetch(path, o);
  if (r.status === 401) { $("#login").classList.remove("hidden"); $("#app").classList.add("hidden"); throw new Error("Cần đăng nhập"); }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Lỗi " + r.status);
  return d;
}
const run = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, 4000); } };

$("#login").addEventListener("submit", run(async (e) => {
  e.preventDefault();
  try { await api("/api/login", "POST", { password: $("#pw").value }); } catch (er) { $("#loginErr").textContent = er.message; return; }
  $("#login").classList.add("hidden"); refresh();
}));

function render(s) {
  $("#app").classList.remove("hidden");
  const st = s.status;
  $("#pill").textContent = { tiktok: "TikTok", mock: "Thử", off: "Ngắt" }[st.mode] + " · " + ({ idle: "chờ", connecting: "đang kết nối", connected: "đã kết nối", disconnected: "mất kết nối", error: "lỗi" }[st.state] || st.state);
  $("#pill").className = "pill " + st.state;
  $("#status").textContent = st.detail + (st.attempt > 1 ? ` (lần ${st.attempt})` : "");
  $("#mockCard").style.opacity = st.mode === "mock" ? 1 : .5;
  const g = s.game, Q = g.question;
  $("#gameInfo").innerHTML = `<b>${PHASE[g.phase]}</b>${g.phase !== "idle" ? ` · còn ${Math.ceil(g.remaining)}s` : ""} · đã chơi ${g.round} câu ·
    ${g.players} người chơi · ❤️ ${g.likes} · 💎 ${g.goals.diamonds.value}/${g.goals.diamonds.goal} · 🔁 ${g.goals.shares.value} · ➕ ${g.follows}
    ${g.double_next ? " · <b style='color:var(--warn)'>câu sau x2</b>" : ""}${g.next_special ? ` · <b style='color:var(--warn)'>câu sau: ${SPECIAL[g.next_special]}</b>` : ""}
    ${g.teams ? `<br>🔴 Đỏ ${g.teams.red.score} (${g.teams.red.members} người) · 🔵 Xanh ${g.teams.blue.score} (${g.teams.blue.members} người)` : ""}
    ${g.vote_mode ? ` · khán giả chọn: ${KIND[g.vote_mode]}` : ""}
    ${Q ? `<br>Câu hiện tại${Q.special ? " (" + SPECIAL[Q.special] + ")" : ""}: <b>${esc(Q.prompt)}</b> · ${Q.answered} trả lời${Q.answer != null ? ` · đáp án ${"ABCD"[Q.answer]}: ${esc(Q.options[Q.answer])}` : ""}` : ""}
    ${g.message ? `<br><span class="err">${esc(g.message)}</span>` : ""}`;
  const A = s.ai, J = A.job;
  $("#aiInfo").innerHTML = `Đã có: 🧩 ${A.counts.cloze || 0} câu điền chỗ trống · 📝 ${A.counts.trans || 0} câu dịch ·
    key: DeepSeek ${A.has_deepseek_key ? "✅" : "❌"} · OpenAI ${A.has_openai_key ? "✅" : "❌"}
    ${J.running ? `<br><b style="color:var(--warn)">⏳ ${J.done}/${J.total} từ · đã tạo ${J.made} câu</b>` : J.detail ? `<br>${esc(J.detail)}` : ""}`;
  $("#aiGen").disabled = J.running;
  $("#adminTop").innerHTML = g.top.map((p) => `<li>${esc(p.name)} <b>${p.score}</b></li>`).join("");
  $("#overlayUrl").value = location.origin + s.overlay_path;
  $("#openUrl").href = s.overlay_path;
  if (!formLoaded) {
    formLoaded = true;
    $("#ttUser").value = s.tiktok.username;
    $("#ttKey").placeholder = s.tiktok.has_sign_key ? "đã lưu khoá · để trống = giữ nguyên" : "chưa có khoá";
    $("#hsUrl").value = s.hansong.url;
    $("#hsPw").placeholder = s.hansong.has_password ? "đã lưu · để trống = giữ nguyên" : "chưa đặt";
    const f = $("#gameCfg");
    for (const [k, v] of Object.entries(g.config)) if (f.elements[k]) f.elements[k].value = v;
    $("#aiProvider").value = A.provider; $("#aiModelDs").value = A.model_deepseek; $("#aiModelOa").value = A.model_openai;
    $("#aiVerify").value = A.verify ? "1" : "0";
    $("#aiDsKey").placeholder = A.has_deepseek_key ? "đã lưu · để trống = giữ nguyên" : "chưa có khoá";
    $("#aiOaKey").placeholder = A.has_openai_key ? "đã lưu · để trống = giữ nguyên" : "chưa có khoá";
  }
}

async function refresh() {
  try { render(await api("/api/admin")); } catch (e) { if (e.message !== "Cần đăng nhập") $("#status").textContent = e.message; }
}
setInterval(() => { if (!$("#app").classList.contains("hidden")) refresh(); }, 1000);
refresh();

document.querySelectorAll("[data-game]").forEach((b) => b.addEventListener("click", run(async () => {
  if (b.dataset.game === "reset" && !confirm("Xoá điểm của phiên live này? (Điểm mọi thời đại vẫn giữ)")) return;
  await api("/api/game", "POST", { action: b.dataset.game }); refresh();
})));
document.querySelectorAll("[data-connect]").forEach((b) => b.addEventListener("click", run(async () => {
  await api("/api/connect", "POST", { mode: b.dataset.connect }); refresh();
})));
$("#saveTT").addEventListener("click", run(async () => {
  await api("/api/config", "PUT", { tiktok_username: $("#ttUser").value, tiktok_sign_key: $("#ttKey").value || null });
  $("#ttKey").value = ""; formLoaded = false; toast("Đã lưu ✓");
}));
$("#saveHS").addEventListener("click", run(async () => {
  await api("/api/config", "PUT", { hansong_url: $("#hsUrl").value, hansong_password: $("#hsPw").value || null });
  $("#hsPw").value = ""; formLoaded = false; toast("Đã lưu ✓");
}));
$("#checkHS").addEventListener("click", run(async () => {
  $("#hsResult").textContent = "Đang kiểm tra…";
  const r = await api("/api/hansong/check", "POST");
  $("#hsResult").innerHTML = `<span style="color:var(${r.ok ? "--good" : "--bad"})">${esc(r.detail)}</span>`;
}));
$("#clearAudio").addEventListener("click", run(async () => { await api("/api/hansong/clear-audio", "POST"); toast("Đã xoá cache âm thanh"); }));
$("#gameCfg").addEventListener("submit", run(async (e) => {
  e.preventDefault();
  const game = Object.fromEntries(new FormData(e.target).entries());
  await api("/api/config", "PUT", { game }); toast("Đã lưu cài đặt ✓");
}));
$("#copyUrl").addEventListener("click", run(async () => { await navigator.clipboard.writeText($("#overlayUrl").value); toast("Đã chép link"); }));

const mock = (body) => api("/api/mock", "POST", body);
$("#mSend").addEventListener("click", run(async () => mock({ type: "comment", name: $("#mName").value, text: $("#mText").value })));
document.querySelectorAll("[data-mock]").forEach((b) => b.addEventListener("click", run(async () => {
  const k = b.dataset.mock, name = $("#mName").value;
  if (k === "random") {
    for (const n of MOCK_NAMES.slice(0, 10).sort(() => Math.random() - .5))
      await mock({ type: "comment", name: n, text: "ABCD"[Math.floor(Math.random() * 4)] });
  } else if (k === "gift") await mock({ type: "gift", name, count: 1, gift_name: "Hoa hồng", diamonds: 1 });
  else if (k === "gift-big") await mock({ type: "gift", name, count: 1, gift_name: "Bánh donut", diamonds: 30 });
  else if (k === "gift-huge") await mock({ type: "gift", name, count: 1, gift_name: "Sư tử", diamonds: 100 });
  else if (k === "team") {
    for (const [i, n] of MOCK_NAMES.slice(0, 10).entries()) await mock({ type: "comment", name: n, text: i % 2 ? "đội xanh" : "đội đỏ" });
  }
  else if (k === "like") await mock({ type: "like", name, count: 100 });
  else await mock({ type: k, name });
  refresh();
})));

$("#loadStats").addEventListener("click", run(async () => {
  const st = await api("/api/stats");
  if (!st.recent.length) { $("#stats").textContent = "Chưa có dữ liệu. Chơi vài câu rồi tải lại."; return; }
  const row = (cells, tag = "td") => "<tr>" + cells.map((c) => `<${tag}>${esc(c)}</${tag}>`).join("") + "</tr>";
  $("#stats").innerHTML = `<b>Trung bình theo kiểu câu (500 câu gần nhất)</b>
    <table class="tbl">${row(["Kiểu", "Số câu", "Trả lời/câu", "Comment/câu", "Người xem", "% đúng"], "th")}
    ${st.by_kind.map((k) => row([KIND[k.kind] || k.kind, k.rounds, k.answered, k.comments, k.viewers, k.correct_pct + "%"])).join("")}</table>
    <b>20 câu gần nhất</b>
    <table class="tbl">${row(["Lúc", "Kiểu", "Trả lời", "Đúng", "Comment", "Người xem"], "th")}
    ${st.recent.map((r) => row([r.at.slice(11, 16), KIND[r.special || r.mode] || r.mode, r.answered, r.correct, r.comments, r.viewers])).join("")}</table>`;
}));

$("#aiSave").addEventListener("click", run(async () => {
  await api("/api/config", "PUT", {
    ai: { provider: $("#aiProvider").value, model_deepseek: $("#aiModelDs").value, model_openai: $("#aiModelOa").value, verify: $("#aiVerify").value },
    deepseek_key: $("#aiDsKey").value || null, openai_key: $("#aiOaKey").value || null,
  });
  $("#aiDsKey").value = $("#aiOaKey").value = ""; formLoaded = false; toast("Đã lưu ✓");
}));
$("#aiGen").addEventListener("click", run(async () => {
  await api("/api/ai/generate", "POST", { n: +$("#aiN").value || 30, redo: $("#aiRedo").checked }); refresh();
}));
$("#aiClear").addEventListener("click", run(async () => {
  if (!confirm("Xoá hết câu hỏi AI đã tạo?")) return;
  await api("/api/ai/clear", "POST"); refresh();
}));
