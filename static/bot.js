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
    clearInterval(fxTimer);
    const fx = FX[m];
    if (fx) { spawn(fx); fxTimer = setInterval(() => spawn(fx), m === "sleep" ? 1600 : 450); }
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
  }

  function say(text, mood = "talk") {
    if (!root) return;
    clearTimeout(moodTimer); clearInterval(typeTimer); clearTimeout(hideTimer);
    setMood(mood);
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

  return { mount, say, base, speaking };
})();
