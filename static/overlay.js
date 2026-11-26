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
  box.innerHTML = `<div class="a-text">${esc(f.text)}</div>`;
  if (f.kind === "record" || f.kind === "goal" || f.kind === "like" || f.kind === "level") { sfx("fanfare", tier >= 3); confetti(tier >= 3 ? 70 : 35); }
  else sfx("sparkle");
  box.className = `alert t${tier} k-${f.kind}`;
  setTimeout(nextAlert, tier >= 3 ? 3400 : 2400);
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
  el.innerHTML = `<div class="no">${esc(no)}</div><div class="kind">${kind}</div>`;
  void el.offsetWidth;
  el.className = "splash " + cls;
  clearTimeout(splash.t);
  splash.t = setTimeout(() => el.classList.add("hidden"), 1900);
}
function flash(cls) {
  const el = $("#flash");
  el.className = "flash"; void el.offsetWidth; el.className = "flash " + cls;
}
function restart(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }

/* ---------------------------------------------------------------- mẹo chơi luân phiên (làn bot) */
function tips() {
  if (!cfg) return [];
  const t = ["<b>Comment A / B / C / D</b> để ra đòn · đúng = gây sát thương lên quái ⚔️",
    "⚡ Người đúng <b>đầu tiên</b> được CHÍ MẠNG · trả lời càng nhanh đòn càng mạnh",
    "💥 Dưới 50% cả phòng đúng thì quái <b>phản đòn</b>, mất tim chung!"];
  if (cfg.boss_every) t.push(`👹 Cứ ${cfg.boss_every} ải có 1 <b>BOSS</b> · hết tim thì về ải đầu vùng`);
  if (cfg.like_goal) t.push(`❤️ Thả tim đủ ${cfg.like_goal} = câu sau <b>x2 sát thương</b>`);
  if (cfg.share_goal) t.push(`🔁 Đủ ${cfg.share_goal} lượt chia sẻ = <b>hồi 1 tim</b> cho cả phòng`);
  if (cfg.vote) t.push("🚪 Hạ quái xong comment <b>1 / 2 / 3</b> để chọn cửa vào ải sau");
  t.push("⬆️ Sát thương tích luỹ để lên cấp: 🌱 → 🗡 → 🛡 → 🔮 → ⭐ → 👑 · gõ <b>điểm</b> để xem");
  if (cfg.bot && cfg.bot_ai) t.push("🐰 Gõ <b>bot ơi …</b> để hỏi Hami về tiếng Hàn");
  t.push("➕ Theo dõi kênh để không bỏ lỡ buổi săn quái sau nha!");
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
let tickQ = 0, tickSeq = 0;
function renderTicker(s) {
  const box = $("#ticker"), rows = s.phase === "question" ? s.recent_ans || [] : [];
  const qid = s.question && s.phase === "question" ? s.question.id : 0;
  if (qid !== tickQ) { box.innerHTML = ""; tickQ = qid; tickSeq = 0; }
  for (const r of rows) {
    if (r.seq <= tickSeq) continue;
    const d = document.createElement("div");
    d.className = "tick";
    d.innerHTML = `${avatar(r)}<span class="nm">${esc(r.name)}</span>${cfg.live_counts ? `<em>${esc(r.letter)}</em>` : "<em>⚔</em>"}`;
    box.prepend(d);
    tickSeq = r.seq;
  }
  while (box.children.length > 4) box.lastChild.remove();
  $("#lane").classList.toggle("has-ticker", box.children.length > 0);
}

/* ---------------------------------------------------------------- HUD */
function renderHud(s) {
  const R = s.room, M = s.monster, G = s.goals;
  const floor = M ? M.floor : R.floor, n = R.zone_len;
  const inZone = ((floor - 1) % n) + 1;
  const pips = Array.from({ length: n }, (_, i) => {
    const boss = cfg.boss_every && i === n - 1;
    return `<i class="${i + 1 < inZone ? "done" : i + 1 === inZone ? "cur" : ""}${boss ? " boss" : ""}">${boss ? "👹" : ""}</i>`;
  }).join("");
  const hearts = anim.hearts ?? R.hearts;
  const breaking = Date.now() - anim.brokenAt < 1300;
  const hs = Array.from({ length: R.max_hearts }, (_, i) =>
    `<i class="${i < hearts ? "on" : "off"}${breaking && i >= hearts && i < hearts + anim.broken ? " break" : ""}">${i < hearts ? "❤️" : "🖤"}</i>`).join("");
  const chips = [];
  const chip = (cls, x, text, hot) => chips.push(`<div class="chip ${cls}${hot ? " hot" : ""}"><i style="width:${Math.min(1, x) * 100}%"></i><span>${text}</span></div>`);
  if (G.likes.goal) chip("", s.double_next ? 1 : G.likes.progress, s.double_next ? "💥 x2 câu sau!" : `❤️ ${G.likes.value}/${G.likes.goal} · x2`, s.double_next);
  if (G.shares.goal) chip("share", G.shares.progress, `🔁 ${G.shares.value}/${G.shares.goal} · hồi tim`);
  chip("rec", 0, R.best_floor ? `🏆 Kỷ lục: ải ${R.best_floor}` : "🏆 Chưa có kỷ lục");
  setHTML($("#hud"), `<div class="hud-row">
      <div class="floor${M && M.boss ? " boss" : ""}"><b>ẢI ${floor}</b><span>${esc(M ? M.zone_name : "Săn Quái Chữ")}</span></div>
      <div class="pips">${pips}</div>
      <div class="hearts${hearts <= 1 && s.phase !== "idle" ? " low" : ""}">${hs}</div>
    </div><div class="chips">${chips.join("")}</div>`);
}

/* ---------------------------------------------------------------- sàn đấu */
const ASK = { ko2vi: "Từ này nghĩa là gì?", vi2ko: "Tiếng Hàn là gì?", cloze: "Điền vào chỗ trống",
  trans: "Câu này nghĩa là gì?", hanviet: "Âm Hán Việt là gì?" };
const KIND = { ko2vi: "Hàn → Việt", vi2ko: "Việt → Hàn", cloze: "🧩 Điền chỗ trống", trans: "📝 Dịch câu", hanviet: "🈶 Hán Việt" };
const OPT_LANG = { ko2vi: "vi", vi2ko: "ko", cloze: "ko", trans: "vi", hanviet: "vi" };
const BLANK = "＿＿＿";
const DEMO_SEED = 20261126;

function initArena() {
  $("#hp").innerHTML = `<div class="hp-top"><span class="nm" id="hpName"></span><span class="tr" id="hpTraits"></span></div>
    <div class="bar"><i class="lag" id="hpLag"></i><i class="fill" id="hpFill"></i><em id="hpNum"></em></div>`;
  const C = 2 * Math.PI * 42;
  const ring = document.createElement("div");
  ring.className = "ring hidden"; ring.id = "ring";
  ring.innerHTML = `<svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="42"/><circle class="fg" cx="50" cy="50" r="42" stroke-dasharray="${C}"/></svg><b></b>`;
  $("#arena").appendChild(ring);
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
  const st = $("#stage");
  st.classList.toggle("m-trans", !!(Q && Q.mode === "trans" && (ph === "question" || ph === "reveal")));
  st.classList.toggle("m-sent", !!(Q && (Q.mode === "cloze" || Q.mode === "trans")));
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
  }
  // vòng đếm ngược
  const ring = $("#ring");
  ring.classList.toggle("hidden", ph !== "question");
  if (ph === "question") {
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
  if (Q.mode !== "cloze") return esc(Q.prompt);
  return esc(Q.prompt).replace(BLANK, `<span class="blank">${BLANK}</span>`);
}
function panelHtml(s) {
  const Q = s.question, ph = s.phase, O = s.outcome, R = s.room;
  if ((ph === "question" || ph === "reveal") && Q) {
    const sentence = Q.mode === "cloze" || Q.mode === "trans";
    if (ph === "question") {
      return `<div class="tag">${Q.listen ? "👻 Quái tàng hình · nghe" : KIND[Q.mode] || ""}${Q.double ? ` <b class="x2">💥 x2</b>` : ""}</div>
        <div class="prompt ${Q.listen ? "listen" : Q.prompt_lang}${sentence ? " sent" : ""}">${promptHtml(Q)}</div>
        ${Q.word.romanization ? `<div class="rom">[${esc(Q.word.romanization)}]</div>` : ""}
        ${Q.hint ? `<div class="hint">${Q.mode === "hanviet" ? "Nghĩa: " : "💬 "}${esc(Q.hint)}</div>` : ""}
        ${!Q.hint && !Q.word.romanization ? `<div class="ask">${Q.listen ? "Nghe rồi chọn nghĩa" : ASK[Q.mode] || ""}</div>` : ""}`;
    }
    const w = Q.word;
    return `<div class="tag ok">✅ Đáp án</div>
      <div class="ko${sentence ? " sm" : ""}">${esc(w.korean)}</div>
      ${w.hanviet || w.romanization ? `<div class="sub">${[w.romanization ? `[${esc(w.romanization)}]` : "", w.hanviet ? `<span class="hv">${esc(w.hanviet)}</span>` : ""].filter(Boolean).join(" · ")}</div>` : ""}
      <div class="vi">${esc(w.vietnamese)}</div>
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
  const long = Q.mode === "trans";
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
  return `<div class="opts${long ? " long" : ""}">${opts}</div>${foot}`;
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
  if (ph === "clear" && O) {
    return `<div class="card"><div class="ctitle">🏆 MVP hạ ${esc(O.name)}${O.last_hit ? ` · 🗡 đòn kết liễu: <b>${esc(O.last_hit.name)}</b>` : ""}</div>${heroes(O.mvp)}</div>
      ${s.vote ? renderDoors(s.vote, O.next_floor) : thanks(s)}`;
  }
  if (ph === "fail" && O) {
    return `<div class="card"><div class="ctitle">💪 Chiến binh dũng cảm nhất trận</div>${heroes(O.mvp)}</div>
      <div class="note">Gom sức lại! Cả phòng cùng đúng trên 50% thì quái không phản đòn được.</div>`;
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
function fxAt(html, cls, x, y, ms = 1300) {
  const d = document.createElement("div");
  d.className = "fxi " + cls;
  d.style.left = x + "%"; d.style.top = y + "%";
  d.innerHTML = html;
  $("#fx").appendChild(d);
  setTimeout(() => d.remove(), ms);
  return d;
}
function slash(big) {
  const img = fxAt(`<img src="/static/game/fx/${big ? "star_06" : Math.random() < 0.5 ? "slash_02" : "slash_03"}.png" alt="">`,
    "slash" + (big ? " crit" : ""), 66 + Math.random() * 14, 35 + Math.random() * 30, 600);
  img.style.setProperty("--rot", Math.round(Math.random() * 360) + "deg");
}
function poof() {
  for (let i = 0; i < 6; i++) {
    const d = fxAt(`<img src="/static/game/fx/smoke_04.png" alt="">`, "smoke", 64 + Math.random() * 20, 40 + Math.random() * 35, 1600);
    d.style.animationDelay = i * 0.06 + "s";
  }
}
function runHits(s, P) {
  const Q = s.question, r = Q.result, M = s.monster;
  if (!r || !M) return;
  clearTimers();
  anim.busy = 1;
  anim.hp = r.hp_before;
  anim.hearts = P ? P.hearts : s.room.hearts;
  const mon = $("#mon");
  const step = Math.max(160, Math.min(420, 2600 / Math.max(1, r.hits.length)));
  let t = 450, hp = r.hp_before;
  r.hits.forEach((h, i) => {
    later(t + i * step, () => {
      hp = Math.max(0, hp - h.dmg);
      anim.hp = hp;
      restart(mon, "hit");
      slash(h.crit);
      const d = fxAt(`<b>−${h.dmg}</b><span>${esc(h.name)}</span>${h.crit ? "<i>CHÍ MẠNG!</i>" : ""}`, "dmg" + (h.crit ? " crit" : ""),
        52 + Math.random() * 30, 22 + Math.random() * 38);
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
      fxAt(`<b>−${r.attack.hearts} ❤️</b><span>Quái phản đòn!</span>`, "dmg room", 30, 30, 1600);
      renderHud(s);
    });
    if (r.healed) later(t + 1100, () => { anim.hp = r.hp_after; fxAt(`<b>+${r.healed}</b><span>hồi máu</span>`, "dmg heal", 74, 30); renderArena(s); });
  } else if (!r.total) {
    later(t, () => fxAt(`<b>💤</b><span>Chưa ai ra đòn</span>`, "dmg zz", 70, 30, 1600));
  }
  later(t + 1300, () => { anim.hp = null; anim.hearts = null; anim.busy = 0; });
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
  const Q = s.question, M = s.monster, P = prev;
  prev = { phase: s.phase, qid: Q ? Q.id : 0, answered: Q ? Q.answered : 0, sec: Math.ceil(s.remaining),
    seed: M ? M.seed : 0, hearts: s.room.hearts, vote: !!s.vote };
  if (!P) { if (M) setMonster(M.seed, M.boss, false); return false; }   // lần đầu mở overlay: không bắn hiệu ứng cũ
  let entered = false;
  if (M && M.seed !== P.seed) {
    clearTimers(); anim.hp = anim.hearts = null; anim.busy = 0;
    setMonster(M.seed, M.boss, true);
    const tr = M.traits.map((t) => `${t.icon} ${esc(t.name)}`).join(" · ");
    splash(`ẢI ${M.floor}`, `${M.boss ? "👹 BOSS · " : ""}${esc(M.name)}${tr ? `<small>${tr}</small>` : ""}`, M.boss ? "boss" : "");
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
    runHits(s, P);
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
  const entered = transitions(s);
  renderHud(s);
  renderArena(s);
  renderTicker(s);
  const main = $("#main");
  $("#stage").dataset.phase = s.phase;
  setHTML(main, renderMain(s));
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

  // âm thanh: câu mới -> đọc đề (chờ màn giới thiệu quái nếu vừa xuất hiện); hiện đáp án -> bản 2 luồng
  const Q = s.question;
  if (Q) {
    const key = Q.id + ":" + s.phase;
    if (key !== last.sound) {
      const fresh = last.sound !== "";
      last.sound = key;
      if (s.phase === "question" && Q.audio_q) setTimeout(() => play(`/audio/${Q.word_id}/${Q.audio_q}.mp3`), fresh && entered ? 1300 : 300);
      else if (s.phase === "reveal") play(`/audio/${Q.word_id}/${Q.audio_reveal || "mix"}.mp3`);
    }
  }
}

async function poll() {
  try {
    const r = await fetch(q("/api/overlay/state"), { credentials: "same-origin" });
    if (r.ok) render(await r.json());
    else if (r.status === 401) $("#main").innerHTML = `<div class="card note">⚠️ Link overlay thiếu hoặc sai token.<br>Lấy lại link trong trang /admin.</div>`;
  } catch (e) { console.error(e); /* mất mạng tạm thời: thử lại */ }
  setTimeout(poll, 400);
}
poll();
