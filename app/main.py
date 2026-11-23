"""HanSongLive: trò chơi đoán từ tiếng Hàn trên TikTok LIVE, lấy dữ liệu từ HanSong.

Trang:
  /admin              bảng điều khiển (cần LIVE_PASSWORD nếu có đặt)
  /overlay?k=<token>  màn hình đưa lên TikTok LIVE Studio / OBS (Browser source 1080x1920)
"""
import asyncio
import hashlib
import hmac
import os
import random
import re
import shutil
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, live
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
    try:
        words = source().words(cfg["source"])
    except SourceError:
        return None
    fresh = [w for w in words if w["id"] not in recent] or words
    if len(words) < 2:
        return None
    word = random.choice(fresh)
    pool = random.sample(words, min(len(words), 40))
    q = live.build_question(word, pool, cfg["mode"])
    if q:   # tải sẵn âm thanh câu này ở nền
        threading.Thread(target=source().prefetch, args=(word["id"],), daemon=True).start()
    return q


GAME = live.LiveGame(picker)
CONNECTOR: TikTokConnector | None = None
STATUS = {"mode": "off", "state": "idle", "detail": "Chưa kết nối", "attempt": 0}
LOOP: asyncio.AbstractEventLoop | None = None


def set_status(s: dict):
    STATUS.clear()
    STATUS.update(s)


async def ticker():
    while True:
        try:
            await asyncio.to_thread(GAME.tick)
        except Exception as e:  # không để vòng lặp chết
            GAME.message = f"Lỗi: {e}"
        await asyncio.sleep(0.25)


@asynccontextmanager
async def lifespan(_app):
    global LOOP
    LOOP = asyncio.get_running_loop()
    db.conn()
    GAME.configure(db.get_conf("game", {}))
    t = asyncio.create_task(ticker())
    yield
    t.cancel()
    if CONNECTOR:
        await CONNECTOR.stop()


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
        if not (admin_ok or overlay_ok):
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
def admin_state():
    h, t = hansong_conf(), tiktok_conf()
    return {
        "hansong": {"url": h["url"], "has_password": bool(h["password"]),
                    "error": SOURCE.last_error if SOURCE else ""},
        "tiktok": {"username": t["username"], "has_sign_key": bool(t["sign_key"])},
        "status": dict(STATUS),
        "overlay_path": f"/overlay?k={overlay_token()}",
        "game": GAME.state(),
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
    return admin_state()


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
    if CONNECTOR:
        await CONNECTOR.stop()
        CONNECTOR = None
    if body.mode == "tiktok":
        t = tiktok_conf()
        if not t["username"]:
            raise HTTPException(400, "Nhập tên tài khoản TikTok trước khi kết nối")
        CONNECTOR = TikTokConnector(t["username"], t["sign_key"], GAME.handle, set_status)
        CONNECTOR.start()
    elif body.mode == "mock":
        set_status({"mode": "mock", "state": "connected", "detail": "Chế độ thử: gửi comment giả từ bảng điều khiển",
                    "attempt": 0})
    else:
        set_status({"mode": "off", "state": "idle", "detail": "Đã ngắt kết nối", "attempt": 0})
    return dict(STATUS)


class GameReq(BaseModel):
    action: str   # start | pause | skip | reset | boss | listen | double


@app.post("/api/game")
def game(body: GameReq):
    act = {"start": GAME.start, "pause": GAME.pause, "skip": GAME.skip, "reset": GAME.reset_scores,
           "boss": lambda: GAME.queue("boss"), "listen": lambda: GAME.queue("listen"),
           "double": lambda: GAME.queue("double")}.get(body.action)
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


# ---------------------------------------------------------------- overlay
@app.get("/api/overlay/state")
def overlay_state():
    boards = None
    if GAME.phase == "board":
        boards = {"all_time": live.all_time_top(1), "weekly": live.weekly_top(5), "weekly_fans": live.weekly_fans(3)}
    s = GAME.state(boards)
    s["connected"] = STATUS.get("state") == "connected"
    return s


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


app.mount("/static", StaticFiles(directory=STATIC), name="static")
