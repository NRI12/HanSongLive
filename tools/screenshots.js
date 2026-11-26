/* Chụp overlay 540x960 ở mọi màn (vùng an toàn + bot) để kiểm tra bố cục.
   Chạy trên một server THỬ (bản sao DB, chế độ thử), không phải server đang live:
     DATA_DIR=/tmp/x LIVE_PASSWORD= .venv/bin/uvicorn app.main:app --port 8101
     node tools/screenshots.js http://127.0.0.1:8101 /tmp/out [http://127.0.0.1:8000]
   Tham số 3 = HanSong (thật hoặc giả) mà server thử đang dùng: công cụ tra nghĩa từ để biết đáp án đúng của câu Hàn → Việt,
   nhờ đó điều khiển được màn hạ quái / quái phản đòn. Cần google-chrome; Playwright lấy từ tu-tien-online (xem CLAUDE.md). */
const { chromium } = require(process.env.PLAYWRIGHT || "/home/nri12/betaka/tu-tien-online/node_modules/playwright");
const B = process.argv[2] || "http://127.0.0.1:8101", out = process.argv[3] || ".", HS = process.argv[4] || "http://127.0.0.1:8000";
const call = (m, p, b) => fetch(B + p, { method: m, headers: { "Content-Type": "application/json" }, body: b && JSON.stringify(b) });
const st = async () => (await (await fetch(B + "/api/overlay/state")).json());
const N = ["Minh Anh", "Tuấn", "Hà Linh", "Bảo", "Thu Trang", "Khoa", "Ngọc", "Duy", "Mai", "Phúc", "Lan", "Quân", "Nguyễn Thị Phương Thảo Xinh Đẹp"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waitPhase = async (p) => { for (let i = 0; i < 60 && (await st()).phase !== p; i++) await sleep(200); };
const game = (action) => call("POST", "/api/game", { action });
const cfg = (game) => call("PUT", "/api/config", { game });
let MEANING = {};
async function rightIdx() {           // đáp án đúng của câu Hàn → Việt (tra nghĩa từ HanSong)
  const Q = (await st()).question;
  if (!Q) return -1;
  return Q.options.indexOf(MEANING[Q.prompt] ?? "") ;
}
// n người trả lời, `good` người đầu đúng (cần câu ko2vi), còn lại sai
async function answer(n, good) {
  const r = await rightIdx();
  for (let i = 0; i < n; i++) {
    const idx = r < 0 ? Math.floor(Math.random() * 4) : i < good ? r : (r + 1 + (i % 3)) % 4;
    await call("POST", "/api/mock", { name: N[i], text: "ABCD"[idx] });
  }
}
// bỏ qua tới khi đang hỏi
async function toQuestion() { for (let i = 0; i < 6 && (await st()).phase !== "question"; i++) { await game("skip"); await sleep(150); } }

(async () => {
  const words = await (await fetch(HS + "/api/words")).json().catch(() => []);
  for (const w of words) MEANING[w.korean] = w.vietnamese;
  await call("POST", "/api/connect", { mode: "mock" });
  await cfg({ mode: "ko2vi", question_s: 120, reveal_s: 120, clear_s: 120, hearts: 3, turns: 4, boss_every: 3, vote: 1,
    safe: 1, bot: 1, bot_voice: 0, sfx: 1, like_goal: 300, share_goal: 10 });
  await game("pause"); await game("reset");
  const br = await chromium.launch({ executablePath: "/usr/bin/google-chrome" });
  const pg = await br.newPage({ viewport: { width: 540, height: 960 } });
  pg.on("pageerror", (e) => console.log("pageerror:", e.message));
  const shot = async (n, w = 1500) => { await pg.waitForTimeout(w); await pg.screenshot({ path: `${out}/n-${n}.png` }); console.log("shot", n); };
  await pg.goto(B + "/overlay"); await shot("00-idle", 1200);

  // ải 1: quái xuất hiện, câu hỏi, đòn đánh, hạ quái + bình chọn cửa
  for (const x of N) await call("POST", "/api/mock", { type: "join", name: x });
  await game("start"); await shot("01-spawn", 500);
  await answer(13, 9); await shot("02-question", 1800);
  await game("skip"); await shot("03-reveal-hits", 900); await shot("04-reveal", 2600);
  // đánh tiếp cho tới khi quái gục
  for (let i = 0; i < 8 && (await st()).phase !== "clear"; i++) { await game("skip"); await sleep(200); if ((await st()).phase === "question") { await answer(13, 12); await game("skip"); await sleep(300); } }
  await waitPhase("clear");
  for (let i = 0; i < 7; i++) await call("POST", "/api/mock", { name: N[i], text: String(1 + (i % 3)) });
  await shot("05-clear-vote", 2500);

  // quái tàng hình (câu nghe) + phản đòn
  await game("stealth"); await game("skip"); await waitPhase("question");
  await answer(10, 0); await shot("06-listen", 1500);
  await game("skip"); await shot("07-attack", 3400);

  // các dạng câu khác
  for (const [mode, name] of [["cloze", "08-cloze"], ["hanviet", "10-hanviet"], ["vi2ko", "11-vi2ko"], ["trans", "09-trans"]]) {
    await game("pause"); await game("reset"); await cfg({ mode }); await game("start"); await answer(6, 0); await shot(name, 2400);
  }
  await game("skip"); await shot("12-trans-reveal", 2500);
  await game("pause"); await game("reset"); await cfg({ mode: "ko2vi" }); await game("start");

  // thua: đánh trượt tới hết tim
  for (let i = 0; i < 6 && (await st()).phase !== "fail"; i++) {
    await toQuestion(); await answer(8, 0); await game("skip"); await sleep(300);
    if ((await st()).phase === "reveal") await game("skip");
    await sleep(200);
  }
  await waitPhase("fail"); await shot("13-fail", 1500);

  // boss
  await game("boss"); await game("skip"); await waitPhase("question"); await shot("14-boss-spawn", 600); await answer(13, 7); await shot("15-boss", 1800);
  // thông báo lớn: đủ mốc tim
  await call("POST", "/api/mock", { type: "like", name: "Lan", count: 300 }); await shot("16-alert", 900);
  await pg.goto(B + "/overlay?guide=1"); await shot("17-guide", 1500);
  await br.close();
})();
