"use strict";
/* Overlay "sân khấu game show": hỏi trạng thái server mỗi 400ms rồi vẽ lại.
   Hiệu ứng (màn giới thiệu câu, pháo giấy, âm thanh) chỉ chạy khi trạng thái ĐỔI (câu mới, hiện đáp án, vào bảng…),
   không chạy lại mỗi lần vẽ. Nội dung chỉ nằm trong vùng an toàn --st%…--sb% (xem overlay.css). */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const params = new URLSearchParams(location.search);
const K = params.get("k") || "";
const q = (path) => path + (path.includes("?") ? "&" : "?") + "k=" + encodeURIComponent(K);
if (params.get("bg") === "0") document.body.classList.add("transparent");
const L = "ABCD";
const snd = $("#snd");
const TEAM_ICON = { red: "🔴", blue: "🔵" };
let last = { sound: "" }, feedSeq = -1, cfg = null, prev = null;

/* ---------------------------------------------------------------- âm thanh từ vựng */
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
const sfx = (name, ...a) => { if (cfg && cfg.sfx) SFX[name](...a); };

/* ---------------------------------------------------------------- avatar */
const COLORS = ["#ff5d97", "#7b5cff", "#20c39a", "#ffb020", "#4fa8ff", "#ff6b6b", "#b05cff"];
function hue(name) { let h = 0; for (const c of String(name)) h = (h * 31 + c.codePointAt(0)) >>> 0; return COLORS[h % COLORS.length]; }
function avatar(p, size, extra = "") {
  const init = esc([...String(p.name || "?").trim()][0] || "?").toUpperCase();
  const img = p.avatar ? `<img src="${esc(p.avatar)}" referrerpolicy="no-referrer" alt="" onerror="this.remove()">` : "";
  return `<span class="av" style="--bgc:${hue(p.name)};${size ? `--s:${size};` : ""}"><span style="position:absolute">${init}</span>${img}${extra}</span>`;
}

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
    sfx("sparkle");
    if (tier >= 3) confetti(60);
  } else {
    box.innerHTML = `<div class="a-text">${esc(f.text)}</div>`;
    if (f.kind === "goal" || f.kind === "like") { sfx("fanfare"); confetti(40); }
  }
  box.className = `alert t${tier} k-${f.kind}`;
  setTimeout(nextAlert, tier >= 3 ? 3800 : 2400);
}

function confetti(n = 50) {
  const box = $("#confetti");
  const colors = ["#ff3d7f", "#7b5cff", "#ffe066", "#20c39a", "#4fa8ff", "#fff"];
  for (let i = 0; i < n; i++) {
    const c = document.createElement("i");
    c.style.left = Math.random() * 100 + "%";
    c.style.background = colors[i % colors.length];
    c.style.animationDuration = 1.6 + Math.random() * 1.6 + "s";
    c.style.animationDelay = Math.random() * 0.4 + "s";
    box.appendChild(c);
    setTimeout(() => c.remove(), 3800);
  }
}

function splash(no, kind, cls = "") {
  const el = $("#splash");
  el.className = "splash hidden";
  el.innerHTML = `<div class="no">${esc(no)}</div><div class="kind">${esc(kind)}</div>`;
  void el.offsetWidth;
  el.className = "splash " + cls;
  clearTimeout(splash.t);
  splash.t = setTimeout(() => el.classList.add("hidden"), 1450);
}

/* ---------------------------------------------------------------- mẹo chơi luân phiên (làn bot) */
function tips() {
  if (!cfg) return [];
  const t = ["<b>Comment A / B / C / D</b> để trả lời · gõ <b>điểm</b> để xem hạng",
    "⚡ Trả lời nhanh được thêm điểm · đúng liên tiếp 3 câu có thưởng chuỗi 🔥"];
  t.push(`🎁 Tặng quà = loại 1 đáp án sai · quà từ ${cfg.gift_big}💎 thêm 10 giây cho cả phòng`);
  if (cfg.round_len) t.push(`🏁 Mỗi vòng ${cfg.round_len} câu, câu cuối x3 điểm · cao điểm nhất vòng làm <b>Vua vòng 👑</b>`);
  if (cfg.like_goal) t.push(`❤️ Thả tim đủ ${cfg.like_goal} = câu sau <b>x2 điểm</b>`);
  if (cfg.gift_goal) t.push(`💎 Cả phòng đủ ${cfg.gift_goal} kim cương = mở <b>CÂU BOSS x3</b>`);
  if (cfg.teams) t.push("🔴🔵 Gõ <b>đội đỏ</b> hoặc <b>đội xanh</b> để vào đội");
  if (cfg.bot && cfg.bot_ai) t.push("🐰 Gõ <b>bot ơi …</b> để hỏi Hami về tiếng Hàn");
  t.push("➕ Theo dõi kênh để không bỏ lỡ buổi học tiếng Hàn sau nhé!");
  return t;
}
let tipIdx = 0;
function rotateTip() {
  const t = tips();
  if (!t.length) return;
  const el = $("#tips");
  el.classList.remove("in"); void el.offsetWidth;
  el.innerHTML = `<span>${t[tipIdx++ % t.length]}</span>`;   // bọc span: flex không nuốt khoảng trắng quanh <b>
  el.classList.add("in");
}
setInterval(rotateTip, 6000);

/* dải "vừa trả lời": giữ phần tử cũ, chỉ thêm người mới để hiệu ứng trượt vào không chạy lại */
let tickQ = 0, tickSeq = 0;
function renderTicker(s) {
  const box = $("#ticker"), rows = s.phase === "question" ? s.recent_ans || [] : [];
  const qid = s.question && s.phase === "question" ? s.question.id : 0;
  if (qid !== tickQ) { box.innerHTML = ""; tickQ = qid; tickSeq = 0; }
  for (const r of rows) {
    if (r.seq <= tickSeq) continue;
    const d = document.createElement("div");
    d.className = "tick";
    d.innerHTML = `${avatar(r)}<span class="nm">${esc(r.name)}</span>${cfg.live_counts ? `<em>${esc(r.letter)}</em>` : "⚡"}`;
    box.prepend(d);
    tickSeq = r.seq;
  }
  while (box.children.length > 4) box.lastChild.remove();
  $("#lane").classList.toggle("has-ticker", box.children.length > 0);
}

/* ---------------------------------------------------------------- HUD */
function renderHud(s) {
  const R = s.round_info, Q = s.question;
  if (R && R.len) {
    const final = Q && Q.special === "final" && s.phase !== "board";
    $("#round").innerHTML = `<span>Vòng ${R.no}</span><span class="bar"><i style="width:${(Math.min(R.q, R.len) / R.len) * 100}%"></i></span>
      <span class="${final ? "final" : ""}">${final ? "🏁 CHUNG KẾT" : `Câu ${R.q}/${R.len}`}</span>`;
  } else $("#round").innerHTML = `<span>Câu ${s.round + (s.phase === "question" ? 1 : 0)}</span><span class="bar"><i style="width:0"></i></span>`;
  const G = s.goals, out = [];
  const chip = (cls, x, text, hot) => out.push(`<div class="chip ${cls}${hot ? " hot" : ""}"><i style="width:${Math.min(1, x) * 100}%"></i><span>${text}</span></div>`);
  if (G.likes.goal) chip("", s.double_next ? 1 : G.likes.progress, s.double_next ? "❤️ x2 câu sau!" : `❤️ ${G.likes.value}/${G.likes.goal}`, s.double_next);
  else chip("", 0, `❤️ ${s.likes}`);
  if (G.diamonds.goal) chip("dia", s.next_special === "boss" ? 1 : G.diamonds.progress,
    s.next_special === "boss" ? "👹 Sắp BOSS!" : `💎 ${G.diamonds.value}/${G.diamonds.goal}`, s.next_special === "boss");
  if (G.shares.goal) chip("share", G.shares.progress, `🔁 ${G.shares.value}/${G.shares.goal}`);
  const t = s.teams;
  if (t && (t.red.members || t.blue.members)) {
    const r = t.red.score + t.blue.score ? t.red.score / (t.red.score + t.blue.score) : 0.5;
    chip("team", r, `🔴 ${t.red.score} · ${t.blue.score} 🔵`);
  }
  $("#chips").innerHTML = out.join("");
}

/* ---------------------------------------------------------------- câu hỏi + đáp án */
const ASK = { ko2vi: "Từ này nghĩa là gì?", vi2ko: "Tiếng Hàn là gì?", cloze: "Điền vào chỗ trống",
  trans: "Câu này nghĩa là gì?", hanviet: "Âm Hán Việt là gì?" };
const KIND = { ko2vi: "Hàn → Việt", vi2ko: "Việt → Hàn", cloze: "🧩 Điền chỗ trống", trans: "📝 Dịch câu", hanviet: "🈶 Hán Việt" };
const OPT_LANG = { ko2vi: "vi", vi2ko: "ko", cloze: "ko", trans: "vi", hanviet: "vi" };
const BLANK = "＿＿＿";
function promptHtml(Q) {
  if (Q.mode !== "cloze") return esc(Q.prompt);
  return esc(Q.prompt).replace(BLANK, `<span class="blank">${BLANK}</span>`);
}
function badge(Q) {
  if (Q.special === "final") return `<span class="badge final">🏁 CHUNG KẾT x${Q.mult}</span>`;
  if (Q.special === "boss") return `<span class="badge boss">👹 BOSS x${Q.mult}</span>`;
  if (Q.special === "listen") return `<span class="badge listen">🎧 NGHE${Q.double ? " · x2" : ""}</span>`;
  if (Q.double) return `<span class="badge x2">x2 ĐIỂM</span>`;
  return "";
}
function ring(s) {
  const frac = s.duration ? Math.max(0, Math.min(1, s.remaining / s.duration)) : 0, C = 2 * Math.PI * 42;
  return `<div class="ring${s.remaining <= 5 ? " low" : ""}"><svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="42"/>
    <circle class="fg" cx="50" cy="50" r="42" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - frac)}"/></svg><b>${Math.ceil(s.remaining)}</b></div>`;
}

function renderQuestion(s) {
  const Q = s.question, reveal = s.phase === "reveal";
  const counts = Q.counts, total = counts ? Math.max(1, counts.reduce((a, b) => a + b, 0)) : 1;
  const sentence = Q.mode === "cloze" || Q.mode === "trans", long = Q.mode === "trans";
  const opts = Q.options.map((o, i) => {
    const c = counts ? counts[i] : 0;
    return `<div class="opt ${OPT_LANG[Q.mode] || "vi"}${!reveal && Q.hints.includes(i) ? " out" : ""}">
      ${counts ? `<span class="fill" style="width:${(c / total) * 100}%"></span>` : ""}
      <span class="l">${L[i]}</span><span class="t">${esc(o)}</span>
      ${counts && c ? `<span class="cnt">${Math.round((c / total) * 100)}%</span>` : ""}</div>`;
  }).join("");
  if (!reveal) {
    return `<div class="card ${Q.special ? "sp-" + Q.special : ""}">
        ${ring(s)}
        <div class="qhead"><span class="tag">${Q.listen ? "🎧 Nghe" : KIND[Q.mode] || ""}</span>${badge(Q)}</div>
        <div class="prompt ${Q.listen ? "listen" : Q.prompt_lang}${sentence ? " sent" : ""}">${promptHtml(Q)}</div>
        ${Q.hint ? `<div class="hint">${Q.mode === "hanviet" ? "Nghĩa: " : "💬 "}${esc(Q.hint)}</div>` : ""}
        <div class="meta">${Q.sponsor ? `💎 Tài trợ bởi <b class="sp">${esc(Q.sponsor)}</b>` : ASK[Q.mode] || ""} · ${Q.answered} người đã chọn${Q.extra ? ` · <b class="extra">+${Q.extra}s nhờ quà</b>` : ""}</div>
      </div>
      <div class="opts${long ? " long" : ""}">${opts}</div>`;
  }
  const w = Q.word, r = Q.result, right = Q.options[Q.answer];
  return `<div class="card reveal ${Q.special ? "sp-" + Q.special : ""}">
      <div class="qhead"><span class="tag">✅ Đáp án</span>${badge(Q)}</div>
      <div class="ko">${esc(w.korean)}</div>
      ${w.hanviet || w.pos ? `<div class="sub">${[w.hanviet ? `<span class="hv">${esc(w.hanviet)}</span>` : "", esc(w.pos || "")].filter(Boolean).join(" · ")}</div>` : ""}
      <div class="vi">${esc(w.vietnamese)}</div>
      ${w.example_ko ? `<div class="ex${sentence ? " focus" : ""}"><div class="k">${esc(w.example_ko)}</div><div>${esc(w.example_vi)}</div></div>` : ""}
    </div>
    <div class="result"><span class="ok"><span class="l">${L[Q.answer]}</span><span>${esc(right)}</span></span>
      <span class="st">${r.correct}/${r.total} đúng</span></div>
    ${r.fastest.length ? `<div class="winners">${r.fastest.map((f, i) => {
      const p = s.top.find((t) => t.name === f.name) || {};
      return `<div class="win">${avatar({ ...p, name: f.name }, "calc(var(--u) * 7)", `<span class="medal">${["🥇", "🥈", "🥉"][i]}</span>`)}
        <span class="nm">${esc(f.name)}</span><span class="pt">+${f.points}</span></div>`;
    }).join("")}</div>` : ""}`;
}

/* ---------------------------------------------------------------- bục vinh quang */
function podium(rows, key = "score") {
  const slot = (p, n) => p
    ? `<div class="pod p${n}">${avatar(p, n === 1 ? "calc(var(--u) * 11)" : "calc(var(--u) * 8.5)", p.crown || n === 1 ? `<span class="crown">👑</span>` : "")}
        <span class="nm">${esc(p.name)}</span><span class="pt">${p[key]} điểm</span><div class="base">${n}</div></div>`
    : `<div class="pod p${n} empty"><span class="nm">…</span><div class="base">${n}</div></div>`;
  return `<div class="podium">${slot(rows[1], 2)}${slot(rows[0], 1)}${slot(rows[2], 3)}</div>`;
}
function ranks(rows, from) {
  return rows.length ? `<ol class="ranks">${rows.map((p, i) => `<li><span class="rk">${from + i}</span>${avatar(p, "calc(var(--u) * 6)")}
    <span class="n">${p.team ? TEAM_ICON[p.team] + " " : ""}${p.crown ? "👑 " : ""}${esc(p.name)}</span><b>${p.score}</b></li>`).join("")}</ol>` : "";
}
function thanks(s) {   // 1 dòng gọn: Vua tuần + người tặng quà nhiều nhất phiên
  const parts = [];
  if (s.weekly[0]) parts.push(`👑 Vua tuần: <b>${esc(s.weekly[0].name)}</b>`);
  if (s.supporters.length) parts.push(`🎁 Cảm ơn ${s.supporters.slice(0, 2).map((p) => `<b>${esc(p.name)}</b> ${p.diamonds}💎`).join(", ")}`);
  return parts.length ? `<div class="thanks">${parts.join(" · ")}</div>` : "";
}
function renderVote(v) {
  const total = Math.max(1, v.counts.reduce((a, b) => a + b, 0));
  return `<div class="card"><div class="side-title">🗳 Chọn kiểu câu tiếp theo: comment <b>1 / 2 / 3</b></div>
    <div class="vopts">${v.options.map((o, i) => `<div class="vopt"><span class="fill" style="--h:${(v.counts[i] / total) * 100}%"></span>
      <span class="l">${i + 1}</span><span class="t">${esc(o.replace("Nghe đoán nghĩa", "🎧 Nghe"))}</span><b>${v.counts[i]} phiếu</b></div>`).join("")}</div></div>`;
}
function renderBoard(s) {
  const E = s.round_end;
  if (E) {
    return `<div class="card">
        <div class="board-title">🏁 Kết thúc vòng ${E.no}<small>Bảng điểm của vòng này</small></div>
        ${podium(E.podium)}
      </div>
      ${E.king ? `<div class="king">👑 Vua vòng ${E.no}: <b>${esc(E.king.name)}</b> · ${E.king.score} điểm · giữ vương miện cả vòng sau!</div>` : ""}`;
  }
  return `<div class="card">
      <div class="board-title">🏆 Bảng xếp hạng<small>sau ${s.round} câu</small></div>
      ${podium(s.top)}
      ${s.vote ? "" : ranks(s.top.slice(3, 5), 4)}
    </div>
    ${s.vote ? renderVote(s.vote) : thanks(s)}`;
}

function renderIdle(s) {
  return `<div class="idle card">
      <div class="ko">한국어 LIVE</div>
      <div class="big">Đoán nghĩa từ tiếng Hàn</div>
      <div style="color:var(--muted);font-weight:800">${esc(s.message && s.message !== "Tạm dừng" ? s.message : "Sắp bắt đầu, chờ chút nhé…")}</div>
      <div class="cta">COMMENT A / B / C / D ĐỂ CHƠI 👇</div>
    </div>`;
}

/* ---------------------------------------------------------------- bot + khung căn chỉnh */
let botSeq = -1;
Hami.mount($("#hami"), $("#hamiBubble"));
snd.addEventListener("play", () => Hami.speaking(true));
["pause", "ended", "error"].forEach((e) => snd.addEventListener(e, () => Hami.speaking(false)));

/* giọng Hami: audio riêng; nếu đang đọc từ vựng thì chờ đọc xong (tối đa 6 giây) để không chồng tiếng */
const botSnd = new Audio();
botSnd.preload = "auto";
botSnd.addEventListener("playing", () => {
  Hami.speaking(true);
  if (isFinite(botSnd.duration)) Hami.extend(botSnd.duration * 1000 + 600);
});
["pause", "ended", "error"].forEach((e) => botSnd.addEventListener(e, () => Hami.speaking(false)));
function botVoice(seq) {
  botSnd.src = q(`/audio/bot/${seq}.mp3`);
  const go = (tries) => {
    if (!snd.paused && !snd.ended && tries > 0) return setTimeout(() => go(tries - 1), 300);
    botSnd.play().catch(() => {});
  };
  go(20);
}

function renderBot(b) {
  $("#hami").classList.toggle("hidden", !b);
  if (!b) { $("#hamiBubble").classList.remove("show"); return; }
  Hami.base(b.mood);
  const fresh = botSeq >= 0;
  for (const l of b.lines) {
    if (l.seq <= botSeq) continue;
    botSeq = l.seq;
    if (fresh) Hami.say(l.text, l.mood, cfg.bot_voice ? () => botVoice(l.seq) : null);   // vừa mở overlay: không nói lại câu cũ
  }
  if (botSeq < 0) botSeq = 0;
}

function renderGuide() {
  if (params.get("guide") !== "1") return;
  const z = (t, l, w, h, label, soft) => `<div class="z${soft ? " soft" : ""}" style="top:${t}%;left:${l}%;width:${w}%;height:${h}%">${label}</div>`;
  $("#guide").innerHTML =
    z(0, 0, 100, 10, "TikTok: tên host · người xem · nút đóng") +
    z(10, 0, 45, 4, "Xếp hạng / sự kiện", true) +
    z(54, 0, 64, 7, "Banner quà TikTok", true) +
    z(62, 0, 74, 27, "Bình luận TikTok") +
    z(64, 84, 16, 25, "Tim bay", true) +
    z(90, 0, 100, 10, "Ô nhập · nút quà · chia sẻ") +
    `<div class="line" style="top:${cfg.safe_top}%">▲ safe_top ${cfg.safe_top}%</div>` +
    `<div class="line" style="top:${cfg.safe_bottom}%">▼ safe_bottom ${cfg.safe_bottom}%</div>`;
  $("#guide").classList.remove("hidden");
}

/* ---------------------------------------------------------------- hiệu ứng khi trạng thái đổi */
function transitions(s) {
  const Q = s.question, P = prev;
  prev = { phase: s.phase, qid: Q ? Q.id : 0, answered: Q ? Q.answered : 0, sec: Math.ceil(s.remaining) };
  if (!P) return false;                          // lần đầu mở overlay: không bắn hiệu ứng cũ
  let entered = false;
  if (s.phase === "question" && Q && Q.id !== P.qid) {
    entered = true;
    sfx("whoosh");
    const kind = Q.special === "final" ? "🏁 CHUNG KẾT VÒNG · x3" : Q.special === "boss" ? "👹 CÂU BOSS · x3"
      : Q.listen ? "🎧 Câu nghe" : KIND[Q.mode] || "";
    splash(Q.special === "final" ? "🏁" : `CÂU ${s.round_info && s.round_info.len ? s.round_info.q : s.round + 1}`, kind,
      Q.special === "final" ? "final" : "");
  }
  if (s.phase === "question" && Q && Q.id === P.qid) {
    if (Q.answered > P.answered) sfx("pop");
    const sec = Math.ceil(s.remaining);
    if (sec !== P.sec && sec >= 1 && sec <= 5) sfx("tick", sec <= 3);
  }
  if (s.phase === "reveal" && P.phase !== "reveal" && Q) {
    entered = true;
    if (Q.result && Q.result.correct) { sfx("ding"); if (Q.result.correct >= 3) confetti(30); } else sfx("buzz");
  }
  if (s.phase === "board" && P.phase !== "board") {
    entered = true;
    sfx("fanfare", !!s.round_end);
    confetti(s.round_end ? 90 : 40);
  }
  if (s.phase !== P.phase && s.phase === "idle") entered = true;
  return entered;
}

function render(s) {
  const first = cfg === null;
  cfg = s.config;
  if (first) rotateTip();
  // vùng an toàn tắt: dùng gần hết khung (vẫn chừa mép trên/dưới)
  document.documentElement.style.setProperty("--st", cfg.safe ? cfg.safe_top : 3);
  document.documentElement.style.setProperty("--sb", cfg.safe ? cfg.safe_bottom : 86);
  document.body.classList.add("safe");
  renderGuide();
  renderBot(s.bot);
  renderHud(s);
  renderTicker(s);
  const entered = transitions(s);
  const main = $("#main");
  $("#stage").dataset.phase = s.phase;
  if ((s.phase === "question" || s.phase === "reveal") && s.question) main.innerHTML = renderQuestion(s);
  else if (s.phase === "board") main.innerHTML = renderBoard(s);
  else main.innerHTML = renderIdle(s);
  if (entered) {
    main.classList.remove("enter"); void main.offsetWidth; main.classList.add("enter");
    clearTimeout(render.t); render.t = setTimeout(() => main.classList.remove("enter"), 900);
  }

  // thông báo lớn: chỉ dòng mới; lần đầu mở overlay không bật lại thông báo cũ
  const fresh = feedSeq >= 0;
  for (const f of s.feed) {
    if (f.seq <= feedSeq) continue;
    feedSeq = f.seq;
    if (fresh && f.alert) pushAlert(f);
  }
  if (feedSeq < 0) feedSeq = 0;

  // âm thanh: câu mới -> đọc đề (sau màn giới thiệu); quà lớn -> đọc lại đề; hiện đáp án -> bản 2 luồng
  const Q = s.question;
  if (Q) {
    const key = Q.id + ":" + s.phase + ":" + (s.phase === "question" ? Q.replay : 0);
    if (key !== last.sound) {
      last.sound = key;
      if (s.phase === "question" && Q.audio_q) setTimeout(() => play(`/audio/${Q.word_id}/${Q.audio_q}.mp3`), 700);
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
