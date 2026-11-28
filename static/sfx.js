"use strict";
/* Hiệu ứng âm thanh: phần lớn tự tổng hợp bằng WebAudio, cộng vài tiếng đấm/chém/xu từ Kenney (CC0, static/game/sfx).
   SFX.tick() · whoosh() · pop() · ding() · buzz() · sparkle() · fanfare(big) · drum() · sample(name, vol)
   Âm lượng nhỏ để không lấn giọng đọc từ vựng và giọng Hami. */
const SFX = (() => {
  let ctx = null, master = null, enabled = true, endAt = 0;   // endAt: lúc tiếng đang phát kết thúc (giây, ctx.currentTime)
  const until = (t) => { endAt = Math.max(endAt, t); };
  function ac() {
    if (!ctx) {
      const C = window.AudioContext || window.webkitAudioContext;
      if (!C) return null;
      ctx = new C();
      master = ctx.createGain();
      master.gain.value = 0.32;
      master.connect(ctx.destination);
    }
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  }
  document.addEventListener("click", () => ac());

  function tone(freq, t0, dur, { type = "sine", vol = 0.6, slide = 0, attack = 0.005 } = {}) {
    const c = ac(); if (!c || !enabled) return;
    const o = c.createOscillator(), g = c.createGain();
    const t = c.currentTime + t0;
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq * slide), t + dur);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(vol, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(master);
    o.start(t); o.stop(t + dur + 0.02); until(t + dur);
  }
  function noise(t0, dur, { vol = 0.4, hp = 800, lp = 8000 } = {}) {
    const c = ac(); if (!c || !enabled) return;
    const n = Math.floor(c.sampleRate * dur), buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const s = c.createBufferSource(), f1 = c.createBiquadFilter(), f2 = c.createBiquadFilter(), g = c.createGain();
    f1.type = "highpass"; f1.frequency.value = hp; f2.type = "lowpass"; f2.frequency.value = lp;
    g.gain.value = vol;
    s.buffer = buf; s.connect(f1); f1.connect(f2); f2.connect(g); g.connect(master);
    s.start(c.currentTime + t0); until(c.currentTime + t0 + dur);
  }

  // tiếng mẫu: tải trước 1 lần, giải mã khi đã có AudioContext
  const SAMPLES = ["hit1", "hit2", "hit3", "crit", "hurt", "block", "coins", "draw", "slice", "door"];
  const raw = {}, decoded = {};
  for (const n of SAMPLES) fetch(`/static/game/sfx/${n}.ogg`).then((r) => r.ok ? r.arrayBuffer() : null).then((b) => { if (b) raw[n] = b; }).catch(() => {});
  function sample(name, vol = 0.6) {
    const c = ac(); if (!c || !enabled) return;
    const go = (buf) => {
      const s = c.createBufferSource(), g = c.createGain();
      g.gain.value = vol; s.buffer = buf; s.connect(g); g.connect(master); s.start(); until(c.currentTime + buf.duration);
    };
    if (decoded[name]) return go(decoded[name]);
    if (!raw[name]) return;
    until(c.currentTime + 0.8);      // đang giải mã lần đầu: coi như đang có tiếng để Hami không nói chồng
    const b = raw[name]; delete raw[name];
    c.decodeAudioData(b).then((buf) => { decoded[name] = buf; go(buf); }).catch(() => {});
  }

  return {
    set(on) { enabled = !!on; },
    busy() { return !!ctx && ctx.currentTime < endAt; },   // đang có hiệu ứng phát (Hami chờ, không nói chồng)
    sample,
    tick(urgent) { tone(urgent ? 1320 : 990, 0, 0.06, { type: "square", vol: 0.18 }); },
    whoosh() { noise(0, 0.35, { vol: 0.35, hp: 400, lp: 5000 }); tone(300, 0, 0.35, { slide: 3, vol: 0.12, type: "triangle" }); },
    pop() { tone(660 + Math.random() * 220, 0, 0.07, { type: "triangle", vol: 0.22, slide: 1.6 }); },
    ding() { [880, 1320, 1760].forEach((f, i) => tone(f, i * 0.09, 0.45, { type: "sine", vol: 0.35 })); },
    buzz() { tone(180, 0, 0.35, { type: "sawtooth", vol: 0.15, slide: 0.7 }); },
    sparkle() { [1568, 2093, 2637, 3136].forEach((f, i) => tone(f, i * 0.06, 0.25, { vol: 0.18 })); },
    drum() { for (let i = 0; i < 10; i++) noise(i * 0.05, 0.05, { vol: 0.18 + i * 0.02, hp: 120, lp: 1200 }); },
    fanfare(big) {
      const notes = big ? [523, 659, 784, 1047, 784, 1047] : [523, 659, 784, 1047];
      notes.forEach((f, i) => tone(f, i * 0.12, i === notes.length - 1 ? 0.6 : 0.16, { type: "square", vol: 0.14 }));
      if (big) noise(0.5, 0.9, { vol: 0.18, hp: 1500 });
    },
  };
})();
