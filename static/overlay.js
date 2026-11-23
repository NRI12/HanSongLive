"use strict";
/* Overlay: hỏi trạng thái server mỗi 400ms, vẽ lại, phát âm thanh khi đổi câu / hiện đáp án,
   hiện thông báo lớn (quà, chuỗi đúng, đạt mốc) và banner hướng dẫn luân phiên. */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const params = new URLSearchParams(location.search);
const K = params.get("k") || "";
const q = (path) => path + (path.includes("?") ? "&" : "?") + "k=" + encodeURIComponent(K);
if (params.get("bg") === "0") document.body.classList.add("transparent");
const L = "ABCD";
const snd = $("#snd");
const TEAM_ICON = { red: "🔴", blue: "🔵" };
let last = { sound: "" }, feedSeq = -1, cfg = null;

function play(url) {
  snd.src = q(url);
  // Không hiện nút trên màn live; lỗi thoáng qua (mạng, file đang tải) thì thử lại một lần.
  const src = snd.src;
  snd.play().catch(() => setTimeout(() => {
    if (snd.src !== src) return;      // đã sang âm thanh khác
    snd.load();                       // tải lại sau lỗi mạng/500
    snd.play().catch(() => {});
  }, 1000));
}
// Trình duyệt chặn tự phát: bấm vào bất kỳ đâu trên trang để mở khoá âm thanh.
document.addEventListener("click", () => { if (snd.paused && !snd.ended && snd.src) snd.play().catch(() => {}); });

/* ---------------------------------------------------------------- thông báo lớn */
const alerts = [];
let alertBusy = false;
function pushAlert(f) {
  if (alerts.length >= 4) alerts.shift();          // phòng đông: bỏ bớt thông báo cũ chưa kịp hiện
  alerts.push(f);
  if (!alertBusy) nextAlert();
}
function nextAlert() {
  const f = alerts.shift(), box = $("#alert");
  if (!f) { alertBusy = false; box.className = "alert hidden"; return; }
  alertBusy = true;
  const tier = f.tier || 1;
  if (f.kind === "gift") {
    box.innerHTML = `<div class="a-icon">${tier >= 3 ? "💎" : "🎁"}</div>
      <div class="a-name">${esc(f.who)}</div>
      <div class="a-sub">tặng ${esc(f.gift)} ×${f.count}</div>
      <div class="a-thanks">${tier >= 3 ? "Cảm ơn nhà tài trợ! 🙇" : "Cảm ơn bạn! 💖"}</div>
      <div class="a-fx">${esc(f.text.split("→")[1] || "")}</div>`;
  } else {
    box.innerHTML = `<div class="a-text">${esc(f.text)}</div>`;
  }
  box.className = `alert t${tier} k-${f.kind}`;
  setTimeout(nextAlert, tier >= 3 ? 3800 : 2400);
}

/* ---------------------------------------------------------------- banner luân phiên */
function tips() {
  if (!cfg) return [];
  const t = ["<b>Comment A / B / C / D</b> để trả lời · gõ <b>điểm</b> để xem hạng",
    "⚡ Trả lời nhanh được thêm điểm · đúng liên tiếp 3 câu trở lên có thưởng chuỗi 🔥"];
  t.push(`🎁 Tặng quà = loại 1 đáp án sai · quà từ ${cfg.gift_big}💎 thêm 10 giây cho cả phòng`);
  if (cfg.gift_huge) t.push(`💎 Quà từ ${cfg.gift_huge}💎 = tên bạn là <b>nhà tài trợ</b> câu kế tiếp`);
  if (cfg.like_goal) t.push(`❤️ Thả tim đủ ${cfg.like_goal} = câu sau <b>x2 điểm</b>`);
  if (cfg.share_goal) t.push(`🔁 Chia sẻ live đủ ${cfg.share_goal} lượt = câu sau <b>x2 điểm</b>`);
  if (cfg.gift_goal) t.push(`💎 Cả phòng đủ ${cfg.gift_goal} kim cương = mở <b>CÂU BOSS x3</b>`);
  if (cfg.teams) t.push("🔴🔵 Gõ <b>đội đỏ</b> hoặc <b>đội xanh</b> để vào đội, điểm của bạn cộng cho đội");
  if (cfg.boss_every) t.push(`👹 Cứ ${cfg.boss_every} câu có 1 <b>CÂU BOSS</b> x3 điểm`);
  if (cfg.listen_every) t.push(`🎧 Cứ ${cfg.listen_every} câu có 1 <b>câu nghe</b>: chỉ nghe, không nhìn chữ`);
  if (cfg.vote && cfg.board_every) t.push("🗳 Lúc hiện bảng xếp hạng: comment <b>1 / 2 / 3</b> để chọn kiểu câu tiếp theo");
  t.push("➕ Theo dõi kênh để không bỏ lỡ buổi học tiếng Hàn sau nhé!");
  return t;
}
let tipIdx = 0;
function rotateTip() {
  const t = tips();
  if (t.length) {
    const el = $("#help");
    el.classList.remove("in"); void el.offsetWidth;
    el.innerHTML = t[tipIdx++ % t.length];
    el.classList.add("in");
  }
}
setInterval(rotateTip, 6000);

/* ---------------------------------------------------------------- render */
function topList(rows, valueKey = "score", unit = "") {
  return rows.map((p) => `<li><span class="n">${p.team ? TEAM_ICON[p.team] + " " : ""}${esc(p.name)}</span><b>${p[valueKey]}${unit}</b></li>`).join("")
    || `<li><span class="n" style="color:var(--muted)">Chưa có ai</span></li>`;
}

function badge(Q) {
  const b = [];
  if (Q.special === "boss") b.push(`<span class="x2 boss">👹 BOSS x${Q.mult}</span>`);
  else if (Q.double) b.push(`<span class="x2">x2 ĐIỂM</span>`);
  if (Q.special === "listen") b.push(`<span class="x2 listen">🎧 NGHE</span>`);
  return b.join(" ");
}

function renderQuestion(s) {
  const Q = s.question, reveal = s.phase === "reveal";
  const pct = s.duration ? Math.max(0, Math.min(100, (s.remaining / s.duration) * 100)) : 0;
  const counts = Q.counts;
  const total = counts ? Math.max(1, counts.reduce((a, b) => a + b, 0)) : 1;
  const ask = Q.listen ? "Nghe và chọn nghĩa đúng" : ASK[Q.mode] || "Chọn đáp án đúng";
  const optLang = OPT_LANG[Q.mode] || "vi";
  const sentence = Q.mode === "cloze" || Q.mode === "trans";
  const opts = Q.options.map((o, i) => {
    let cls = "opt " + optLang;
    if (reveal) cls += i === Q.answer ? " right" : " wrong";
    else if (Q.hints.includes(i)) cls += " out";
    const c = counts ? counts[i] : 0;
    return `<div class="${cls}"><span class="l">${L[i]}</span><span class="t">${esc(o)}</span>
      ${counts ? `<span class="bar" style="width:${(c / total) * 100}%"></span><span class="pct">${Math.round((c / total) * 100)}% · ${c}</span>` : ""}</div>`;
  }).join("");
  const sponsor = Q.sponsor ? `<div class="sponsor">💎 Câu này được tài trợ bởi <b>${esc(Q.sponsor)}</b></div>` : "";
  if (!reveal) {
    const hot = s.hot.length ? s.hot.map((p) => `<span class="hot">🔥 ${esc(p.name)} <b>${p.streak}</b></span>`).join("") : "";
    let body = `<div class="card ${Q.special ? "sp-" + Q.special : ""}">
      <div class="qhead"><span>Câu ${s.round + 1} · ${ask}</span>${badge(Q)}</div>
      <div class="prompt ${Q.listen ? "listen" : Q.prompt_lang}${sentence ? " sent" : ""}">${promptHtml(Q)}</div>
      ${Q.hint ? `<div class="hint">${Q.mode === "hanviet" ? "Nghĩa: " : "💬 "}${esc(Q.hint)}</div>` : ""}
      <div class="timer ${s.remaining < 5 ? "low" : ""}"><i style="width:${pct}%"></i></div>
      <div class="sub">⏱ ${Math.ceil(s.remaining)} giây${Q.extra ? ` <b class="extra">+${Q.extra}s nhờ quà</b>` : ""} · ${Q.answered} người đã trả lời</div>
    </div>
    ${sponsor}
    <div class="opts${Q.mode === "trans" ? " long" : ""}">${opts}</div>`;
    if (s.top.length || hot) body += `<div class="mini-top">${hot}${s.top.slice(0, 4).map((p, i) => `<span>${i + 1}. ${esc(p.name)} <b>${p.score}</b></span>`).join("")}</div>`;
    return body;
  }
  const w = Q.word, r = Q.result;
  return `<div class="card reveal ${Q.special ? "sp-" + Q.special : ""}">
      <div class="qhead"><span>Đáp án câu ${s.round}</span>${badge(Q)}</div>
      <div class="ko">${esc(w.korean)}</div>
      ${w.hanviet || w.pos ? `<div class="sub">${[w.hanviet ? `<span class="hv">${esc(w.hanviet)}</span>` : "", esc(w.pos || "")].filter(Boolean).join(" · ")}</div>` : ""}
      <div class="vi">${esc(w.vietnamese)}</div>
      ${w.example_ko ? `<div class="ex${sentence ? " focus" : ""}"><div class="k">${esc(w.example_ko)}</div><div>${esc(w.example_vi)}</div></div>` : ""}
    </div>
    <div class="opts compact${Q.mode === "trans" ? " long" : ""}">${opts}</div>
    <div class="reveal">
      ${r.fastest.length ? `<div class="fast">${r.fastest.map((f, i) => `<span>${["🥇", "🥈", "🥉"][i]} ${esc(f.name)} +${f.points}</span>`).join("")}</div>` : ""}
      <div class="stat">${r.correct}/${r.total} người trả lời đúng</div>
    </div>`;
}

const ASK = { ko2vi: "Từ này nghĩa là gì?", vi2ko: "Tiếng Hàn của từ này là gì?", cloze: "Điền vào chỗ trống",
  trans: "Câu này nghĩa là gì?", hanviet: "Âm Hán Việt của từ này?" };
const OPT_LANG = { ko2vi: "vi", vi2ko: "ko", cloze: "ko", trans: "vi", hanviet: "vi" };
const BLANK = "＿＿＿";
function promptHtml(Q) {
  if (Q.mode !== "cloze") return esc(Q.prompt);
  return esc(Q.prompt).replace(BLANK, `<span class="blank">${BLANK}</span>`);
}

function renderVote(v) {
  const total = Math.max(1, v.counts.reduce((a, b) => a + b, 0));
  return `<div class="card vote"><div class="side-title">🗳 Chọn kiểu câu tiếp theo: comment <b>1 / 2 / 3</b></div>
    <div class="vopts">${v.options.map((o, i) => `<div class="vopt"><span class="bar" style="width:${(v.counts[i] / total) * 100}%"></span>
      <span class="l">${i + 1}</span><span class="t">${esc(o)}</span><b>${v.counts[i]}</b></div>`).join("")}</div></div>`;
}

function renderBoard(s) {
  const rec = s.all_time[0];
  const fan = s.weekly_fans[0];
  return `<div class="card big">
      <div class="board-title">🏆 Bảng xếp hạng sau ${s.round} câu</div>
      <ol class="top">${topList(s.top.slice(0, s.vote ? 4 : 6))}</ol>
      ${rec ? `<div class="record">🌟 Kỷ lục mọi thời đại: <b>${esc(rec.name)}</b> ${rec.score} điểm</div>` : ""}
    </div>
    ${s.vote ? renderVote(s.vote) : ""}
    <div class="cols">
      <div class="card"><div class="side-title">👑 Vua tuần này</div><ol class="top">${topList(s.weekly.slice(0, 3))}</ol></div>
      <div class="card"><div class="side-title">🎁 Cảm ơn đã tặng quà</div><ol class="top">${topList(s.supporters.slice(0, 3), "diamonds", "💎")}</ol>
        ${fan ? `<div class="record small">💖 Fan cứng tuần: <b>${esc(fan.name)}</b></div>` : ""}</div>
    </div>`;
}

function renderIdle(s) {
  return `<div class="idle card">
      <div class="ko">한국어</div>
      <div style="font-size:1.4em;font-weight:800">Đoán nghĩa từ tiếng Hàn</div>
      <div class="sub">${esc(s.message && s.message !== "Tạm dừng" ? s.message : "Sắp bắt đầu, chờ chút nhé…")}</div>
      <div>Comment <b>A / B / C / D</b> để trả lời.<br>Trả lời nhanh được thêm điểm, đúng liên tiếp có thưởng chuỗi.</div>
      ${s.teams ? `<div>Gõ <b>đội đỏ</b> hoặc <b>đội xanh</b> để vào đội 🔴🔵</div>` : ""}
    </div>`;
}

function renderGoals(s) {
  const G = s.goals, out = [];
  const g = (icon, x, text) => out.push(`<div class="goal"><i style="width:${x.progress * 100}%"></i><span>${icon} ${text}</span></div>`);
  if (G.likes.goal) g("❤️", s.double_next ? { progress: 1 } : G.likes, s.double_next ? "x2 câu sau!" : `${G.likes.value}/${G.likes.goal}`);
  else g("❤️", { progress: 0 }, String(s.likes));
  if (G.diamonds.goal) g("💎", s.next_special === "boss" ? { progress: 1 } : G.diamonds, s.next_special === "boss" ? "Sắp có BOSS!" : `${G.diamonds.value}/${G.diamonds.goal} → BOSS`);
  if (G.shares.goal) g("🔁", G.shares, `${G.shares.value}/${G.shares.goal} → x2`);
  return out.join("");
}

function renderTeams(t) {
  if (!t || (!t.red.members && !t.blue.members)) return "";
  const sum = Math.max(1, t.red.score + t.blue.score);
  const r = t.red.score || t.blue.score ? (t.red.score / sum) * 100 : 50;
  return `<div class="teams"><i style="width:${r}%"></i>
    <span>🔴 Đỏ <b>${t.red.score}</b> <small>(${t.red.members})</small></span>
    <span><small>(${t.blue.members})</small> <b>${t.blue.score}</b> Xanh 🔵</span></div>`;
}

function render(s) {
  const first = cfg === null;
  cfg = s.config;
  if (first) rotateTip();
  $("#viewers").textContent = "👀 " + s.viewers;
  $("#players").textContent = "🙋 " + s.players;
  $("#goals").innerHTML = renderGoals(s);
  $("#teams").innerHTML = renderTeams(s.teams);
  const main = $("#main");
  $("#stage").dataset.phase = s.phase;
  $("#stage").dataset.special = (s.question && s.question.special) || "";
  $("#stage").dataset.mode = (s.question && s.question.mode) || "";
  if ((s.phase === "question" || s.phase === "reveal") && s.question) main.innerHTML = renderQuestion(s);
  else if (s.phase === "board") main.innerHTML = renderBoard(s);
  else main.innerHTML = renderIdle(s);

  // feed: chỉ thêm dòng mới; lần đầu mở overlay không bật lại thông báo cũ
  const feed = $("#feed"), fresh = feedSeq >= 0;
  for (const f of s.feed) {
    if (f.seq <= feedSeq) continue;
    feedSeq = f.seq;
    const d = document.createElement("div");
    d.className = f.kind + (f.tier ? " t" + f.tier : ""); d.textContent = f.text; feed.appendChild(d);
    if (fresh && f.alert) pushAlert(f);
  }
  if (feedSeq < 0) feedSeq = 0;
  while (feed.children.length > 3) feed.firstChild.remove();

  // âm thanh: câu mới -> đọc đề; quà lớn -> đọc lại đề; hiện đáp án -> bản 2 luồng (Việt trái / Hàn phải)
  const Q = s.question;
  if (Q) {
    const key = Q.id + ":" + s.phase + ":" + (s.phase === "question" ? Q.replay : 0);
    if (key !== last.sound) {
      last.sound = key;
      if (s.phase === "question" && Q.audio_q) play(`/audio/${Q.word_id}/${Q.audio_q}.mp3`);
      else if (s.phase === "reveal") play(`/audio/${Q.word_id}/${Q.audio_reveal || "mix"}.mp3`);
    }
  }
}

async function poll() {
  try {
    const r = await fetch(q("/api/overlay/state"), { credentials: "same-origin" });
    if (r.ok) render(await r.json());
    else if (r.status === 401) $("#main").innerHTML = `<div class="idle card">⚠️ Link overlay thiếu hoặc sai token.<br>Lấy lại link trong trang /admin.</div>`;
  } catch { /* mất mạng tạm thời: thử lại */ }
  setTimeout(poll, 400);
}
poll();
