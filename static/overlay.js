"use strict";
/* Overlay "Săn Quái Chữ": hỏi trạng thái server mỗi 400ms rồi vẽ lại.
   Sàn đấu (#arena: nền, quái, thanh máu, vòng đếm) là phần tử GIỮ NGUYÊN, chỉ cập nhật phần đổi -> hoạt cảnh quái
   (thở, bị đánh, ngã) không chạy lại mỗi lần vẽ. Các vùng khác dùng setHTML(): chỉ ghi DOM khi nội dung đổi.
   Hiệu ứng (quái xuất hiện, chuỗi đòn đánh, phản đòn, hạ gục) chỉ chạy khi trạng thái ĐỔI (transitions()).
   Nội dung chỉ nằm trong vùng an toàn --st%…--sb% (xem overlay.css). */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const params = new URLSearchParams(location.search);
const K = params.get("k") || "";
const q = (path) => path + (path.includes("?") ? "&" : "?") + "k=" + encodeURIComponent(K);
if (params.get("bg") === "0") document.body.classList.add("transparent");
const L = "ABCD";
const snd = $("#snd");
let last = { sound: "" }, feedSeq = -1, cfg = null, prev = null;
const anim = { hp: null, hearts: null, broken: 0, brokenAt: 0, busy: 0 };   // giá trị đang diễn hoạt cảnh (ghi đè state)
const timers = [];
const later = (ms, fn) => timers.push(setTimeout(fn, ms));
const clearTimers = () => { while (timers.length) clearTimeout(timers.pop()); };

function setHTML(el, html) { if (el._h !== html) { el.innerHTML = html; el._h = html; return true; } return false; }

/* ---------------------------------------------------------------- âm thanh từ vựng */
function play(url) {
  snd.src = q(url);
  const src = snd.src;
  snd.play().catch(() => setTimeout(() => {          // lỗi thoáng qua (mạng, file đang tải): thử lại một lần
    if (snd.src !== src) return;
    snd.load();
    snd.play().catch(() => {});
  }, 1000));
}
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
const lv = (p) => p && p.level ? `<span class="lv" title="${esc(p.title || "")}">${esc(p.icon || "")}${p.level}</span>` : "";

/* ---------------------------------------------------------------- dòng sự kiện (thay thông báo lớn giữa màn)
   Có thông báo (lên cấp, chuỗi, mốc tim, combo…) thì hiện lần lượt; rảnh thì hiện tiến độ mốc tim. */
const alerts = [];
let alertBusy = false, evtState = null;
function pushAlert(f) {
  if (alerts.length >= 4) alerts.shift();          // phòng đông: bỏ bớt thông báo cũ chưa kịp hiện
  alerts.push(f);
  if (!alertBusy) nextAlert();
}
function nextAlert() {
  const f = alerts.shift(), box = $("#evt"), txt = box.querySelector(".txt");
  if (!f) { alertBusy = false; evtIdle(); return; }
  alertBusy = true;
  const tier = f.tier || 1;
  box.className = `evt alert t${tier}`;
  box.querySelector(".bar").style.width = "0";
  txt.innerHTML = esc(f.text); txt._h = null;
  txt.style.animation = "none"; void txt.offsetWidth; txt.style.animation = "";
  if (f.kind === "record") { sfx("fanfare", true); confetti(60); } else sfx("sparkle");
  setTimeout(nextAlert, tier >= 3 ? 3200 : 2400);
}
function evtIdle(s) {
  if (s) evtState = s;
  s = evtState;
  if (alertBusy || !s || !cfg) return;
  const box = $("#evt"), G = s.goals;
  let html = "⚔️ Comment <b>A B C D</b> để ra đòn", w = 0, hot = false;
  if (s.phase === "flip") html = "🃏 Comment <b>2 số</b> để lật thẻ · vd. <b>3 8</b>";
  else if (s.double_next) { html = "💥 Câu sau <b>x2 sát thương</b>!"; hot = true; }
  else if (G.likes.goal) { html = `❤️ Thả tim <b>${G.likes.value}/${G.likes.goal}</b> → câu sau x2 sát thương`; w = G.likes.progress; }
  box.className = "evt" + (hot ? " hot" : "");
  setHTML(box.querySelector(".txt"), html);
  box.querySelector(".bar").style.width = w * 100 + "%";
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

function splash(no, kind, cls = "", how = "") {
  const el = $("#splash");
  el.className = "splash hidden";
  el.innerHTML = `<div class="no">${esc(no)}</div><div class="kind">${kind}</div>${how ? `<div class="how">${how}</div>` : ""}`;
  void el.offsetWidth;
  el.className = "splash " + cls;
  clearTimeout(splash.t);
  splash.t = setTimeout(() => el.classList.add("hidden"), 2000);
}
function flash(cls) {
  const el = $("#flash");
  el.className = "flash"; void el.offsetWidth; el.className = "flash " + cls;
}
function restart(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }

/* ---------------------------------------------------------------- mẹo chơi luân phiên (làn bot) */
function tips() {
  if (!cfg) return [];
  const t = ["<b>Comment A / B / C / D</b> để ra đòn · đúng = gây sát thương ⚔️",
    "⚡ Người đúng <b>đầu tiên</b> được CHÍ MẠNG",
    "💥 Dưới 50% cả phòng đúng thì quái <b>phản đòn</b>"];
  if (cfg.special_floors) t.push("🃏 Ải 2 <b>lật thẻ</b> · 🏎 Ải 3 <b>đua xe</b>");
  if (cfg.bot && cfg.bot_ai) t.push("🐰 Gõ <b>bot ơi …</b> để hỏi Hami");
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

/* dải "vừa ra đòn": giữ phần tử cũ, chỉ thêm người mới để hiệu ứng trượt vào không chạy lại */
let tickQ = 0, tickSeq = 0, tickReady = false;
function renderTicker(s) {
  const box = $("#ticker"), rows = s.phase === "question" ? s.recent_ans || [] : [];
  const qid = s.question && s.phase === "question" ? s.question.id : 0;
  if (qid !== tickQ) { box.innerHTML = ""; tickQ = qid; tickSeq = 0; }
  let flown = 0;
  for (const r of rows) {
    if (r.seq <= tickSeq) continue;
    const d = document.createElement("div");
    d.className = "tick" + (r.crown ? " king" : "") + (r.streak >= 3 ? " hot" : "");
    const badge = r.crown ? `<i class="b-crown">👑</i>` : r.streak >= 3 ? `<i class="b-fire">🔥${r.streak}</i>` : r.new ? `<i class="b-new">MỚI</i>` : "";
    d.innerHTML = `${avatar(r)}<span class="nm">${esc(r.name)}</span>${badge}${cfg.live_counts ? `<em>${esc(r.letter)}</em>` : "<em>⚔</em>"}`;
    box.prepend(d);
    tickSeq = r.seq;
    if (tickReady && flown < 6) shoot(d, r, flown++);   // mở overlay giữa câu: không bắn lại người cũ
  }
  tickReady = true;
  while (box.children.length > 4) box.lastChild.remove();
  $("#lane").classList.toggle("has-ticker", box.children.length > 0);
}

/* ---------------------------------------------------------------- hiệu ứng tương tác của người xem */
const rel = (el) => {     // toạ độ tâm phần tử, tính theo khung #stage
  const a = el.getBoundingClientRect(), b = $("#stage").getBoundingClientRect();
  return { x: a.left - b.left + a.width / 2, y: a.top - b.top + a.height / 2, w: a.width, h: a.height };
};
/* người vừa comment đáp án: avatar bay từ dải "vừa ra đòn" lên đập vào quái (ai cũng bay, không lộ đúng/sai) */
function shoot(tick, r, i) {
  const race = $("#board").classList.contains("l-race");
  const from = rel(tick.querySelector(".av")), mon = rel(race ? $("#track") : $("#mon"));
  const to = { x: mon.x + (Math.random() - .5) * mon.w * .35, y: mon.y - mon.h * (.05 + Math.random() * .25) };
  const o = document.createElement("div");
  o.className = "orb";
  o.innerHTML = avatar(r) + (r.crown ? `<i>👑</i>` : "");
  $("#fly").appendChild(o);
  const midX = (from.x + to.x) / 2 - 40, midY = Math.min(from.y, to.y) - 70 - Math.random() * 40;
  const dur = 620 + Math.random() * 120, delay = i * 110;
  const a = o.animate([
    { transform: `translate(${from.x}px, ${from.y}px) translate(-50%, -50%) scale(1)`, opacity: 1 },
    { transform: `translate(${midX}px, ${midY}px) translate(-50%, -50%) scale(1.25) rotate(-200deg)`, opacity: 1, offset: .5 },
    { transform: `translate(${to.x}px, ${to.y}px) translate(-50%, -50%) scale(.55) rotate(-400deg)`, opacity: .9 },
  ], { duration: dur, delay, easing: "cubic-bezier(.35, 0, .6, 1)", fill: "both" });
  a.onfinish = () => {
    o.remove();
    if (race) return;
    const a2 = $("#arena").getBoundingClientRect(), st = $("#stage").getBoundingClientRect();
    const px = ((to.x - (a2.left - st.left)) / a2.width) * 100, py = ((to.y - (a2.top - st.top)) / a2.height) * 100;
    fxAt(`<img src="/static/game/fx/star_06.png" alt="">`, "spark", px, py, 450);
    if (!anim.busy) $("#monInner").animate([{ transform: "none" }, { transform: "translateX(3%) scale(.96, 1.04)" }, { transform: "none" }],
      { duration: 220, easing: "ease-out" });
  };
}

function hearts(n) {
  const k = Math.min(9, 2 + Math.round(Math.log2(n + 1)));
  for (let i = 0; i < k; i++) {
    if ($("#board").classList.contains("l-race")) return;      // đua xe: không có ô quái
    const h = fxAt(["❤️", "💖", "💗", "💕"][i % 4], "heart", 90 + Math.random() * 7, 95, 2000);
    h.style.setProperty("--dx", (Math.random() * -26 - 4).toFixed(1));
    h.style.animationDelay = i * 0.09 + "s";
  }
}
let pulseSeq = -1;
function renderPulse(list) {
  const fresh = pulseSeq >= 0;
  for (const p of list || []) {
    if (p.seq <= pulseSeq) continue;
    pulseSeq = p.seq;
    if (!fresh) continue;                       // vừa mở overlay: không chạy lại hiệu ứng cũ
    if (p.kind === "combo") pushAlert({ text: `🔥 COMBO! ${p.n} người cùng ra đòn`, tier: p.n >= 20 ? 2 : 1, kind: "combo" });
    if (p.kind === "like") { hearts(p.n); restart($("#evt"), "bump"); }
  }
  if (pulseSeq < 0) pulseSeq = 0;
}

/* ---------------------------------------------------------------- ải lật thẻ */
let flipSeq = -1;
function renderFlip(s) {
  const F = s.flip, wrap = $("#flipWrap");
  if (!F || !wrap) return;
  if (wrap.dataset.board !== String(F.board) || wrap.children.length !== F.cards.length) {
    wrap.dataset.board = F.board;
    wrap.style.setProperty("--rows", Math.ceil(F.cards.length / 4));
    wrap.innerHTML = F.cards.map((c) => `<div class="fc"><div class="fc-in"><div class="fc-back">${c.n}</div><div class="fc-face"></div></div></div>`).join("");
  }
  F.cards.forEach((c, i) => {
    const el = wrap.children[i], key = c.state + "|" + (c.text || "");
    if (el._k === key) return;
    el._k = key;
    el.className = `fc s-${c.state}${c.lang ? " " + c.lang : ""}`;
    if (c.state !== "down") {
      el.querySelector(".fc-face").innerHTML = `<span class="t">${esc(c.text)}</span>${c.by ? avatar(c.by, "calc(var(--u) * 3.6)") : ""}`;
    }
  });
  const fresh = flipSeq >= 0;
  for (const e of F.log) {
    if (e.seq <= flipSeq) continue;
    flipSeq = e.seq;
    if (!fresh) continue;                         // vừa mở overlay: không diễn lại lượt lật cũ
    sfx("pop");
    if (!e.ok) continue;
    const at = rel(wrap.children[e.b]);
    const d = document.createElement("div");
    d.className = "fxi dmg crit";
    d.style.left = at.x + "px"; d.style.top = at.y + "px";
    d.innerHTML = `<b>−${e.dmg}</b><span>${avatar(e, "calc(var(--u) * 4.2)")}${esc(e.name)}</span>`;
    $("#fly").appendChild(d);
    setTimeout(() => d.remove(), 1300);
    restart($("#mon"), "hit"); slash(true);
    if (cfg.sfx) SFX.sample("crit", 0.6);
    if (e.wid) setTimeout(() => play(`/audio/${e.wid}/ko_word.mp3`), 350);   // lật trúng: đọc từ vừa ghép
  }
  if (flipSeq < 0) flipSeq = 0;
}

/* ---------------------------------------------------------------- ải đua xe: mỗi người một làn, xe quái làn trên cùng */
function renderTrack(s) {
  const T = $("#track"), R = s.race;
  const show = !!(R && (s.phase === "question" || s.phase === "reveal"));
  T.classList.toggle("hidden", !show);
  if (!show) return;
  const res = s.question && s.question.result && s.question.result.race;
  const view = s.phase === "reveal" && res ? res.after : R;       // lúc hiện đáp án: xe chạy tới vị trí mới (CSS transition)
  if (!T._init) {
    T._init = true;
    T.innerHTML = `<div class="tk-head"><span>🏁 Về đích trước để hạ quái</span><span id="tkMon"></span></div>
      <div class="lanes" id="lanes"><div class="ln mcar" id="lnMon"><span class="who"></span><div class="rd"><div class="car"><span>👹</span></div></div></div></div>
      <div class="fx" id="tfx"></div>`;
  }
  const pct = (d) => Math.max(0, Math.min(100, (d / view.finish) * 100)) * .94 + 3;
  const M = s.monster;
  setHTML($("#lnMon .who"), `👹 ${esc(M ? M.name : "Quái")}`);
  $("#lnMon .car").style.left = pct(view.mon) + "%";
  setHTML($("#tkMon"), `Xe quái: <b>${Math.round(view.mon)}/${view.finish}</b>`);
  const box = $("#lanes"), seen = new Set(["__mon"]);
  view.cars.slice(0, 5).forEach((c, i) => {
    seen.add(c.name);
    let el = [...box.children].find((x) => x._n === c.name);
    if (!el) {
      el = document.createElement("div");
      el.className = "ln"; el._n = c.name;
      el.innerHTML = `<span class="who"></span><div class="rd"><div class="car" style="left:3%">${avatar(c)}</div></div>`;
      box.appendChild(el);
    }
    setHTML(el.querySelector(".who"), `${i + 1}. ${esc(c.name)}`);
    el.classList.toggle("lead", i === 0);
    el.style.order = i + 1;
    requestAnimationFrame(() => { el.querySelector(".car").style.left = pct(c.dist) + "%"; });
  });
  $("#lnMon")._n = "__mon"; $("#lnMon").style.order = 0;
  for (const el of [...box.children]) if (!seen.has(el._n)) el.remove();
  let empty = $("#tkEmpty");
  if (!view.cars.length && !empty) { empty = document.createElement("div"); empty.id = "tkEmpty"; empty.className = "tk-empty"; empty.textContent = "Trả lời đúng là xe của bạn xuất phát! 🏎"; box.appendChild(empty); }
  if (view.cars.length && empty) empty.remove();
  if (empty) empty.style.order = 9;
}

/* ---------------------------------------------------------------- HUD */
const LAYOUT_TAG = { quiz: "⚔️ Ra đòn", duel: "🗡 Đối đầu", boss: "👹 BOSS", race: "🏎 Đua xe", flip: "🃏 Lật thẻ" };
function renderHud(s, layout) {
  const R = s.room, M = s.monster;
  const floor = M ? M.floor : R.floor;
  const hearts = anim.hearts ?? R.hearts;
  const breaking = Date.now() - anim.brokenAt < 1300;
  const hs = Array.from({ length: R.max_hearts }, (_, i) =>
    `<i class="${i < hearts ? "on" : "off"}${breaking && i >= hearts && i < hearts + anim.broken ? " break" : ""}">${i < hearts ? "❤️" : "🖤"}</i>`).join("");
  const tag = LAYOUT_TAG[layout];
  setHTML($("#hud"), `<div class="floor"><b>ẢI ${floor}</b><span>${esc(M ? M.zone_name : "Săn Quái Chữ")}</span></div>
    ${tag && s.phase !== "idle" ? `<span class="gtag${layout === "boss" ? " boss" : ""}">${tag}</span>` : ""}
    <div class="hearts${hearts <= 1 && s.phase !== "idle" ? " low" : ""}">${hs}</div>`);
}

/* kiểu bố cục của khu ải: mỗi kiểu ải một layout */
function layoutOf(s) {
  const M = s.monster, ph = s.phase;
  if (ph === "clear" || ph === "fail") return "end";
  if (ph === "flip") return "flip";
  if (!M || ph === "idle") return "quiz";
  if (M.game === "race") return "race";
  if (M.boss) return "boss";
  return M.floor % 2 ? "quiz" : "duel";
}

/* ---------------------------------------------------------------- sàn đấu */
const ASK = { ko2vi: "Từ này nghĩa là gì?", vi2ko: "Tiếng Hàn là gì?", cloze: "Điền vào chỗ trống",
  trans: "Câu này nghĩa là gì?", hanviet: "Âm Hán Việt là gì?", gram: "Điền ngữ pháp đúng", gfix: "Câu tiếng Hàn nào đúng ngữ pháp?" };
const KIND = { ko2vi: "Hàn → Việt", vi2ko: "Việt → Hàn", cloze: "🧩 Điền chỗ trống", trans: "📝 Dịch câu", hanviet: "🈶 Hán Việt",
  gram: "📘 Ngữ pháp", gfix: "✅ Câu đúng ngữ pháp" };
const OPT_LANG = { ko2vi: "vi", vi2ko: "ko", cloze: "ko", trans: "vi", hanviet: "vi", gram: "ko", gfix: "ko" };
const SENT = new Set(["cloze", "trans", "gram", "gfix"]);     // đề là cả câu
const BLANK = "＿＿＿";
const DEMO_SEED = 20261126;

function initArena() {
  $("#hp").innerHTML = `<div class="hp-top"><span class="nm" id="hpName"></span><span class="tr" id="hpTraits"></span></div>
    <div class="bar"><i class="lag" id="hpLag"></i><i class="fill" id="hpFill"></i><em id="hpNum"></em></div><div class="note" id="hpNote"></div>`;
  const C = 2 * Math.PI * 42;
  const ring = document.createElement("div");
  ring.className = "ring hidden"; ring.id = "ring";
  ring.innerHTML = `<svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="42"/><circle class="fg" cx="50" cy="50" r="42" stroke-dasharray="${C}"/></svg><b></b>`;
  $("#qcard").appendChild(ring);
}
initArena();

let monKey = "";
function setMonster(seed, boss, enter) {
  const key = seed + ":" + boss;
  const mon = $("#mon");
  if (key === monKey) return;
  monKey = key;
  $("#monInner").innerHTML = Monster.svg(seed, boss);
  mon.className = "mon" + (boss ? " boss" : "");
  if (enter) restart(mon, "enter");
}

function renderArena(s) {
  const M = s.monster, Q = s.question, ph = s.phase;
  const zone = M ? M.zone : "forest";
  $("#arenaBg").className = "bg z-" + zone;
  renderTrack(s);
  // quái
  if (M) setMonster(M.seed, M.boss, false);
  else setMonster(DEMO_SEED, false, false);
  const mon = $("#mon");
  mon.classList.toggle("dead", ph === "clear" || (ph === "reveal" && Q && Q.result && Q.result.killed && !anim.busy));
  mon.classList.toggle("laugh", ph === "fail");
  mon.classList.toggle("sleep", ph === "idle");
  // thanh máu
  $("#hp").classList.toggle("hidden", !M);
  if (M) {
    const hp = anim.hp ?? M.hp, pct = Math.max(0, Math.min(1, hp / M.max_hp)) * 100;
    setHTML($("#hpName"), `${M.boss ? "👹 " : ""}${esc(M.name)}`);
    setHTML($("#hpTraits"), M.traits.map((t) => `<span class="trait t-${t.id}">${t.icon} ${esc(t.name)}</span>`).join(""));
    $("#hpFill").style.width = pct + "%";
    $("#hpLag").style.width = pct + "%";
    $("#hpFill").parentElement.classList.toggle("low", pct < 30);
    $("#hpNum").textContent = `${Math.max(0, Math.round(hp))} / ${M.max_hp}`;
    $("#hp").classList.toggle("boss", M.boss);
    setHTML($("#hpNote"), ph === "flip" && s.flip ? `Đã ghép <b>${s.flip.done}/${s.flip.pairs}</b> cặp · mỗi cặp −${s.flip.dmg} máu` : "");
  }
  // vòng đếm ngược
  const ring = $("#ring"), home = ph === "flip" ? $("#arena") : $("#qcard");
  if (ring.parentElement !== home) home.appendChild(ring);
  ring.classList.toggle("hidden", ph !== "question" && ph !== "flip");
  $("#qcard").classList.toggle("ring-in", ph === "question");
  if (ph === "question" || ph === "flip") {
    const frac = s.duration ? Math.max(0, Math.min(1, s.remaining / s.duration)) : 0, C = 2 * Math.PI * 42;
    ring.querySelector(".fg").setAttribute("stroke-dashoffset", String(C * (1 - frac)));
    ring.querySelector("b").textContent = Math.ceil(s.remaining);
    ring.classList.toggle("low", s.remaining <= 5);
  }
  // bảng đề / đáp án
  setHTML($("#panel"), panelHtml(s));
  $("#panel").className = "panel p-" + ph + (Q && (Q.mode === "cloze" || Q.mode === "trans") ? " sent" : "");
  // dấu đóng lớn
  const O = s.outcome;
  let banner = "";
  if (ph === "clear" && O) banner = `<div class="stamp win">${O.boss ? "👑 HẠ BOSS!" : "ĐÃ HẠ GỤC!"}</div>`;
  else if (ph === "fail" && O) banner = `<div class="stamp lose">THẤT BẠI</div>`;
  setHTML($("#banner"), banner);
}

function promptHtml(Q) {
  if (Q.mode !== "cloze" && Q.mode !== "gram") return esc(Q.prompt);
  return esc(Q.prompt).replace(BLANK, `<span class="blank">${BLANK}</span>`);
}
function panelHtml(s) {
  const Q = s.question, ph = s.phase, O = s.outcome, R = s.room;
  if (ph === "flip" && s.flip) {
    return `<div class="tag">🃏 Lật thẻ · đã ghép <b>${s.flip.done}/${s.flip.pairs}</b> cặp</div>
      <div class="big flipt">Ghép chữ Hàn ↔ nghĩa Việt</div>
      <div class="ask">Comment <b>2 số</b> để lật · vd. <b>3 8</b></div>`;
  }
  if ((ph === "question" || ph === "reveal") && Q) {
    const sentence = SENT.has(Q.mode);
    const race = s.monster && s.monster.game === "race" ? "🏎 Đua xe · " : "";
    if (ph === "question") {
      return `<div class="tag">${race}${Q.listen ? "👻 Quái tàng hình · nghe" : KIND[Q.mode] || ""}${Q.double ? ` <b class="x2">💥 x2</b>` : ""}</div>
        <div class="prompt ${Q.listen ? "listen" : Q.prompt_lang}${sentence ? " sent" : ""}">${promptHtml(Q)}</div>
        ${Q.word.romanization ? `<div class="rom">[${esc(Q.word.romanization)}]</div>` : ""}
        ${Q.hint ? `<div class="hint">${Q.mode === "hanviet" ? "Nghĩa: " : "💬 "}${esc(Q.hint)}</div>` : ""}
        ${!Q.hint && !Q.word.romanization ? `<div class="ask">${Q.listen ? "Nghe rồi chọn nghĩa" : ASK[Q.mode] || ""}</div>` : ""}`;
    }
    const w = Q.word;
    if (Q.mode === "gram" || Q.mode === "gfix") {      // ngữ pháp: câu đầy đủ + giải thích ngắn
      return `<div class="tag ok">✅ Đáp án · 📘 Ngữ pháp</div>
        <div class="ko sm gsent">${esc(w.example_ko)}</div>
        ${Q.note ? `<div class="gnote">${esc(Q.note)}</div>` : ""}
        <div class="sub">${esc(w.example_vi)}</div>`;
    }
    // không lặp chữ: ô đáp án đúng ngay bên dưới đã ghi nghĩa (Hàn → Việt). Không hiện âm Hán Việt (người dùng yêu cầu bỏ).
    const flat = (x) => String(x || "").normalize("NFC").toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
    const vi = flat(w.vietnamese) === flat(Q.options[Q.answer]) ? "" : w.vietnamese;
    return `<div class="tag ok">✅ Đáp án</div>
      <div class="ko${sentence ? " sm" : ""}">${esc(w.korean)}</div>
      ${w.romanization ? `<div class="sub">[${esc(w.romanization)}]</div>` : ""}
      ${vi ? `<div class="vi">${esc(vi)}</div>` : ""}
      ${w.example_ko ? `<div class="ex${sentence ? " focus" : ""}"><div class="k">${esc(w.example_ko)}</div><div>${esc(w.example_vi)}</div></div>` : ""}`;
  }
  if (ph === "clear" && O) {
    return `<div class="tag ok">Ải ${O.floor} hoàn thành</div>
      <div class="big">${esc(O.name)}</div>
      ${O.record ? `<div class="rec">🏆 KỶ LỤC MỚI!</div>` : ""}
      ${s.vote ? "" : `<div class="next">Tiếp theo: <b>Ải ${O.next_floor}</b>${O.next_boss ? ` · <b class="bossy">👹 BOSS</b>` : ""}${O.new_zone ? " · vùng mới" : ""}</div>`}`;
  }
  if (ph === "fail" && O) {
    return `<div class="tag bad">💀 Hết tim</div>
      <div class="big">${esc(O.name)} quá mạnh!</div>
      <div class="next">Quay về <b>ải ${O.back_to}</b> · hồi đầy ${R.max_hearts} tim</div>`;
  }
  return `<div class="title-ko">괴물 사냥</div><div class="title">SĂN QUÁI CHỮ</div>
    <div class="ask">${esc(s.message && s.message !== "Tạm dừng" ? s.message : "Sắp bắt đầu, chờ chút nhé…")}</div>`;
}

/* ---------------------------------------------------------------- phần dưới sàn đấu */
function renderOptions(s) {
  const Q = s.question, reveal = s.phase === "reveal";
  const counts = Q.counts, total = counts ? Math.max(1, counts.reduce((a, b) => a + b, 0)) : 1;
  const long = Q.mode === "trans" || Q.mode === "gfix", col = long || $("#board").classList.contains("l-duel");
  const opts = Q.options.map((o, i) => {
    const c = counts ? counts[i] : 0;
    const cls = reveal ? (i === Q.answer ? " right" : " wrong") : "";
    return `<div class="opt ${OPT_LANG[Q.mode] || "vi"}${cls}">
      ${counts ? `<span class="fill" style="width:${(c / total) * 100}%"></span>` : ""}
      <span class="l">${reveal && i === Q.answer ? "✓" : L[i]}</span><span class="t">${esc(o)}</span>
      ${counts && c ? `<span class="cnt">${Math.round((c / total) * 100)}%</span>` : ""}</div>`;
  }).join("");
  let foot = "";
  if (reveal && Q.result) {
    const r = Q.result;
    foot = `<div class="res">${r.total ? `⚔️ <b>${r.dmg}</b> sát thương · ${r.correct}/${r.total} đúng` : "Chưa ai ra đòn…"}
      ${r.attack ? ` · <b class="bad">💥 −${r.attack.hearts} ❤️</b>` : ""}${r.healed ? ` · <b class="heal">💚 +${r.healed}</b>` : ""}</div>`;
  } else foot = `<div class="res q">${Q.answered} người đã ra đòn${Q.double ? " · <b>💥 x2 sát thương</b>" : ""}</div>`;
  return `<div class="opts${col ? " col" : ""}${long ? " long" : ""}">${opts}</div>${foot}`;
}
function heroes(list, unit = "sát thương") {
  const medal = ["🥇", "🥈", "🥉"];
  return `<div class="heroes">${list.map((p, i) => `<div class="hero h${i + 1}">${avatar(p, "calc(var(--u) * 8)", `<span class="medal">${medal[i]}</span>`)}
    <div class="hn"><span class="nm">${esc(p.name)}</span><span class="pt">${lv(p)} ${p.dmg} ${unit}</span></div></div>`).join("") || `<div class="empty">Chưa ai gây sát thương</div>`}</div>`;
}
function renderDoors(v, floor) {
  const total = Math.max(1, v.counts.reduce((a, b) => a + b, 0));
  return `<div class="doors-title">🚪 Chọn cửa vào <b>ải ${floor}</b>: comment <b>1 / 2 / 3</b></div>
    <div class="doors">${v.doors.map((d, i) => `<div class="door"><span class="fill" style="--h:${(v.counts[i] / total) * 100}%"></span>
      <span class="dn">${i + 1}</span><span class="dt"><span class="di">${d.icon}</span>${esc(d.name)}</span><span class="dd">${esc(d.desc)}</span>
      <b>${v.counts[i]} phiếu</b></div>`).join("")}</div>`;
}
function renderMain(s) {
  const ph = s.phase, O = s.outcome;
  if ((ph === "question" || ph === "reveal") && s.question) return renderOptions(s);
  if (ph === "flip") return `<div class="flipwrap" id="flipWrap"></div>`;     // các thẻ do renderFlip giữ nguyên (lật có hoạt cảnh)
  if (ph === "clear" && O) {
    return `<div class="card"><div class="ctitle">🏆 MVP hạ ${esc(O.name)}${O.last_hit ? ` · 🗡 đòn kết liễu: <b>${esc(O.last_hit.name)}</b>` : ""}</div>${heroes(O.mvp)}</div>
      ${s.vote ? renderDoors(s.vote, O.next_floor) : thanks(s)}`;
  }
  if (ph === "fail" && O) {
    return `<div class="card"><div class="ctitle">💪 Chiến binh dũng cảm nhất trận</div>${heroes(O.mvp)}</div>`;
  }
  return `<div class="howto">
      <div class="step"><b>1</b><span>Comment <em>A B C D</em><br>để ra đòn</span></div>
      <div class="step"><b>2</b><span>Đúng = <em>sát thương</em><br>nhanh = chí mạng</span></div>
      <div class="step"><b>3</b><span>Hạ quái, <em>leo ải</em><br>lên cấp 👑</span></div>
    </div>`;
}
function thanks(s) {
  const parts = [];
  if (s.weekly && s.weekly[0]) parts.push(`👑 Dũng sĩ tuần: <b>${esc(s.weekly[0].name)}</b> · ${s.weekly[0].score} sát thương`);
  const top = s.top[0];
  if (top) parts.push(`⚔️ Mạnh nhất phiên: <b>${esc(top.name)}</b> ${lv(top)}`);
  return parts.length ? `<div class="note">${parts.join("<br>")}</div>` : "";
}

/* ---------------------------------------------------------------- hoạt cảnh đòn đánh */
/* chỗ hiện số sát thương trong ô quái (theo bố cục: quái nằm bên trái ở ải ⚔️, giữa ở boss…) */
function dmgAt() {
  const l = $("#board").className.match(/l-(\w+)/)[1];
  const [x0, x1] = l === "quiz" || l === "end" ? [10, 40] : l === "flip" ? [5, 15] : [25, 75];
  return [x0 + Math.random() * (x1 - x0), 38 + Math.random() * 34];
}
function fxAt(html, cls, x, y, ms = 1300, box = null) {
  const d = document.createElement("div");
  d.className = "fxi " + cls;
  d.style.left = x + "%"; d.style.top = y + "%";
  d.innerHTML = html;
  (box || $("#fx")).appendChild(d);
  setTimeout(() => d.remove(), ms);
  return d;
}
function slash(big) {
  const img = fxAt(`<img src="/static/game/fx/${big ? "star_06" : Math.random() < 0.5 ? "slash_02" : "slash_03"}.png" alt="">`,
    "slash" + (big ? " crit" : ""), ...dmgAt(), 600);
  img.style.setProperty("--rot", Math.round(Math.random() * 360) + "deg");
}
function poof() {
  for (let i = 0; i < 6; i++) {
    const d = fxAt(`<img src="/static/game/fx/smoke_04.png" alt="">`, "smoke", ...dmgAt(), 1600);
    d.style.animationDelay = i * 0.06 + "s";
  }
}
function runHits(s, P) {
  const Q = s.question, r = Q.result, M = s.monster;
  if (!r || !M) return 0;
  clearTimers();
  anim.busy = 1;
  anim.hp = r.hp_before;
  anim.hearts = P ? P.hearts : s.room.hearts;
  const mon = $("#mon"), race = M.game === "race";
  if (race) anim.hp = null;
  const step = Math.max(160, Math.min(420, 2600 / Math.max(1, r.hits.length)));
  let t = 450, hp = r.hp_before;
  r.hits.forEach((h, i) => {
    later(t + i * step, () => {
      hp = Math.max(0, hp - h.dmg);
      if (!race) { anim.hp = hp; restart(mon, "hit"); slash(h.crit); }
      const d = race
        ? fxAt(`<b>🏎 +${h.dmg}</b><span>${avatar(h, "calc(var(--u) * 4)")}${esc(h.name)}</span>`, "dmg race", 30 + Math.random() * 50, 40 + Math.random() * 30, 1300, $("#tfx"))
        : fxAt(`<b>−${h.dmg}</b><span>${avatar(h, "calc(var(--u) * 4.2)")}${esc(h.name)}</span>${h.crit ? "<i>CHÍ MẠNG!</i>" : ""}`, "dmg" + (h.crit ? " crit" : ""),
          ...dmgAt());
      d.style.setProperty("--dx", (Math.random() * 10 - 5).toFixed(1));
      if (cfg.sfx) SFX.sample(h.crit ? "crit" : ["hit1", "hit2", "hit3"][i % 3], h.crit ? 0.7 : 0.55);
      renderArena(s);
    });
  });
  t += r.hits.length * step;
  if (r.more) later(t, () => fxAt(`<b>+${r.more} người nữa</b>`, "dmg more", 60, 70));
  if (r.killed) {
    later(t + 250, () => {
      anim.hp = 0; anim.busy = 0; renderArena(s);
      poof(); flash("white");
      if (cfg.sfx) { SFX.sample("coins", 0.8); SFX.fanfare(M.boss); }
      confetti(M.boss ? 90 : 45);
    });
  } else if (r.attack) {
    later(t + 300, () => {
      restart(mon, "attack");
      if (cfg.sfx) SFX.sample("draw", 0.5);
    });
    later(t + 620, () => {
      anim.broken = r.attack.hearts; anim.brokenAt = Date.now();
      anim.hearts = s.room.hearts;
      flash("red"); restart($("#stage"), "shake");
      if (cfg.sfx) SFX.sample("hurt", 0.9);
      fxAt(`<b>−${r.attack.hearts} ❤️</b><span>${r.attack.race ? "Xe quái về đích trước!" : "Quái phản đòn!"}</span>`, "dmg room", 30, 30, 1600);
      renderHud(s);
    });
    if (r.healed) later(t + 1100, () => { anim.hp = r.hp_after; fxAt(`<b>+${r.healed}</b><span>hồi máu</span>`, "dmg heal", 74, 30); renderArena(s); });
  } else if (!r.total) {
    later(t, () => fxAt(`<b>💤</b><span>Chưa ai ra đòn</span>`, "dmg zz", 70, 30, 1600));
  }
  later(t + 1300, () => { anim.hp = null; anim.hearts = null; anim.busy = 0; });
  return t + (r.killed ? 450 : r.attack ? 750 : 0);   // sau mốc này mới đọc đáp án (tiếng đấm / phản đòn đã bắt đầu hết)
}

/* ---------------------------------------------------------------- bot + khung căn chỉnh */
let botSeq = -1;
Hami.mount($("#hami"), $("#hamiBubble"));
snd.addEventListener("play", () => Hami.speaking(true));
["pause", "ended", "error"].forEach((e) => snd.addEventListener(e, () => Hami.speaking(false)));

/* THỨ TỰ ÂM THANH (không để 2 thứ nói chồng nhau):
   - câu mới:      🐰 Hami giới thiệu (câu intro của câu này) → 🔊 đọc đề → báo server bắt đầu đếm ngược
   - hiện đáp án:  💥 tiếng đòn đánh → 🔊 đọc đáp án → 🐰 Hami khen gọi tên / phản đòn… (giữ màn đáp án tới khi xong)
   - đang có âm thanh (từ vựng, hiệu ứng) thì Hami chờ; câu thoại xếp hàng ở botQueue.
   - sang câu hỏi mới: bỏ các câu phụ (soft) còn sót của câu trước; câu khen gọi tên không bao giờ bị bỏ. */
let sndPending = false;   // đang chờ tới lượt đọc đáp án (sau tiếng đòn đánh): Hami chưa được nói
let curQ = 0, phaseNow = "", askWait = 0;
const audioBusy = () => sndPending || (!snd.paused && !snd.ended) || (typeof SFX !== "undefined" && SFX.busy());
const botSnd = new Audio();
botSnd.preload = "auto";
let botPending = false;   // đã gọi botVoice nhưng tiếng chưa phát / chưa xong (đang tải, đang chờ từ vựng đọc xong)
["playing", "ended", "error", "pause"].forEach((e) => botSnd.addEventListener(e, () => { if (e !== "playing") botPending = false; }));
botSnd.addEventListener("playing", () => {
  Hami.speaking(true);
  if (isFinite(botSnd.duration)) Hami.extend(botSnd.duration * 1000 + 600);
});
["pause", "ended", "error"].forEach((e) => botSnd.addEventListener(e, () => Hami.speaking(false)));
snd.addEventListener("play", () => { if (!botSnd.paused) botSnd.pause(); });   // từ vựng được ưu tiên
function botVoice(seq) {
  botPending = true;
  botSnd.src = q(`/audio/bot/${seq}.mp3?b=${boot}`);   // seq quay về 0 sau khi khởi động lại: tránh cache câu cũ
  const t0 = Date.now();
  const go = () => {
    if (audioBusy()) {
      if (Date.now() - t0 > 8000) { botPending = false; return; }   // chờ quá lâu: bỏ giọng câu này
      return setTimeout(go, 150);
    }
    botSnd.play().catch(() => { botPending = false; });
  };
  go();
}

const botQueue = [];      // câu thoại chờ âm thanh im mới nói
let botTimer = null;
const stale = (l) => Date.now() - l.t > (l.soft ? 12000 : 25000) || (l.soft && l.qid < curQ);
function pumpBot() {
  clearTimeout(botTimer); botTimer = null;
  for (let i = botQueue.length - 1; i >= 0; i--) if (stale(botQueue[i])) botQueue.splice(i, 1);
  if (!botQueue.length) return;
  if (audioBusy() || (cfg.bot_voice && (botPending || !botSnd.paused))) { botTimer = setTimeout(pumpBot, 150); return; }
  // đang chờ đọc đề câu mới: câu phụ (chào người mới…) đợi sau khi đọc đề, chỉ câu giới thiệu / câu khen được nói trước
  const i = askWait ? botQueue.findIndex((x) => !x.soft) : 0;
  if (i < 0) { botTimer = setTimeout(pumpBot, 150); return; }
  const l = botQueue.splice(i, 1)[0];
  speaking = l;
  Hami.say(l.text, l.mood, cfg.bot_voice ? () => botVoice(l.seq) : null);
  if (botQueue.length) botTimer = setTimeout(pumpBot, 150);
}

function renderBot(b) {
  $("#hami").classList.toggle("hidden", !b);
  if (!b) { $("#hamiBubble").classList.remove("show"); botQueue.length = 0; return; }
  Hami.base(b.mood);
  const fresh = botSeq >= 0;
  for (const l of b.lines) {
    if (l.seq <= botSeq) continue;
    botSeq = l.seq;
    if (!fresh) continue;                                  // vừa mở overlay: không nói lại câu cũ
    botQueue.push({ ...l, t: Date.now() });
    if (botQueue.length > 5) {                             // hàng quá dài: bỏ câu phụ trước, câu khen gọi tên giữ lại
      const i = botQueue.findIndex((x) => x.soft);
      botQueue.splice(i >= 0 ? i : 0, 1);
    }
  }
  if (botSeq < 0) botSeq = 0;
  // chạy sau phần âm thanh của cùng lượt render (âm đề được hẹn ở cuối render) để Hami không chen vào trước
  if (botQueue.length && !botTimer) botTimer = setTimeout(pumpBot, 50);
}

function renderGuide() {
  if (params.get("guide") !== "1") return;
  const z = (t, l, w, h, label, soft) => `<div class="z${soft ? " soft" : ""}" style="top:${t}%;left:${l}%;width:${w}%;height:${h}%">${label}</div>`;
  $("#guide").innerHTML =
    z(0, 0, 100, 10, "TikTok: tên host · người xem · nút đóng") +
    z(10, 0, 45, 4, "Xếp hạng / sự kiện", true) +
    z(54, 0, 64, 7, "Banner quà TikTok", true) +
    z(67, 0, 72, 22, "Bình luận TikTok") +
    z(64, 84, 16, 25, "Tim bay", true) +
    z(90, 0, 100, 10, "Ô nhập · nút quà · chia sẻ") +
    `<div class="line" style="top:${cfg.safe_top}%">▲ safe_top ${cfg.safe_top}%</div>` +
    `<div class="line" style="top:${cfg.safe_bottom}%">▼ safe_bottom ${cfg.safe_bottom}%</div>`;
  $("#guide").classList.remove("hidden");
}

/* ---------------------------------------------------------------- hiệu ứng khi trạng thái đổi */
function transitions(s) {
  const Q = s.question, M = s.monster, P = prev;
  prev = { phase: s.phase, qid: Q ? Q.id : 0, answered: Q ? Q.answered : 0, sec: Math.ceil(s.remaining),
    seed: M ? M.seed : 0, hearts: s.room.hearts, vote: !!s.vote };
  if (!P) { if (M) setMonster(M.seed, M.boss, false); return false; }   // lần đầu mở overlay: không bắn hiệu ứng cũ
  let entered = false;
  if (M && M.seed !== P.seed) {
    clearTimers(); anim.hp = anim.hearts = null; anim.busy = 0;
    setMonster(M.seed, M.boss, true);
    const tr = M.traits.map((t) => `${t.icon} ${esc(t.name)}`).join(" · ");
    const how = M.game === "flip" ? "🃏 <b>LẬT THẺ</b>: comment 2 số (vd. <b>3 8</b>) để lật, ghép chữ Hàn với nghĩa Việt"
      : M.game === "race" ? "🏎 <b>ĐUA XE</b>: trả lời đúng để xe chạy, về đích trước xe quái"
      : M.boss ? "👹 Boss đánh mất 2 tim, tập trung nha!" : "";
    splash(`ẢI ${M.floor}`, `${M.boss ? "👹 BOSS · " : ""}${esc(M.name)}${tr ? `<small>${tr}</small>` : ""}`, M.boss ? "boss" : "", how);
    if (cfg.sfx) { SFX.sample(M.boss ? "door" : "draw", 0.7); if (M.boss) SFX.drum(); }
  }
  if (s.phase === "question" && Q && Q.id !== P.qid) {
    entered = true;
    if (M && M.seed === P.seed) sfx("whoosh");
  }
  if (s.phase === "question" && Q && Q.id === P.qid) {
    if (Q.answered > P.answered) sfx("pop");
    const sec = Math.ceil(s.remaining);
    if (sec !== P.sec && sec >= 1 && sec <= 5) sfx("tick", sec <= 3);
  }
  if (s.phase === "reveal" && P.phase !== "reveal" && Q) {
    entered = true;
    revealT0 = Date.now();
    revealEnd = runHits(s, P) || 0;
  }
  if ((s.phase === "clear" || s.phase === "fail") && P.phase !== s.phase) {
    entered = true;
    if (s.phase === "fail") { flash("red"); restart($("#stage"), "shake"); sfx("buzz"); }
    if (s.vote && cfg.sfx) setTimeout(() => SFX.sample("door", 0.5), 900);
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
  const layout = layoutOf(s);
  $("#board").className = "board l-" + layout;
  $("#stage").classList.toggle("t-boss", layout === "boss");
  const entered = transitions(s);
  renderHud(s, layout);
  evtIdle(s);
  renderPulse(s.pulse);
  renderArena(s);
  renderTicker(s);
  const main = $("#main");
  $("#stage").dataset.phase = s.phase;
  setHTML(main, renderMain(s));
  renderFlip(s);
  if (entered) {
    main.classList.remove("enter"); void main.offsetWidth; main.classList.add("enter");
    clearTimeout(render.t); render.t = setTimeout(() => main.classList.remove("enter"), 900);
  }

  // thông báo lớn: chỉ dòng mới; lần đầu mở overlay không bật lại thông báo cũ. Hạ quái / thua đã hiện trên sàn đấu.
  const fresh = feedSeq >= 0;
  for (const f of s.feed) {
    if (f.seq <= feedSeq) continue;
    feedSeq = f.seq;
    if (fresh && f.alert && f.kind !== "clear" && f.kind !== "fail") pushAlert(f);
  }
  if (feedSeq < 0) feedSeq = 0;

  // âm thanh theo thứ tự (xem chú thích ở botQueue)
  const Q = s.question;
  phaseNow = s.phase;
  if (Q) {
    if (Q.id !== curQ) { curQ = Q.id; pumpBot(); }        // sang câu mới: dọn câu phụ cũ trong hàng
    const key = Q.id + ":" + s.phase;
    if (key !== last.sound) {
      const fresh = last.sound !== "";
      last.sound = key;
      if (s.phase === "question") askAudio(Q, fresh && entered ? 1300 : 300, s.reading);
      else if (s.phase === "reveal") revealAudio(Q);
    }
  }
}

/* Hami đang nói / sắp nói (bong bóng, giọng đang tải hoặc đang phát) */
const hamiBusy = () => botPending || (!botSnd.paused && !botSnd.ended) || !Hami.idle();
/* chỉ chờ câu QUAN TRỌNG (giới thiệu câu, khen gọi tên, phản đòn…). Câu phụ (chào người mới, top, mời tim) không được làm
   chậm nhịp game: đồng hồ vẫn chạy, màn đáp án không bị giữ, Hami nói câu phụ xen vào lúc rảnh. */
let speaking = null;      // câu Hami đang nói (lần cuối đưa cho Hami)
const hamiBusyKeep = () => hamiBusy() && !!speaking && !speaking.soft;
const keepLeft = (pred) => botQueue.some((l) => !l.soft && pred(l));
const sfxBusy = () => typeof SFX !== "undefined" && SFX.busy();

/* câu mới: chờ Hami nói xong câu giới thiệu của câu này (và câu khen còn dở của câu trước) rồi mới đọc đề;
   đọc xong + im hẳn thì báo server bắt đầu đếm ngược. Chờ tối đa 7 giây (server tự chạy đồng hồ sau read_wait_s). */
function askAudio(Q, minDelay, reading) {
  const qid = Q.id, t0 = Date.now();
  let startedAt = 0;
  const introLeft = () => botQueue.some((l) => (l.intro && l.qid === qid) || (!l.soft && l.qid < qid));
  askWait = qid;
  const gate = () => {
    if (curQ !== qid || phaseNow !== "question") { if (askWait === qid) askWait = 0; return; }
    const wait = Date.now() - t0 < minDelay || (cfg.bot && (introLeft() || hamiBusyKeep())) || sfxBusy();
    if (wait && Date.now() - t0 < 7000) return setTimeout(gate, 150);
    startedAt = Date.now();
    askWait = 0;
    if (Q.audio_q) play(`/audio/${Q.word_id}/${Q.audio_q}.mp3`);
  };
  gate();
  if (!reading) return;
  const check = () => {     // báo server: đọc đề xong, Hami im -> bắt đầu đếm ngược
    if (curQ !== qid || phaseNow !== "question") return;
    if (!startedAt || Date.now() - startedAt < 700 || audioBusy() || hamiBusyKeep() || keepLeft((l) => l.qid <= qid)) return setTimeout(check, 200);
    fetch(q(`/api/overlay/ready?qid=${qid}`), { method: "POST" }).catch(() => {});
  };
  setTimeout(check, 200);
}

/* hiện đáp án: chờ chuỗi đòn đánh (tiếng đấm, phản đòn) xong mới đọc đáp án; Hami chờ tới lượt sau đó.
   Trong lúc còn diễn / còn câu Hami cần nói cho câu này thì xin server giữ màn đáp án (server giới hạn tối đa). */
let revealT0 = 0, revealEnd = 0;
function revealAudio(Q) {
  const qid = Q.id, t0 = revealT0 || Date.now(), end = revealEnd;
  const url = Q.audio_url || (Q.audio_reveal && Q.audio_reveal !== "none" ? `/audio/${Q.word_id}/${Q.audio_reveal}.mp3` : "");
  sndPending = true;
  const gate = () => {
    if (curQ !== qid || phaseNow !== "reveal") { sndPending = false; return; }
    if ((Date.now() - t0 < end || sfxBusy()) && Date.now() - t0 < end + 4000) return setTimeout(gate, 120);
    if (url) play(url);       // snd.paused = false ngay khi gọi play: Hami vẫn bị chặn tới khi đọc xong
    sndPending = false;
  };
  gate();
  const hold = () => {
    if (curQ !== qid || phaseNow !== "reveal") return;
    const busy = sndPending || audioBusy() || hamiBusyKeep() || keepLeft((l) => l.qid === qid);
    if (busy) fetch(q(`/api/overlay/hold?qid=${qid}`), { method: "POST" }).catch(() => {});
    setTimeout(hold, 800);
  };
  setTimeout(hold, 800);
}

let boot = null;
function onState(s) {
  // server vừa khởi động lại: số thứ tự câu thoại/feed quay về 0 và có thể đã có JS mới -> tải lại trang
  if (s.boot && boot && s.boot !== boot) { location.reload(); return; }
  boot = s.boot || boot;
  try { render(s); } catch (e) { console.error(e); }
}

/* Nhận trạng thái: ưu tiên KÊNH ĐẨY (server gửi ngay khi có comment, trễ < 50 ms). Server cũ chưa có kênh này
   hoặc kênh lỗi liên tục thì quay về hỏi định kỳ mỗi 250 ms, cứ 30 giây thử lại kênh đẩy. */
let pushOk = false, polling = false;
function startPush() {
  if (typeof EventSource === "undefined") return startPoll();
  const es = new EventSource(q("/api/overlay/stream"));
  let got = false;
  es.onmessage = (m) => {
    got = pushOk = true;
    polling = false;
    try { onState(JSON.parse(m.data)); } catch (e) { console.error(e); }
  };
  es.onerror = () => {
    if (got && es.readyState !== EventSource.CLOSED) return;   // rớt mạng giữa chừng: EventSource tự nối lại
    es.close(); pushOk = false;
    startPoll();
    setTimeout(startPush, 30000);
  };
}
async function poll() {
  if (pushOk) { polling = false; return; }
  try {
    const r = await fetch(q("/api/overlay/state"), { credentials: "same-origin" });
    if (r.ok) onState(await r.json());
    else if (r.status === 401) $("#main").innerHTML = `<div class="card note">⚠️ Link overlay thiếu hoặc sai token.<br>Lấy lại link trong trang /admin.</div>`;
  } catch (e) { console.error(e); /* mất mạng tạm thời: thử lại */ }
  setTimeout(poll, 250);
}
function startPoll() { if (!polling && !pushOk) { polling = true; poll(); } }
startPush();
