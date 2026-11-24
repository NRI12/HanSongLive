/* Chụp overlay 540x960 ở mọi màn (vùng an toàn + bot) để kiểm tra bố cục.
   Chạy trên một server THỬ (bản sao DB, chế độ thử), không phải server đang live:
     DATA_DIR=/tmp/x LIVE_PASSWORD= .venv/bin/uvicorn app.main:app --port 8101
     node tools/screenshots.js http://127.0.0.1:8101 /tmp/out
   Cần google-chrome; Playwright lấy từ tu-tien-online (xem CLAUDE.md). */
const { chromium } = require(process.env.PLAYWRIGHT || "/home/nri12/betaka/tu-tien-online/node_modules/playwright");
const B = process.argv[2] || "http://127.0.0.1:8101", out = process.argv[3] || ".";
const call = (m, p, b) => fetch(B + p, { method: m, headers: { "Content-Type": "application/json" }, body: b && JSON.stringify(b) });
const st = async () => (await (await fetch(B + "/api/overlay/state")).json());
const N = ["Minh Anh", "Tuấn", "Hà Linh", "Bảo", "Thu Trang", "Khoa", "Ngọc", "Duy", "Mai", "Phúc", "Lan", "Quân", "Nguyễn Thị Phương Thảo"];
const ans = async (n = 13) => { for (const x of N.slice(0, n)) await call("POST", "/api/mock", { name: x, text: "ABCD"[Math.floor(Math.random() * 4)] }); };
const waitPhase = async (p) => { for (let i = 0; i < 40 && (await st()).phase !== p; i++) await new Promise((r) => setTimeout(r, 250)); };
(async () => {
  await call("POST", "/api/connect", { mode: "mock" });
  await call("PUT", "/api/config", { game: { mode: "ko2vi", question_s: 120, reveal_s: 120, board_s: 120, board_every: 0, boss_every: 0, listen_every: 0,
    safe: 1, bot: 1, bot_voice: 0, vote: 0, round_len: 3, sfx: 1 } });
  await call("POST", "/api/game", { action: "pause" }); await call("POST", "/api/game", { action: "reset" });
  const br = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
  const pg = await br.newPage({ viewport: { width: 540, height: 960 } });
  const shot = async (n, w = 1500) => { await pg.waitForTimeout(w); await pg.screenshot({ path: `${out}/n-${n}.png` }); };
  await pg.goto(B + "/overlay"); await shot("0-idle", 800);
  for (let i = 0; i < 13; i++) await call("POST", "/api/mock", { name: N[i], text: i % 2 ? "đội xanh" : "đội đỏ" });
  await call("POST", "/api/game", { action: "start" }); await shot("1-splash", 350);
  await ans(); await shot("2-question", 1600);
  await call("POST", "/api/game", { action: "skip" }); await shot("3-reveal", 1200);
  await call("PUT", "/api/config", { game: { mode: "trans" } }); await call("POST", "/api/game", { action: "skip" }); await ans(6); await shot("4-trans", 1800);
  await call("PUT", "/api/config", { game: { mode: "cloze", reveal_s: 1 } }); await call("POST", "/api/game", { action: "skip" }); await call("POST", "/api/game", { action: "skip" });
  await shot("5-final-splash", 350); await ans(); await shot("6-final", 1600);
  await call("POST", "/api/game", { action: "skip" }); await waitPhase("board"); await shot("7-round-end", 1500);
  await call("PUT", "/api/config", { game: { board_every: 1, vote: 1, round_len: 0, mode: "ko2vi" } });
  await call("POST", "/api/game", { action: "skip" }); await ans(5); await call("POST", "/api/game", { action: "skip" }); await waitPhase("board");
  for (let i = 0; i < 6; i++) await call("POST", "/api/mock", { name: N[i], text: String(1 + (i % 3)) });
  await shot("8-board-vote", 1500);
  await call("PUT", "/api/config", { game: { vote: 0 } });
  await call("POST", "/api/game", { action: "skip" }); await ans(5); await call("POST", "/api/game", { action: "skip" }); await waitPhase("board");
  await shot("9-board", 1500);
  await call("POST", "/api/mock", { type: "gift", name: "Phúc", count: 1, gift_name: "Sư tử", diamonds: 100 }); await shot("10-gift", 900);
  await br.close();
})();
