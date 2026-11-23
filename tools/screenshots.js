/* Chụp overlay 540x960 ở mọi màn (vùng an toàn + bot) để kiểm tra bố cục.
   Chạy trên một server THỬ (bản sao DB, chế độ thử), không phải server đang live:
     DATA_DIR=/tmp/x LIVE_PASSWORD= .venv/bin/uvicorn app.main:app --port 8101
     node tools/screenshots.js http://127.0.0.1:8101 /tmp/out
   Cần google-chrome; Playwright lấy từ tu-tien-online (xem CLAUDE.md). */
const { chromium } = require(process.env.PLAYWRIGHT || "/home/nri12/betaka/tu-tien-online/node_modules/playwright");
const B = process.argv[2] || "http://127.0.0.1:8101", out = process.argv[3] || ".";
const call = (m, p, b) => fetch(B + p, { method: m, headers: { "Content-Type": "application/json" }, body: b && JSON.stringify(b) });
const st = async () => (await (await fetch(B + "/api/overlay/state")).json());
const NAMES = ["Minh Anh", "Tuấn", "Hà Linh", "Bảo", "Thu Trang", "Khoa", "Ngọc", "Duy", "Mai", "Phúc", "Lan", "Quân", "Nguyễn Thị Phương Thảo"];
const answerAll = async (n = 13) => { for (const x of NAMES.slice(0, n)) await call("POST", "/api/mock", { name: x, text: "ABCD"[Math.floor(Math.random() * 4)] }); };
const toQuestion = async (mode) => { await call("PUT", "/api/config", { game: { mode } }); await call("POST", "/api/game", { action: "pause" }); await call("POST", "/api/game", { action: "start" }); };
(async () => {
  await call("POST", "/api/connect", { mode: "mock" });
  await call("PUT", "/api/config", { game: { mode: "ko2vi", question_s: 120, reveal_s: 120, board_s: 120, board_every: 0, boss_every: 0, listen_every: 0, safe: 1, bot: 1, vote: 1 } });
  await call("POST", "/api/game", { action: "pause" }); await call("POST", "/api/game", { action: "reset" });
  const br = await chromium.launch({ executablePath: "/usr/bin/google-chrome", args: ["--autoplay-policy=no-user-gesture-required"] });
  const pg = await br.newPage({ viewport: { width: 540, height: 960 } });
  const shot = async (n, wait = 1500) => { await pg.waitForTimeout(wait); await pg.screenshot({ path: `${out}/${n}.png` }); };
  await pg.goto(B + "/overlay"); await pg.waitForTimeout(800);
  await shot("t0-idle", 300);
  for (let i = 0; i < 13; i++) await call("POST", "/api/mock", { name: NAMES[i], text: i % 2 ? "đội xanh" : "đội đỏ" });
  for (const m of ["ko2vi", "cloze", "trans", "hanviet"]) {
    await toQuestion(m); await answerAll(); await shot(`t1-q-${m}`);
    await call("POST", "/api/game", { action: "skip" }); await shot(`t2-r-${m}`);
  }
  await call("PUT", "/api/config", { game: { board_every: 1, reveal_s: 1 } });
  await toQuestion("ko2vi"); await answerAll(5); await call("POST", "/api/game", { action: "skip" });
  for (let i = 0; i < 20 && (await st()).phase !== "board"; i++) await pg.waitForTimeout(300);
  for (let i = 0; i < 6; i++) await call("POST", "/api/mock", { name: NAMES[i], text: String(1 + (i % 3)) });
  await shot("t3-board-vote");
  await call("PUT", "/api/config", { game: { vote: 0 } });
  await call("POST", "/api/game", { action: "skip" }); await answerAll(5); await call("POST", "/api/game", { action: "skip" });
  for (let i = 0; i < 20 && (await st()).phase !== "board"; i++) await pg.waitForTimeout(300);
  await shot("t4-board");
  console.log("board phase:", (await st()).phase);
  await br.close();
})();
