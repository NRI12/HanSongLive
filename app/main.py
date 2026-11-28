"""HanSongLive: game "Săn Quái Chữ" tiếng Hàn trên TikTok LIVE (cả phòng comment A/B/C/D để đánh quái), lấy dữ liệu từ HanSong.

Trang:
  /admin              bảng điều khiển (cần LIVE_PASSWORD nếu có đặt)
  /overlay?k=<token>  màn hình đưa lên TikTok LIVE Studio / OBS (Browser source 1080x1920)
"""
import asyncio
import hashlib
import json
import hmac
import os
import random
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, bot, db, live, plan, viewers
from .source import HanSongSource, SourceError
from .tiktok import TikTokConnector

LIVE_PASSWORD = os.environ.get("LIVE_PASSWORD", "")
SECRET = os.environ.get("LIVE_SECRET", "") or hashlib.sha256(("hansonglive:" + LIVE_PASSWORD).encode()).hexdigest()
STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


def _sign(msg: str) -> str:
    return hmac.new(SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()


def overlay_token() -> str:
    return _sign("overlay")[:32]


# ---------------------------------------------------------------- state
def hansong_conf() -> dict:
    return {"url": db.get_conf("hansong.url") or os.environ.get("HANSONG_URL", "http://127.0.0.1:8000"),
            "password": db.get_conf("hansong.password") or os.environ.get("HANSONG_PASSWORD", "")}


def tiktok_conf() -> dict:
    return {"username": db.get_conf("tiktok.username") or os.environ.get("TIKTOK_USERNAME", ""),
            "sign_key": db.get_conf("tiktok.sign_key") or os.environ.get("TIKTOK_SIGN_API_KEY", "")}


SOURCE: HanSongSource | None = None


def source() -> HanSongSource:
    global SOURCE
    c = hansong_conf()
    if SOURCE is None or SOURCE.base_url != c["url"].rstrip("/") or SOURCE.password != c["password"]:
        SOURCE = HanSongSource(c["url"], c["password"])
    return SOURCE


def picker(recent: set, cfg: dict):
    if not cfg.get("forced"):              # đang chạy 1 buổi trong lộ trình: ra đúng câu kế tiếp của buổi đó
        q, finished = plan.next_question()
        if finished:
            GAME._push("system", "🎉 Đã chạy hết buổi học trong lộ trình! Quay về câu hỏi thường", alert=True, tier=2)
        if q:
            if q.get("word_id", 0) > 0:
                threading.Thread(target=source().prefetch, args=(q["word_id"],), daemon=True).start()
            return q
    try:
        words = source().words(cfg["source"])
    except SourceError:
        return None
    q = live.make_question(cfg["mode"], words, recent, live.load_items(words), last=cfg.get("last_mode"))
    if q:   # tải sẵn âm thanh câu này ở nền
        threading.Thread(target=source().prefetch, args=(q["word_id"],), daemon=True).start()
    return q


def pairs_picker(n: int, cfg: dict) -> list[dict] | None:
    """Ải lật thẻ: n từ ngẫu nhiên, chữ Hàn và nghĩa đều khác nhau, nghĩa đủ ngắn để vừa 1 thẻ."""
    try:
        words = source().words(cfg["source"])
    except SourceError:
        return None
    pool = [w for w in words if w.get("korean") and w.get("vietnamese") and len(w["vietnamese"]) <= 24]
    random.shuffle(pool)
    out, ko, vi = [], set(), set()
    for w in pool:
        k, v = live.plain(w["korean"]), live.plain(w["vietnamese"])
        if k in ko or v in vi:
            continue
        ko.add(k); vi.add(v); out.append(w)
        if len(out) >= n:
            break
    for w in out:       # tải sẵn âm thanh: lật trúng cặp thì đọc từ đó
        threading.Thread(target=source().prefetch, args=(w["id"],), daemon=True).start()
    return out


# ---------------------------------------------------------------- AI
def ai_conf() -> dict:
    return ai.DEFAULT_AI | (db.get_conf("ai") or {})


def ai_key(provider: str) -> str:
    if provider == "deepseek":
        return db.get_conf("ai.deepseek_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    return db.get_conf("ai.openai_key") or os.environ.get("OPENAI_API_KEY", "")


AI_JOB = {"running": False, "total": 0, "done": 0, "made": 0, "detail": ""}


AUTO = {"next": time.time() + 60, "failed": {}}   # lần kiểm tra kế tiếp; word_id -> lúc AI làm hỏng
AUTO_EVERY_S = 60          # cứ 1 phút xem có từ mới chưa có câu hỏi AI không
AUTO_BATCH = 30            # mỗi lần tự tạo tối đa 30 từ
AUTO_FAIL_S = 24 * 3600    # từ nào AI làm hỏng (bị loại khi kiểm tra) thì 1 ngày sau mới thử lại, tránh tốn tiền lặp


PARTS = {"vocab": ("cloze", "trans"), "gram": ("gram", "gfix")}


def missing_words(words: list[dict], redo: bool = False, part: str | None = None) -> list[dict]:
    """Từ có câu ví dụ nhưng chưa đủ nội dung AI. part=None: thiếu bất kỳ phần nào (từ vựng hoặc ngữ pháp)."""
    have = live.load_items(words)
    kinds = PARTS[part] if part else PARTS["vocab"] + PARTS["gram"]
    return [w for w in words if w.get("example_ko") and w.get("example_vi")
            and (redo or any(w["id"] not in have[k] for k in kinds))]


def run_ai_job(words: list[dict], cfg: dict, key: str, auto: bool = False, redo: bool = False):
    rows: list = []

    def progress(n_words, n_items):
        AI_JOB["done"] += n_words
        AI_JOB["made"] = len(rows) + n_items
    try:
        # từ vựng (điền từ, dịch câu) rồi ngữ pháp (điền ngữ pháp, câu đúng ngữ pháp): chỉ phần còn thiếu
        needs = {part: missing_words(words, redo, part) for part in PARTS}
        AI_JOB["total"] = sum(len(n) for n in needs.values()) or len(words)
        for part, need in needs.items():
            if need:
                got = ai.generate_items(need, cfg, key, progress=progress, part=part)
                live.save_items(got, words)
                rows += got
        mark_ai(None)
        now = time.time()
        for w in missing_words(words):        # AI làm hỏng từ này: tạm bỏ qua khi tự tạo
            AUTO["failed"][w["id"]] = now
        AI_JOB["detail"] = f"{'Tự tạo' if auto else 'Xong'}: {len(rows)} câu hỏi từ {len(words)} từ"
    except ai.AICreditError as e:
        mark_ai(e)
    except Exception as e:  # lỗi AI/mạng: báo lên admin, không làm chết server
        AI_JOB["detail"] = f"Lỗi: {e}"
    finally:
        AI_JOB["running"] = False


# ---------------------------------------------------------------- lộ trình học theo ngày (app/plan.py)
PLAN_JOB = {"running": False, "detail": "", "failed_day": "", "failed_at": 0.0}
PLAN_AUTO = {"next": time.time() + 90}
PLAN_AUTO_EVERY_S = 600       # cứ 10 phút xem hôm nay đã có buổi học chưa


def run_plan_job(new: list[int] | None = None):
    try:
        cfg = ai_conf()
        key = ai_key(cfg["provider"])
        words = source().words("all")
        p = plan.create(words, live.load_items(words), cfg, key, new=new)
        PLAN_JOB["detail"] = f"Xong: buổi #{p['id']} · {len(p['questions'])} câu · {p['title']}"
        threading.Thread(target=warm_plan, args=(p["id"],), daemon=True).start()
    except ai.AICreditError as e:
        mark_ai(e)
        PLAN_JOB.update(detail=f"Lỗi: {e}", failed_day=__import__("datetime").date.today().isoformat(), failed_at=time.time())
    except Exception as e:
        PLAN_JOB.update(detail=f"Lỗi: {e}", failed_day=__import__("datetime").date.today().isoformat(), failed_at=time.time())
    finally:
        PLAN_JOB["running"] = False


def start_plan_job(new: list[int] | None = None) -> bool:
    if PLAN_JOB["running"] or not ai_key(ai_conf()["provider"]):
        return False
    PLAN_JOB.update(running=True, detail="Đang soạn buổi học (khoảng 1 phút)…")
    threading.Thread(target=run_plan_job, args=(new,), daemon=True).start()
    return True


def plan_auto():
    """Mỗi ngày tự soạn sẵn 1 buổi (nếu hôm nay chưa có) để chủ kênh xem trước ở /plan. Lỗi thì 1 tiếng sau mới thử lại."""
    now = time.time()
    if now < PLAN_AUTO["next"]:
        return
    PLAN_AUTO["next"] = now + PLAN_AUTO_EVERY_S
    today = __import__("datetime").date.today().isoformat()
    if not ai_conf().get("auto") or PLAN_JOB["running"] or not plan.next_points(1):
        return
    if PLAN_JOB["failed_day"] == today and now - PLAN_JOB["failed_at"] < 3600:
        return
    if GAME.ai_down and now - BOT["down_at"] < AI_RETRY_S:
        return
    if not db.q1("SELECT id FROM live_plans WHERE day=?", (today,)):
        start_plan_job()


GAME = live.LiveGame(picker, pairs_picker=pairs_picker)
CONNECTOR: TikTokConnector | None = None
BOOT_ID = os.urandom(4).hex()   # mã phiên server, xem overlay_state
STATUS = {"mode": "off", "state": "idle", "detail": "Chưa kết nối", "attempt": 0}
LOOP: asyncio.AbstractEventLoop | None = None


def set_status(s: dict):
    STATUS.clear()
    STATUS.update(s)


BOT = {"busy": False, "last": 0.0, "down_at": 0.0}
BOT_GAP_S = 5          # tối đa 1 lần gọi AI / 5 giây cho cả phòng
AI_RETRY_S = 15 * 60   # API hết tiền: 15 phút sau mới thử gọi lại (hoặc ngay khi lưu key mới)


def mark_ai(err: Exception | None):
    """Ghi nhận trạng thái API AI thật sự: hết tiền / key sai / chạy lại được."""
    if isinstance(err, ai.AICreditError):
        BOT["down_at"] = time.time()
        GAME.set_ai_down(err.kind)
        AI_JOB["detail"] = f"⚠️ {err}"
    elif err is None and GAME.ai_down:
        GAME.set_ai_down("")


def bot_answer(ask: dict):
    try:
        cfg = ai_conf()
        reply = ai.bot_reply(cfg, ai_key(cfg["provider"]), ask["name"], ask["text"])
        mark_ai(None)
        GAME.bot_reply(ask["name"], ask["text"], reply)
    except ai.AICreditError as e:
        mark_ai(e)
        GAME.bot_unavailable(ask["name"])
    except Exception as e:  # AI lỗi/timeout lặt vặt: bỏ qua câu này, không làm phiền màn hình live
        print(f"bot AI lỗi: {type(e).__name__}", flush=True)
    finally:
        BOT["busy"] = False
        BOT["last"] = time.time()


def bot_pump():
    if BOT["busy"] or time.time() - BOT["last"] < BOT_GAP_S:
        return
    with GAME.lock:
        if not GAME.bot_asks:
            return
        ask = GAME.bot_asks.popleft()
    if not ai_key(ai_conf()["provider"]):
        return
    if GAME.ai_down and time.time() - BOT["down_at"] < AI_RETRY_S:
        GAME.bot_unavailable(ask["name"])       # chưa tới lúc thử lại: không tốn request
        return
    BOT["busy"] = True
    threading.Thread(target=bot_answer, args=(ask,), daemon=True).start()


def auto_check():
    """Tự tạo câu hỏi AI cho từ mới (HanSong thêm 20 từ/ngày). Không chạy khi: tắt auto, đang có job,
    chưa có key, hoặc API đang hết tiền/key sai và chưa tới lúc thử lại."""
    now = time.time()
    if now < AUTO["next"]:
        return
    AUTO["next"] = now + AUTO_EVERY_S
    cfg = ai_conf()
    key = ai_key(cfg["provider"])
    if not cfg.get("auto") or AI_JOB["running"] or not key:
        return
    if GAME.ai_down and now - BOT["down_at"] < AI_RETRY_S:
        return
    try:
        words = source().words("all")
    except SourceError:
        return
    todo = [w for w in missing_words(words) if now - AUTO["failed"].get(w["id"], -1e18) >= AUTO_FAIL_S]
    if not todo:
        return
    todo = sorted(todo, key=lambda w: -w["id"])[:AUTO_BATCH]      # từ mới nhất trước
    AI_JOB.update(running=True, total=len(todo), done=0, made=0, detail=f"Tự tạo cho {len(todo)} từ mới…")
    threading.Thread(target=run_ai_job, args=(todo, cfg, key, True), daemon=True).start()


def on_event(ev: dict):
    """Mọi sự kiện TikTok đi qua đây: ghi sổ người xem rồi đưa vào game."""
    try:
        viewers.record(ev)
    except Exception:
        pass   # sổ người xem hỏng không được làm hỏng game
    GAME.handle(ev)


async def ticker():
    last_flush = time.time()
    while True:
        try:
            await asyncio.to_thread(GAME.tick)
            bot_pump()
            voice_pump()
            if time.time() - last_flush >= 5:
                last_flush = time.time()
                await asyncio.to_thread(viewers.flush)
            if time.time() >= AUTO["next"]:
                await asyncio.to_thread(auto_check)
            if time.time() >= PLAN_AUTO["next"]:
                await asyncio.to_thread(plan_auto)
        except Exception as e:  # không để vòng lặp chết
            GAME.message = f"Lỗi: {e}"
        await asyncio.sleep(0.25)


@asynccontextmanager
async def lifespan(_app):
    global LOOP
    LOOP = asyncio.get_running_loop()
    db.conn()
    GAME.configure(db.get_conf("game", {}))
    threading.Thread(target=warm_voices, daemon=True).start()
    t = asyncio.create_task(ticker())
    yield
    t.cancel()
    if CONNECTOR:
        await CONNECTOR.stop()
    viewers.flush()


app = FastAPI(title="HanSongLive", lifespan=lifespan)


# ---------------------------------------------------------------- auth
@app.middleware("http")
async def auth_mw(request: Request, call_next):
    """Không đặt LIVE_PASSWORD = dùng nội bộ, mở hết. Có mật khẩu: API admin cần cookie,
    overlay + âm thanh cần ?k=<token> (để dán link vào OBS/LIVE Studio không phải đăng nhập)."""
    p = request.url.path
    if LIVE_PASSWORD and p not in ("/api/login", "/api/health") and p.startswith(("/api/", "/audio/")):
        admin_ok = hmac.compare_digest(request.cookies.get("hsl_token", ""), _sign("admin"))
        overlay_ok = p.startswith(("/api/overlay/", "/audio/")) and \
            hmac.compare_digest(request.query_params.get("k", ""), overlay_token())
        plan_ok = p.startswith(("/api/plans", "/audio/plan/"))   # trang /plan không cần mật khẩu (người dùng yêu cầu)
        if not (admin_ok or overlay_ok or plan_ok):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


class Login(BaseModel):
    password: str


@app.post("/api/login")
def login(body: Login, response: Response):
    if LIVE_PASSWORD and not hmac.compare_digest(body.password, LIVE_PASSWORD):
        time.sleep(1)
        raise HTTPException(401, "Sai mật khẩu")
    response.set_cookie("hsl_token", _sign("admin"), max_age=3600 * 24 * 365, httponly=True, samesite="lax",
                        secure=os.environ.get("COOKIE_SECURE", "0") == "1")
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- admin
def ai_missing() -> int | None:
    try:
        return len(missing_words(source().words("all")))
    except SourceError:
        return None


def admin_state():
    h, t = hansong_conf(), tiktok_conf()
    return {
        "hansong": {"url": h["url"], "has_password": bool(h["password"]),
                    "error": SOURCE.last_error if SOURCE else ""},
        "tiktok": {"username": t["username"], "has_sign_key": bool(t["sign_key"])},
        "status": dict(STATUS),
        "overlay_path": f"/overlay?k={overlay_token()}",
        "game": GAME.state(),
        "ai": {**ai_conf(), "has_openai_key": bool(ai_key("openai")), "has_deepseek_key": bool(ai_key("deepseek")),
               "down": GAME.ai_down, "voices": list(ai.VOICES),
               "tts": {"has_key": bool(ai_key("openai")), "warm": TTS["warm"], "total": len(bot.static_lines()),
                       "detail": TTS["detail"]},
               "job": dict(AI_JOB), "counts": live.item_counts(), "missing": ai_missing()},
    }


@app.get("/api/admin")
def admin():
    return admin_state()


class ConfigReq(BaseModel):
    hansong_url: str | None = None
    hansong_password: str | None = None
    tiktok_username: str | None = None
    tiktok_sign_key: str | None = None
    game: dict | None = None
    ai: dict | None = None             # provider, model_openai, model_deepseek, verify
    openai_key: str | None = None
    deepseek_key: str | None = None


@app.put("/api/config")
def put_config(body: ConfigReq):
    if body.hansong_url is not None:
        url = body.hansong_url.strip()
        if not re.match(r"^https?://[^\s]+$", url):
            raise HTTPException(400, "URL HanSong phải bắt đầu bằng http:// hoặc https://")
        db.set_conf("hansong.url", url)
    if body.hansong_password:            # để trống = giữ mật khẩu cũ
        db.set_conf("hansong.password", body.hansong_password)
    if body.tiktok_username is not None:
        u = body.tiktok_username.strip().lstrip("@")
        if u and not re.match(r"^[\w.]{1,64}$", u):
            raise HTTPException(400, "Tên tài khoản TikTok không hợp lệ")
        db.set_conf("tiktok.username", u)
    if body.tiktok_sign_key:
        db.set_conf("tiktok.sign_key", body.tiktok_sign_key.strip())
    if body.game is not None:
        GAME.configure(body.game)
        db.set_conf("game", GAME.cfg)
    if body.ai is not None:
        cur = ai_conf()
        a = body.ai
        if a.get("provider") in ("openai", "deepseek"):
            cur["provider"] = a["provider"]
        for k in ("model_openai", "model_deepseek"):
            v = str(a.get(k) or "").strip()
            if v:
                if not re.match(r"^[\w.\-:/]{1,80}$", v):
                    raise HTTPException(400, "Tên model không hợp lệ")
                cur[k] = v
        if a.get("voice") in ai.VOICES:
            cur["voice"] = a["voice"]
        for k in ("verify", "auto"):
            if k in a:
                cur[k] = a[k] in (True, 1, "1", "true", "on")
        db.set_conf("ai", cur)
    if body.openai_key:                  # để trống = giữ khoá cũ; khoá không bao giờ được trả về
        db.set_conf("ai.openai_key", body.openai_key.strip())
    if body.deepseek_key:
        db.set_conf("ai.deepseek_key", body.deepseek_key.strip())
    if body.openai_key or body.deepseek_key or (body.ai or {}).get("provider"):
        BOT["down_at"] = 0.0             # key/nhà cung cấp mới: lần hỏi kế tiếp thử gọi AI ngay
    if body.openai_key or (body.ai or {}).get("voice") or (body.game or {}).get("bot_voice") in (1, "1"):
        TTS["down_at"] = 0.0
        TTS["warm"] = 0
        threading.Thread(target=warm_voices, daemon=True).start()
    return admin_state()


class AIGenReq(BaseModel):
    n: int = 30
    redo: bool = False       # tạo lại cả những từ đã có nội dung


@app.post("/api/ai/generate")
def ai_generate(body: AIGenReq):
    if AI_JOB["running"]:
        raise HTTPException(400, "Đang tạo câu hỏi, chờ xong rồi bấm lại")
    cfg = ai_conf()
    key = ai_key(cfg["provider"])
    if not key:
        raise HTTPException(400, f"Chưa có API key cho {cfg['provider']}")
    try:
        words = source().words(GAME.cfg["source"])
    except SourceError as e:
        raise HTTPException(400, str(e))
    todo = missing_words(words, body.redo)
    random.shuffle(todo)
    todo = todo[:max(1, min(300, body.n))]
    if not todo:
        raise HTTPException(400, "Mọi từ trong nguồn đã có câu hỏi AI. Tích 'tạo lại' nếu muốn làm mới.")
    AI_JOB.update(running=True, total=len(todo), done=0, made=0, detail=f"Đang tạo cho {len(todo)} từ…")
    threading.Thread(target=run_ai_job, args=(todo, cfg, key, False, body.redo), daemon=True).start()
    return dict(AI_JOB)


@app.post("/api/ai/clear")
def ai_clear():
    with db.tx() as c:
        c.execute("DELETE FROM live_items")
    return {"ok": True}


@app.post("/api/hansong/check")
def hansong_check():
    s = source()
    with s._lock:
        s._cache.clear()
    return s.check()


@app.post("/api/hansong/clear-audio")
def clear_audio():
    shutil.rmtree(os.path.join(db.DATA_DIR, "audio"), ignore_errors=True)
    return {"ok": True}


class ConnectReq(BaseModel):
    mode: str   # tiktok | mock | off


@app.post("/api/connect")
async def connect(body: ConnectReq):
    global CONNECTOR
    t = tiktok_conf()
    if body.mode == "tiktok" and not t["username"]:   # kiểm tra trước, để lỗi không làm rớt kết nối đang chạy
        raise HTTPException(400, "Nhập tên tài khoản TikTok trước khi kết nối")
    if CONNECTOR:
        await CONNECTOR.stop()
        CONNECTOR = None
    if body.mode == "tiktok":
        CONNECTOR = TikTokConnector(t["username"], t["sign_key"], on_event, set_status)
        CONNECTOR.start()
    elif body.mode == "mock":
        set_status({"mode": "mock", "state": "connected", "detail": "Chế độ thử: gửi comment giả từ bảng điều khiển",
                    "attempt": 0})
    else:
        set_status({"mode": "off", "state": "idle", "detail": "Đã ngắt kết nối", "attempt": 0})
    return dict(STATUS)


class GameReq(BaseModel):
    action: str   # start | pause | skip | reset | boss | double | heart (+1 tim) | fast|stealth|armor|mirror|heal (đặc tính quái sau)


@app.post("/api/game")
def game(body: GameReq):
    act = {"start": GAME.start, "pause": GAME.pause, "skip": GAME.skip, "reset": GAME.reset_scores}.get(body.action)
    if not act and body.action in ("boss", "double", "heart", *live.DOOR_TRAITS):
        act = lambda: GAME.queue(body.action)   # noqa: E731
    if not act:
        raise HTTPException(400, "action không hợp lệ")
    act()
    if body.action in ("start", "skip") and GAME.phase == "idle" and GAME.message:
        raise HTTPException(400, GAME.message + (f". {SOURCE.last_error}" if SOURCE and SOURCE.last_error else ""))
    return GAME.state()


class MockReq(BaseModel):
    type: str = "comment"
    name: str = "Khách"
    text: str = ""
    count: int = 1
    gift_name: str = "Hoa hồng"
    diamonds: int = 1


@app.post("/api/mock")
def mock(body: MockReq):
    if STATUS.get("mode") != "mock":
        raise HTTPException(400, "Bật Chế độ thử trước khi gửi sự kiện giả")
    name = body.name.strip()[:40] or "Khách"
    GAME.handle({"type": body.type, "user": {"id": "mock:" + name, "name": name}, "text": body.text,
                 "count": max(1, min(100000, body.count)), "gift_name": body.gift_name[:40],
                 "diamonds": max(0, min(100000, body.diamonds))})
    return {"ok": True}


@app.get("/api/stats")
def stats():
    return live.round_stats(20)


@app.get("/api/viewers")
def viewer_list(order: str = "recent", limit: int = 100):
    viewers.flush()
    return {"summary": viewers.summary(), "rows": viewers.listing(limit, order)}


@app.get("/api/viewers.csv")
def viewer_csv():
    viewers.flush()
    return Response(viewers.to_csv(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="nguoi-xem.csv"'})


# ---------------------------------------------------------------- overlay
@app.post("/api/overlay/ready")
def overlay_ready(qid: int):
    """Overlay đã đọc đề + Hami nói xong câu `qid`: bắt đầu đếm ngược."""
    return {"ok": GAME.ready(qid)}


@app.post("/api/overlay/hold")
def overlay_hold(qid: int):
    """Overlay còn đang diễn đòn đánh / đọc đáp án / Hami khen của câu `qid`: giữ màn đáp án thêm (có giới hạn)."""
    return {"ok": GAME.hold_reveal(qid)}


def _sig():
    g = GAME
    return (g.ver, g.phase, g.qid, g.bot_seq, g.feed_seq, g.pulse_seq, g.flip_seq, g.hearts, g.read_until, g.phase_end)


@app.get("/api/overlay/stream")
async def overlay_stream(request: Request):
    """Kênh đẩy (Server-Sent Events): có comment / sự kiện / đổi màn là gửi trạng thái ngay (kiểm tra mỗi 30 ms),
    không có gì đổi thì vẫn gửi 4 lần / giây cho đồng hồ đếm ngược. Overlay tự quay về hỏi định kỳ nếu kênh lỗi."""
    async def gen():
        last_sig, last_at = None, 0.0
        while not await request.is_disconnected():
            sig, now = _sig(), time.monotonic()
            if sig != last_sig or now - last_at >= 0.25:
                last_sig, last_at = sig, now
                s = await asyncio.to_thread(overlay_state)
                yield "data: " + json.dumps(s, ensure_ascii=False, separators=(",", ":")) + "\n\n"
            await asyncio.sleep(0.03)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/overlay/state")
def overlay_state():
    boards = None
    if GAME.phase in ("clear", "fail"):
        boards = {"weekly": live.weekly_top(3)}
    s = GAME.state(boards)
    s["connected"] = STATUS.get("state") == "connected"
    s["boot"] = BOOT_ID     # đổi sau mỗi lần khởi động: overlay tự tải lại (số thứ tự câu thoại/feed đã quay về 0)
    return s


# ---------------------------------------------------------------- giọng bot (OpenAI TTS)
TTS = {"down_at": 0.0, "detail": "", "warm": 0}
TTS_LOCKS: dict[str, threading.Lock] = {}
TTS_GUARD = threading.Lock()
TTS_VERSION = "v2"         # đổi khi sửa BOT_VOICE_INSTR để không dùng lại file giọng cũ


def voice_path(text: str) -> str:
    voice = ai_conf().get("voice", "marin")
    h = hashlib.sha1(f"{TTS_VERSION}|{voice}|{text}".encode()).hexdigest()[:20]
    return os.path.join(db.DATA_DIR, "tts", f"{h}.mp3")


def synth(text: str) -> str | None:
    """Câu thoại -> file mp3 giọng Hami (có cache). None nếu không có key / TTS đang hết credit."""
    p = voice_path(text)
    if os.path.exists(p):
        return p
    key = ai_key("openai")
    if not key or time.time() - TTS["down_at"] < AI_RETRY_S:
        return None
    with TTS_GUARD:
        lock = TTS_LOCKS.setdefault(p, threading.Lock())
    with lock:                    # 2 request cùng câu: chỉ gọi TTS 1 lần
        if os.path.exists(p):
            return p
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            ai.tts(text, "vi", ai_conf().get("voice", "marin"), p, key, instructions=ai.BOT_VOICE_INSTR)
            TTS["detail"] = ""
        except ai.AICreditError as e:
            TTS["down_at"] = time.time()
            TTS["detail"] = f"⚠️ Giọng Hami tạm tắt: {e}"
            return None
        except ai.AIError as e:
            TTS["detail"] = f"Lỗi giọng: {str(e)[:120]}"
            return None
    return p


VOICE_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tts")
VOICE = {"seq": 0}


def voice_pump():
    """Câu thoại mới (có tên người xem…) chưa có trong cache: tạo giọng ngay ở luồng nền,
    để lúc overlay xin file thì đã có sẵn, chữ trong bong bóng và tiếng khớp nhau."""
    with GAME.lock:
        new = [l for l in GAME.bot_lines if l["seq"] > VOICE["seq"]]
        if GAME.bot_seq < VOICE["seq"]:          # engine đặt lại số thứ tự
            VOICE["seq"] = 0
    if not new:
        return
    VOICE["seq"] = new[-1]["seq"]
    if not GAME.cfg["bot_voice"] or not ai_key("openai") or time.time() - TTS["down_at"] < AI_RETRY_S:
        return
    for l in new:
        text = bot.speech_text(l["text"])
        if text and not os.path.exists(voice_path(text)):
            VOICE_POOL.submit(synth, text)


def synth_ko(text: str) -> str | None:
    """Câu tiếng Hàn tự đặt của lộ trình -> mp3 (giọng đọc chuẩn Seoul, cache)."""
    voice = ai_conf().get("voice", "marin")
    h = hashlib.sha1(f"ko1|{voice}|{text}".encode()).hexdigest()[:20]
    p = os.path.join(db.DATA_DIR, "tts", f"ko_{h}.mp3")
    if os.path.exists(p):
        return p
    key = ai_key("openai")
    if not key or time.time() - TTS["down_at"] < AI_RETRY_S:
        return None
    with TTS_GUARD:
        lock = TTS_LOCKS.setdefault(p, threading.Lock())
    with lock:
        if os.path.exists(p):
            return p
        os.makedirs(os.path.dirname(p), exist_ok=True)
        try:
            ai.tts(text, "ko", voice, p, key)
        except ai.AICreditError as e:
            TTS["down_at"] = time.time()
            TTS["detail"] = f"⚠️ Giọng đọc tạm tắt: {e}"
            return None
        except ai.AIError:
            return None
    return p


def _plan_text(pid: int, i: int) -> str:
    p = plan.load(pid)
    url = f"/audio/plan/{pid}/{i}.mp3"
    q = next((q for q in (p or {}).get("questions", []) if q.get("audio_url") == url), None)
    return (q or {}).get("word", {}).get("example_ko", "")


def warm_plan(pid: int):
    """Tạo sẵn giọng đọc các câu ngữ pháp của buổi (để lúc live hiện đáp án là đọc ngay)."""
    p = plan.load(pid)
    for q in (p or {}).get("questions", []):
        t = q.get("word", {}).get("example_ko", "") if q.get("audio_url") else ""
        if t and synth_ko(t) is None:
            return


@app.get("/audio/plan/{pid}/{i}.mp3")
def plan_audio(pid: int, i: int):
    """Chỉ đọc câu có trong lộ trình đã lưu (không nhận chữ tuỳ ý)."""
    text = _plan_text(pid, i)
    if not text:
        raise HTTPException(404, "Không có câu này")
    p = synth_ko(text)
    if not p:
        raise HTTPException(404, "Chưa có giọng đọc")
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- API lộ trình (/plan)
class PlanReq(BaseModel):
    points: list[int] | None = None     # tự chọn điểm ngữ pháp mới; trống = 3 điểm kế tiếp trong giáo trình


class PlanRunReq(BaseModel):
    pos: int = 0


@app.get("/api/plans")
def plans():
    done = plan.taught()
    return {"plans": plan.listing(), "active": plan.active(), "job": dict(PLAN_JOB),
            "next": plan.next_points(),
            "syllabus": [dict(p, taught=p["no"] in done) for p in plan.POINTS],
            "has_key": bool(ai_key(ai_conf()["provider"]))}


@app.get("/api/plans/{pid}")
def plan_detail(pid: int):
    p = plan.load(pid)
    if not p:
        raise HTTPException(404, "Không có buổi này")
    return p


@app.post("/api/plans")
def plan_create(body: PlanReq):
    if PLAN_JOB["running"]:
        raise HTTPException(400, "Đang soạn một buổi khác, chờ chút")
    if not ai_key(ai_conf()["provider"]):
        raise HTTPException(400, "Chưa có API key AI (vào /admin để nhập)")
    new = [n for n in (body.points or []) if n in plan.BY_NO][:6] or None
    start_plan_job(new)
    return dict(PLAN_JOB)


@app.post("/api/plans/{pid}/run")
def plan_run(pid: int, body: PlanRunReq):
    if not plan.run(pid, body.pos):
        raise HTTPException(404, "Không có buổi này hoặc buổi trống")
    GAME._push("system", f"📅 Bắt đầu chạy buổi học #{pid}")
    return {"ok": True, "active": plan.active()}


@app.post("/api/plans/stop")
def plan_stop():
    plan.stop()
    return {"ok": True}


@app.delete("/api/plans/{pid}")
def plan_delete(pid: int):
    plan.delete(pid)
    return {"ok": True}


@app.delete("/api/plans/{pid}/q/{i}")
def plan_delete_q(pid: int, i: int):
    p = plan.load(pid)
    if not p or not (0 <= i < len(p.get("questions", []))):
        raise HTTPException(404, "Không có câu này")
    p["questions"].pop(i)
    plan.update(pid, {k: v for k, v in p.items() if k not in ("id", "created_at")})
    a = plan.active()
    if a and a["id"] == pid and a["pos"] > i:
        db.set_conf("plan_active", {"id": pid, "pos": a["pos"] - 1})
    return {"ok": True, "total": len(p["questions"])}


def warm_voices():
    """Tạo sẵn giọng cho các câu cố định, để lúc live bot nói là phát ngay."""
    if not GAME.cfg["bot_voice"] or not ai_key("openai"):
        return
    for t in bot.static_lines():
        if synth(bot.speech_text(t)) is None:
            return
        TTS["warm"] += 1


@app.get("/audio/bot/{seq}.mp3")
def bot_voice(seq: int):
    """Chỉ đọc câu do engine tạo (tra theo seq), không nhận chữ tuỳ ý từ ngoài."""
    if not GAME.cfg["bot_voice"]:
        raise HTTPException(404, "Giọng bot đang tắt")
    with GAME.lock:
        line = next((l for l in GAME.bot_lines if l["seq"] == seq), None)
    text = bot.speech_text(line["text"]) if line else ""
    if not text:
        raise HTTPException(404, "Không có câu này")
    p = synth(text)
    if not p:
        raise HTTPException(404, "Giọng bot chưa sẵn sàng")
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/audio/{wid}/{part}.mp3")
def audio(wid: int, part: str):
    try:
        p = source().audio_path(wid, part)
    except SourceError as e:
        raise HTTPException(404, str(e))
    return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- pages
def _page(name):
    return FileResponse(os.path.join(STATIC, name), headers={"Cache-Control": "no-cache"})


@app.get("/")
def root():
    return RedirectResponse("/admin")


@app.get("/admin")
def admin_page():
    return _page("admin.html")


@app.get("/overlay")
def overlay_page():
    return _page("overlay.html")


@app.get("/plan")
def plan_page():
    return _page("plan.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
