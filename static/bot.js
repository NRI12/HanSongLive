"use strict";
/* Hami: linh vật SVG (tự vẽ) với các trạng thái animation.
   Hami.mount(el, bubbleEl) · Hami.say(text, mood) · Hami.base(mood) · Hami.speaking(bool)
   mood: idle | talk | happy | sad | wow | love | dance | hurry | wave | sleep */
const Hami = (() => {
  const SVG = `
<svg viewBox="0 0 200 230" class="hami-svg" aria-hidden="true">
  <defs>
    <radialGradient id="hBody" cx="45%" cy="35%" r="70%"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#ffe3ec"/></radialGradient>
    <linearGradient id="hBand" x1="0" x2="1"><stop offset="0" stop-color="#ff6f91"/><stop offset="1" stop-color="#ff9a8b"/></linearGradient>
  </defs>
  <ellipse class="h-shadow" cx="100" cy="222" rx="52" ry="7" fill="#0006"/>
  <g class="h-all">
    <g class="h-ear h-ear-l"><path d="M70 78 C52 20 66 0 80 6 C94 12 92 52 86 80 Z" fill="url(#hBody)" stroke="#f3b6c8" stroke-width="3"/>
      <path d="M74 70 C64 30 72 16 80 20 C88 24 86 50 83 72 Z" fill="#ffb3c7"/></g>
    <g class="h-ear h-ear-r"><path d="M130 78 C148 20 134 0 120 6 C106 12 108 52 114 80 Z" fill="url(#hBody)" stroke="#f3b6c8" stroke-width="3"/>
      <path d="M126 70 C136 30 128 16 120 20 C112 24 114 50 117 72 Z" fill="#ffb3c7"/></g>
    <g class="h-body">
      <ellipse cx="100" cy="140" rx="74" ry="72" fill="url(#hBody)" stroke="#f3b6c8" stroke-width="3"/>
      <path d="M40 104 Q100 78 160 104 L157 116 Q100 92 43 116 Z" fill="url(#hBand)"/>
      <circle cx="100" cy="98" r="12" fill="#fff" stroke="#ff6f91" stroke-width="2.5"/>
      <text x="100" y="103" text-anchor="middle" font-size="13" font-weight="900" fill="#ff4d7a" font-family="Noto Sans KR, sans-serif">한</text>
      <g class="h-eyes">
        <g class="h-eyes-open"><g class="h-eye"><ellipse cx="76" cy="138" rx="9" ry="11" fill="#2a1d2e"/><circle cx="79" cy="134" r="3.5" fill="#fff"/></g>
          <g class="h-eye"><ellipse cx="124" cy="138" rx="9" ry="11" fill="#2a1d2e"/><circle cx="127" cy="134" r="3.5" fill="#fff"/></g></g>
        <g class="h-eyes-happy" fill="none" stroke="#2a1d2e" stroke-width="5" stroke-linecap="round"><path d="M66 140 Q76 128 86 140"/><path d="M114 140 Q124 128 134 140"/></g>
        <g class="h-eyes-closed" fill="none" stroke="#2a1d2e" stroke-width="4" stroke-linecap="round"><path d="M66 140 Q76 146 86 140"/><path d="M114 140 Q124 146 134 140"/></g>
        <g class="h-eyes-heart" fill="#ff4d7a"><path d="M76 147 l-10 -10 a6 6 0 0 1 10 -7 a6 6 0 0 1 10 7 z"/><path d="M124 147 l-10 -10 a6 6 0 0 1 10 -7 a6 6 0 0 1 10 7 z"/></g>
        <g class="h-eyes-x" fill="none" stroke="#2a1d2e" stroke-width="4" stroke-linecap="round"><path d="M69 132 l14 12 M83 132 l-14 12"/><path d="M117 132 l14 12 M131 132 l-14 12"/></g>
      </g>
      <ellipse cx="60" cy="160" rx="11" ry="7" fill="#ff9fb8" opacity=".75"/><ellipse cx="140" cy="160" rx="11" ry="7" fill="#ff9fb8" opacity=".75"/>
      <g class="h-mouth">
        <path class="m-smile" d="M88 158 Q100 170 112 158" fill="none" stroke="#2a1d2e" stroke-width="4" stroke-linecap="round"/>
        <path class="m-open" d="M86 156 Q100 182 114 156 Z" fill="#c2185b" stroke="#2a1d2e" stroke-width="3.5" stroke-linejoin="round"/>
        <ellipse class="m-o" cx="100" cy="163" rx="8" ry="10" fill="#c2185b" stroke="#2a1d2e" stroke-width="3.5"/>
        <path class="m-sad" d="M88 166 Q100 155 112 166" fill="none" stroke="#2a1d2e" stroke-width="4" stroke-linecap="round"/>
      </g>
      <path class="h-tear" d="M86 150 q-5 10 0 14 q5 -4 0 -14z" fill="#7cc4ff"/>
      <path class="h-sweat" d="M150 108 q-7 12 0 17 q7 -5 0 -17z" fill="#9ed8ff"/>
    </g>
    <g class="h-arm h-arm-l"><ellipse cx="34" cy="160" rx="14" ry="20" fill="url(#hBody)" stroke="#f3b6c8" stroke-width="3"/></g>
    <g class="h-arm h-arm-r"><ellipse cx="166" cy="160" rx="14" ry="20" fill="url(#hBody)" stroke="#f3b6c8" stroke-width="3"/></g>
    <g class="h-feet"><ellipse cx="74" cy="208" rx="20" ry="11" fill="#fff" stroke="#f3b6c8" stroke-width="3"/>
      <ellipse cx="126" cy="208" rx="20" ry="11" fill="#fff" stroke="#f3b6c8" stroke-width="3"/></g>
  </g>
</svg>
<div class="h-fx"></div>`;

  const FX = { love: ["💖", "💕", "💗"], dance: ["🎉", "✨", "🎊", "⭐"], wow: ["✨", "⭐"], sleep: ["💤"], hurry: ["⏰"], happy: ["✨"], sad: ["💧"] };
  let root, bubble, bubbleText, baseMood = "idle", moodTimer, typeTimer, hideTimer, fxTimer;

  function setMood(m) {
    root.dataset.mood = m;
    if (m !== "idle" && m !== "talk") root.classList.remove("walking", ...ACTS);
    clearInterval(fxTimer);
    const fx = FX[m];
    if (fx) { spawn(fx); fxTimer = setInterval(() => spawn(fx), m === "sleep" ? 2400 : 1100); }   // thưa, đỡ rối mắt
  }
  function spawn(list) {
    const box = root.querySelector(".h-fx");
    const s = document.createElement("span");
    s.textContent = list[Math.floor(Math.random() * list.length)];
    s.style.left = 10 + Math.random() * 80 + "%";
    s.style.animationDuration = 1.4 + Math.random() * 0.8 + "s";
    box.appendChild(s);
    setTimeout(() => s.remove(), 2400);
    while (box.children.length > 10) box.firstChild.remove();
  }

  function mount(el, bubbleEl) {
    root = el; bubble = bubbleEl;
    root.innerHTML = SVG;
    bubble.innerHTML = `<b class="b-name">Hami</b><span class="b-text"></span>`;
    bubbleText = bubble.querySelector(".b-text");
    setMood("idle");
    idleLoop();
  }

  /* lúc rảnh: đảo mắt, đi lại trong vùng trống, vài động tác ngẫu nhiên. Lúc nói: về chỗ gốc cạnh bong bóng. */
  const ACTS = ["act-hop", "act-ears", "act-wave", "act-tilt", "act-spin", "act-bounce", "act-peek"];
  let idleTimer, actTimer, walkTimer, pos = { x: 0, y: 0 };
  const rnd = (a, b) => a + Math.random() * (b - a);
  function look(x, y = 0) { root.style.setProperty("--look", x + "px"); root.style.setProperty("--look-y", y + "px"); }
  function moveTo(x, y) {
    const dist = Math.hypot(x - pos.x, y - pos.y);
    if (dist < 4) return;
    const stage = root.offsetParent;
    const speed = (stage ? stage.clientWidth : 500) * 0.25;   // ~25% chiều rộng khung mỗi giây
    const t = Math.max(0.6, Math.min(3.5, dist / speed));
    if (Math.abs(x - pos.x) > 4) root.classList.toggle("face-left", x < pos.x);
    look(x < pos.x ? -6 : 6);
    root.style.setProperty("--wt", t.toFixed(2) + "s");
    root.style.setProperty("--wx", Math.round(x) + "px");
    root.style.setProperty("--wy", Math.round(y) + "px");
    pos = { x, y };
    root.classList.add("walking");
    clearTimeout(walkTimer);
    walkTimer = setTimeout(() => root.classList.remove("walking"), t * 1000);
  }
  function goHome() { moveTo(0, 0); }
  /* vùng cấm: nội dung game + (chế độ vùng an toàn) cột comment TikTok bên trái phía dưới. Toạ độ trong khung. */
  function blocked() {
    const stage = root.offsetParent, sr = stage.getBoundingClientRect(), W = stage.clientWidth, H = stage.clientHeight;
    const rects = [...stage.querySelectorAll("#hud, #arena, #main > *, #lane")]
      .map((e) => e.getBoundingClientRect()).filter((r) => r.width && r.height)
      .map((r) => ({ l: r.left - sr.left, t: r.top - sr.top, r: r.right - sr.left, b: r.bottom - sr.top }));
    if (document.body.classList.contains("safe")) {
      const sb = parseFloat(getComputedStyle(stage).getPropertyValue("--sb")) || 62;
      rects.push({ l: 0, t: H * sb / 100, r: W * 0.74, b: H * 0.9 });   // comment TikTok
    }
    return rects;
  }
  function free(x, y) {                            // x, y: góc trên trái của Hami trong khung
    const w = root.offsetWidth, h = root.offsetHeight, pad = w * 0.12;
    return blocked().every((r) => x + w - pad <= r.l || x + pad >= r.r || y + h - pad <= r.t || y + pad >= r.b);
  }
  function wander() {
    // offsetLeft/Top không tính transform = chỗ đứng gốc. Chừa 12% trên (tên host TikTok) và 10% dưới (ô nhập).
    const stage = root.offsetParent;
    if (!stage) return;
    const W = stage.clientWidth, H = stage.clientHeight, w = root.offsetWidth, h = root.offsetHeight;
    for (let i = 0; i < 30; i++) {
      const x = rnd(0, Math.max(0, W - w)), y = rnd(H * 0.12, Math.max(H * 0.12, H * 0.9 - h));
      if (free(x, y)) { moveTo(x - root.offsetLeft, y - root.offsetTop); return; }
    }
    goHome();                                      // hết chỗ trống: về chỗ gốc
  }
  function act(c) {
    if (!root) return;
    ACTS.forEach((a) => root.classList.remove(a));
    void root.offsetWidth;                         // để animation chạy lại nếu trùng động tác cũ
    root.classList.add(c);
    clearTimeout(actTimer);
    actTimer = setTimeout(() => root.classList.remove(c), 1700);
  }
  function idleLoop() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => { idleLoop(); try { idleStep(); } catch (e) { /* lỗi 1 bước không được làm dừng vòng */ } },
      rnd(1800, 3600));
  }
  function idleStep() {
    if (!root.offsetParent) return;                // đang ẩn (bot tắt / overlay chưa vẽ xong)
    const busy = root.classList.contains("talking") || bubble.classList.contains("show");
    const m = root.dataset.mood;
    if (m !== "sleep") look(Math.round(rnd(-5, 5)), Math.round(rnd(-2, 3)));   // mắt luôn đảo
    if (busy) { goHome(); return; }
    if (!free(root.offsetLeft + pos.x, root.offsetTop + pos.y)) { wander(); return; }   // bị nội dung mới che: tránh đi
    if (m !== "idle" && m !== "talk") return;      // đang vui / buồn / ngủ…: đứng yên cho biểu cảm hiện rõ
    const r = Math.random();
    if (r < 0.4) wander();
    else if (r < 0.9) act(ACTS[Math.floor(Math.random() * ACTS.length)]);
  }

  /* hàng chờ: câu mới không cắt ngang câu đang nói (trừ khi câu cũ đã hiện đủ 2,5 giây và hàng đã dài) */
  const queue = [];
  let busyUntil = 0, nextTimer;
  function say(text, mood = "talk", onStart = null) {
    if (!root) return;
    if (queue.length >= 3) queue.shift();
    queue.push([text, mood, onStart]);
    pump();
  }
  function pump() {
    clearTimeout(nextTimer);
    if (!queue.length) return;
    const wait = busyUntil - Date.now();
    if (wait > 0) { nextTimer = setTimeout(pump, wait); return; }
    const [text, mood, onStart] = queue.shift();
    speak(text, mood);
    busyUntil = Date.now() + Math.min(5200, 2500 + [...text].length * 40);
    if (onStart) onStart();
    if (queue.length) nextTimer = setTimeout(pump, busyUntil - Date.now());
  }

  function speak(text, mood) {
    clearTimeout(moodTimer); clearInterval(typeTimer); clearTimeout(hideTimer);
    setMood(mood);
    goHome();                                       // về cạnh bong bóng thoại
    root.classList.add("talking");
    bubble.classList.add("show");
    document.body.classList.add("bot-talking");
    const chars = [...text]; let i = 0;
    bubbleText.textContent = "";
    typeTimer = setInterval(() => {                 // gõ từng chữ, miệng nhép theo
      bubbleText.textContent += chars[i++] || "";
      if (i >= chars.length) { clearInterval(typeTimer); root.classList.remove("talking"); }
    }, 38);
    const hold = Math.min(9000, 2600 + chars.length * 55);
    moodTimer = setTimeout(() => setMood(baseMood), Math.max(hold, 4200));
    hideTimer = setTimeout(() => { bubble.classList.remove("show"); document.body.classList.remove("bot-talking"); }, hold);
  }

  function base(m) {
    if (m === baseMood) return;
    baseMood = m;
    if (!bubble.classList.contains("show")) setMood(m);
  }

  function speaking(on) { if (root) root.classList.toggle("speaking", on); }

  /* giọng đọc dài hơn thời gian hiện bong bóng: giữ bong bóng + chặn câu kế tiếp tới khi đọc xong */
  function extend(ms) {
    const until = Date.now() + ms;
    if (until <= busyUntil) return;
    busyUntil = until;
    clearTimeout(hideTimer); clearTimeout(moodTimer);
    hideTimer = setTimeout(() => { bubble.classList.remove("show"); document.body.classList.remove("bot-talking"); }, ms);
    moodTimer = setTimeout(() => setMood(baseMood), ms);
    if (queue.length) { clearTimeout(nextTimer); nextTimer = setTimeout(pump, ms); }
  }

  /* còn câu chờ nói? (overlay dùng để biết Hami đã nói xong chưa trước khi chạy đồng hồ) */
  const pending = () => queue.length;
  const idle = () => !queue.length && Date.now() >= busyUntil;

  return { mount, say, base, speaking, extend, pending, idle, act };
})();
