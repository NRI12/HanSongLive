"use strict";
/* Quái lắp ghép từ bộ phận Kenney "Monster Builder Pack" (CC0, static/game/monster).
   Monster.svg(seed, boss) -> chuỗi <svg> cố định theo seed (cùng seed = cùng con quái trên mọi máy).
   Các nhóm để làm animation: .m-all (thở) · .m-arm-l/.m-arm-r (vung tay, có transform-origin ở vai)
   · .m-eyes / .m-eyes-dead · .m-mouth / .m-mouth-dead (đổi mặt khi bị hạ: thêm class "dead" lên phần tử chứa). */
const Monster = (() => {
  const DIR = "/static/game/monster/";
  const BODY = { A: [330, 330], B: [384, 384], C: [282, 388], D: [348, 364], E: [264, 500], F: [340, 472] };
  const ARM = { A: [164, 352], B: [102, 322], C: [196, 362], D: [184, 394], E: [142, 298] };
  const LEG = { A: [144, 334], B: [110, 298], C: [158, 248], D: [142, 244], E: [204, 218] };
  // điểm khớp (vai / hông) trong ảnh, tính theo tỉ lệ rộng/cao của ảnh
  const ARM_J = { A: [0.27, 0.11], B: [0.33, 0.1], C: [0.27, 0.12], D: [0.3, 0.11], E: [0.4, 0.1] };
  const LEG_J = { A: [0.31, 0.12], B: [0.33, 0.1], C: [0.3, 0.17], D: [0.32, 0.17], E: [0.25, 0.2] };
  const EYE = {
    eye_human: [128, 138], eye_human_blue: [128, 138], eye_human_green: [128, 138], eye_human_red: [128, 138],
    eye_yellow: [128, 138], eye_cute_dark: [128, 138], eye_cute_light: [128, 138],
    eye_psycho_dark: [128, 138], eye_psycho_light: [128, 138], eye_red: [128, 116],
    eye_angry_blue: [128, 116], eye_angry_green: [120, 110], eye_angry_red: [120, 110],
  };
  const CALM_EYES = Object.keys(EYE).filter((k) => !k.includes("angry"));
  const ANGRY_EYES = ["eye_angry_blue", "eye_angry_green", "eye_angry_red"];
  const MOUTH = { mouthA: [140, 68], mouthB: [140, 68], mouthC: [156, 76], mouthD: [132, 54], mouthE: [124, 78],
    mouthF: [148, 84], mouthG: [100, 88], mouthH: [156, 104], mouthI: [148, 84], mouthJ: [144, 96],
    mouth_closed_fangs: [104, 40], mouth_closed_happy: [160, 48], mouth_closed_teeth: [132, 52] };
  const BOSS_MOUTHS = ["mouthB", "mouthC", "mouthF", "mouthH", "mouthJ", "mouth_closed_fangs"];
  const DETAIL = { antenna_large: [76, 116, 0.5, 0.95], antenna_small: [52, 84, 0.5, 0.95], ear: [76, 88, 0.2, 0.9],
    ear_round: [108, 108, 0.35, 0.85], horn_large: [80, 84, 0.2, 0.9], horn_small: [62, 54, 0.2, 0.9] };
  const BROW = { eyebrowA: [98, 64], eyebrowB: [104, 66], eyebrowC: [114, 66] };
  const COLORS = ["blue", "green", "red", "yellow", "white", "dark"];

  function rng(seed) {          // mulberry32
    let a = seed >>> 0;
    return () => {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const pick = (r, a) => a[Math.floor(r() * a.length)];

  function spec(seed, boss) {
    const r = rng(seed);
    const color = boss ? pick(r, ["red", "dark", "dark", "green"]) : pick(r, COLORS);
    const limb = pick(r, COLORS.filter((c) => c !== color));
    return {
      color, limb: r() < 0.6 ? color : limb,
      body: pick(r, Object.keys(BODY)), arm: pick(r, Object.keys(ARM)), leg: pick(r, Object.keys(LEG)),
      eyes: boss ? pick(r, [1, 2, 2, 3]) : pick(r, [1, 1, 2, 2, 2, 3]),
      eye: boss ? pick(r, ANGRY_EYES) : pick(r, CALM_EYES),
      mouth: boss ? pick(r, BOSS_MOUTHS) : pick(r, Object.keys(MOUTH)),
      detail: boss ? "horn_large" : pick(r, ["", "", ...Object.keys(DETAIL)]),
      brow: boss ? pick(r, Object.keys(BROW)) : (r() < 0.25 ? pick(r, Object.keys(BROW)) : ""),
    };
  }

  // đường viền trên của thân (xấp xỉ elip; thân A gần vuông) -> chỗ gắn sừng/tai
  function topY(body, fx) {
    const [, h] = BODY[body];
    if (body === "A") return h * 0.04;
    const d = Math.min(1, Math.abs(fx - 0.5) / 0.5);
    return h * (0.5 - 0.5 * Math.sqrt(1 - d * d)) + h * 0.03;
  }

  function build(seed, boss) {
    const s = spec(seed, boss);
    const [bw, bh] = BODY[s.body];
    const parts = [];          // {cls, src, x, y, w, h, flip, cx}
    const img = (cls, src, x, y, w, h, flip = false) => parts.push({ cls, src, x, y, w, h, flip, cx: x + w / 2 });
    const tall = bh / bw > 1.25;
    // tay: vai ở mép thân, ảnh gốc là tay phải
    const [aw, ah] = ARM[s.arm], [ajx, ajy] = ARM_J[s.arm];
    const shY = bh * (tall ? 0.48 : 0.52);
    const shR = [bw * 0.9, shY], shL = [bw * 0.1, shY];
    const armR = { x: shR[0] - ajx * aw, y: shR[1] - ajy * ah };
    img("m-arm-r", `arm_${s.limb}${s.arm}`, armR.x, armR.y, aw, ah);
    // tay trái = lật tay phải quanh vai trái
    img("m-arm-l", `arm_${s.limb}${s.arm}`, shL[0] - (aw - ajx * aw), armR.y, aw, ah, true);
    // chân
    const [lw, lh] = LEG[s.leg], [ljx, ljy] = LEG_J[s.leg];
    const hipY = bh * (tall ? 0.9 : 0.84);
    img("m-leg-r", `leg_${s.limb}${s.leg}`, bw * 0.66 - ljx * lw, hipY - ljy * lh, lw, lh);
    img("m-leg-l", `leg_${s.limb}${s.leg}`, bw * 0.34 - (lw - ljx * lw), hipY - ljy * lh, lw, lh, true);
    // sừng / tai / râu: 1 cặp trên đỉnh
    if (s.detail) {
      const [dw, dh, dax, day] = DETAIL[s.detail];
      const k = boss ? 1.5 : 1.15;
      const fx = s.detail.startsWith("antenna") ? 0.62 : 0.74;
      const y = topY(s.body, fx) - day * dh * k + dh * k * 0.25;
      img("m-det", `detail_${s.color}_${s.detail}`, bw * fx - dax * dw * k, y, dw * k, dh * k);
      img("m-det", `detail_${s.color}_${s.detail}`, bw * (1 - fx) - (1 - dax) * dw * k, y, dw * k, dh * k, true);
    }
    img("m-body", `body_${s.color}${s.body}`, 0, 0, bw, bh);
    // mặt
    const k = bw / 330;
    const fy = bh * (tall ? 0.3 : 0.4);
    const es = (s.eyes === 1 ? 1.35 : s.eyes === 2 ? 0.95 : 0.78) * k;
    const pos = s.eyes === 1 ? [[0, 0]] : s.eyes === 2 ? [[-0.2, 0], [0.2, 0]] : [[-0.24, 0.05], [0.24, 0.05], [0, -0.13]];
    const [ew, eh] = EYE[s.eye];
    for (const [px, py] of pos) {
      const cx = bw / 2 + px * bw, cy = fy + py * bw;
      img("m-eye", s.eye, cx - (ew * es) / 2, cy - (eh * es) / 2, ew * es, eh * es);
      img("m-eye-dead", "eye_dead", cx - 32 * es, cy - 32 * es, 64 * es, 64 * es);
    }
    if (s.brow) {
      const [ww, wh] = BROW[s.brow];
      const by = fy - (eh * es) / 2 - wh * k * 0.55;
      const xs = s.eyes === 1 ? [0] : [-0.2, 0.2];
      for (const [i, px] of xs.entries()) img("m-brow", s.brow, bw / 2 + px * bw - (ww * k) / 2, by, ww * k, wh * k, i === 0 && xs.length > 1);
    }
    const [mw, mh] = MOUTH[s.mouth];
    const my = bh * (tall ? 0.56 : 0.68);
    const ms = k * (boss ? 1.25 : 1.05);
    img("m-mouth", s.mouth, bw / 2 - (mw * ms) / 2, my - (mh * ms) / 2, mw * ms, mh * ms);
    img("m-mouth-dead", "mouth_closed_sad", bw / 2 - 52 * ms, my - 20 * ms, 104 * ms, 40 * ms);

    // khung bao + dời về gốc 0,0 để transform-origin (px theo viewBox) dễ tính
    const minX = Math.min(...parts.map((p) => p.x)), minY = Math.min(...parts.map((p) => p.y));
    const maxX = Math.max(...parts.map((p) => p.x + p.w)), maxY = Math.max(...parts.map((p) => p.y + p.h));
    const pad = 6, W = maxX - minX + pad * 2, H = maxY - minY + pad * 2;
    const ox = -minX + pad, oy = -minY + pad;
    const tag = (p) => {
      const x = p.x + ox, y = p.y + oy;
      const tf = p.flip ? ` transform="matrix(-1 0 0 1 ${(2 * (x + p.w / 2)).toFixed(1)} 0)"` : "";
      return `<image href="${DIR}${p.src}.png" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${p.w.toFixed(1)}" height="${p.h.toFixed(1)}"${tf}/>`;
    };
    const grp = (cls, extra = "") => `<g class="${cls}"${extra}>${parts.filter((p) => p.cls === cls).map(tag).join("")}</g>`;
    const origin = (x, y) => ` style="transform-origin:${(x + ox).toFixed(1)}px ${(y + oy).toFixed(1)}px"`;
    return {
      W, H, feet: (maxY + oy) / H,
      svg: `<svg class="mon-svg" preserveAspectRatio="xMidYMax meet" viewBox="0 0 ${W.toFixed(1)} ${H.toFixed(1)}" aria-hidden="true">
        <ellipse class="m-shadow" cx="${(bw / 2 + ox).toFixed(1)}" cy="${(maxY + oy - 8).toFixed(1)}" rx="${(bw * 0.55).toFixed(1)}" ry="${(bw * 0.09).toFixed(1)}"/>
        <g class="m-all"${origin(bw / 2, maxY)}>
          ${grp("m-leg-l")}${grp("m-leg-r")}
          ${grp("m-arm-l", origin(shL[0], shL[1]))}${grp("m-arm-r", origin(shR[0], shR[1]))}
          ${grp("m-det")}
          <g class="m-torso"${origin(bw / 2, bh)}>${grp("m-body")}${grp("m-eye")}${grp("m-eye-dead")}${grp("m-brow")}${grp("m-mouth")}${grp("m-mouth-dead")}</g>
        </g></svg>`,
    };
  }

  const cache = new Map();
  return {
    svg(seed, boss = false) {
      const key = seed + ":" + (boss ? 1 : 0);
      if (!cache.has(key)) { cache.set(key, build(seed, boss)); if (cache.size > 30) cache.delete(cache.keys().next().value); }
      return cache.get(key).svg;
    },
    spec,
  };
})();
