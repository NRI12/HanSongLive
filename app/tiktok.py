"""Kết nối TikTok LIVE (thư viện TikTokLive). Payload của SDK chỉ dừng ở file này;
game chỉ nhận dict đã chuẩn hoá (xem live.LiveGame.handle)."""
import asyncio
import logging
import re

log = logging.getLogger("hansong.tiktok")


def _user(u) -> dict | None:
    if u is None:
        return None
    uid = str(getattr(u, "id", "") or getattr(u, "display_id", "") or "")
    if not uid or uid == "0":
        return None
    name = getattr(u, "nickname", "") or getattr(u, "display_id", "") or uid
    out = {"id": uid[:100], "name": str(name)[:60]}
    av = _avatar(u)
    if av:
        out["avatar"] = av
    return out


_AVATAR_RE = re.compile(r"^https://[\w.-]+\.(?:tiktokcdn(?:-[\w]+)?\.com|ibyteimg\.com|byteimg\.com|muscdn\.com)/[^\s\"'<>]{1,600}$")


def _avatar(u) -> str | None:
    """Ảnh đại diện nhỏ của người xem. Chỉ nhận https từ CDN của TikTok, để overlay không tải link lạ."""
    img = getattr(u, "avatar_thumb", None)
    for url in (getattr(img, "url_list", None) or [])[:3]:
        if isinstance(url, str) and _AVATAR_RE.match(url):
            return url
    return None


def normalize(kind: str, ev) -> dict | None:
    """SDK event -> dict chuẩn. Trả None nếu bỏ qua."""
    if kind == "audience":
        n = getattr(ev, "total", None) or getattr(ev, "total_user", None) or 0
        try:
            n = int(n)
        except (TypeError, ValueError):
            return None
        return {"type": "audience", "count": n} if 0 <= n <= 10_000_000 else None
    user = _user(getattr(ev, "user", None))
    if not user:
        return None
    if kind == "comment":
        text = getattr(ev, "content", None) or getattr(ev, "comment", "") or ""
        return {"type": "comment", "user": user, "text": str(text)[:500]}
    if kind == "gift":
        gift = getattr(ev, "gift", None)
        # Quà dạng combo: chỉ tính khi combo kết thúc để không cộng trùng.
        if getattr(ev, "streaking", False):
            return None
        return {"type": "gift", "user": user, "count": max(1, min(100000, int(getattr(ev, "repeat_count", 1) or 1))),
                "gift_name": str(getattr(gift, "name", "") or "quà")[:100],
                "diamonds": int(getattr(gift, "diamond_count", 0) or 0)}
    if kind == "like":
        return {"type": "like", "user": user, "count": max(1, min(100000, int(getattr(ev, "count", 1) or 1)))}
    if kind in ("join", "follow", "share"):
        return {"type": kind, "user": user}
    return None


class TikTokConnector:
    MAX_ATTEMPTS = 6

    def __init__(self, username: str, sign_key: str | None, emit, status):
        self.username = username.lstrip("@")
        self.sign_key = sign_key or None
        self.emit = emit
        self.status = status
        self.client = None
        self.task: asyncio.Task | None = None
        self.stopped = True
        self.attempt = 0

    def _report(self, state, detail):
        self.status({"mode": "tiktok", "state": state, "detail": detail, "attempt": self.attempt})

    def start(self):
        self.stopped = False
        self.task = asyncio.get_running_loop().create_task(self._run())

    async def _run(self):
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.client.web.web_settings import WebDefaults
            from TikTokLive.events import (CommentEvent, ConnectEvent, FollowEvent, GiftEvent,
                                           JoinEvent, LikeEvent, LiveEndEvent, RoomUserSeqEvent, ShareEvent)
        except ImportError:
            self._report("error", "Chưa cài thư viện TikTokLive (pip install TikTokLive).")
            return
        if self.sign_key:
            WebDefaults.tiktok_sign_api_key = self.sign_key
        kinds = {CommentEvent: "comment", GiftEvent: "gift", LikeEvent: "like", JoinEvent: "join",
                 FollowEvent: "follow", ShareEvent: "share", RoomUserSeqEvent: "audience"}
        ended = False
        while not self.stopped and not ended:
            if self.attempt >= self.MAX_ATTEMPTS:
                self._report("error", "Kết nối thất bại sau 6 lần thử. Kiểm tra tài khoản đang LIVE và khoá ký, "
                                      "rồi bấm kết nối lại.")
                return
            self.attempt += 1
            self._report("connecting", f"Đang kết nối @{self.username}…")
            client = self.client = TikTokLiveClient(unique_id="@" + self.username)

            for cls, kind in kinds.items():
                async def handler(ev, kind=kind):
                    if self.stopped:
                        return
                    try:
                        out = normalize(kind, ev)
                    except Exception:  # payload lạ từ SDK: bỏ qua, không làm sập kết nối
                        log.exception("normalize %s", kind)
                        return
                    if out:
                        self.emit(out)
                client.add_listener(cls, handler)

            async def on_connect(_ev):
                self.attempt = 0
                self._report("connected", f"Đang nhận sự kiện @{self.username}")

            async def on_end(_ev):
                nonlocal ended
                ended = True
                self._report("disconnected", "Phiên LIVE đã kết thúc.")

            client.add_listener(ConnectEvent, on_connect)
            client.add_listener(LiveEndEvent, on_end)
            failed = False
            try:
                hb = await client.start(fetch_live_check=True)
                await hb
            except asyncio.CancelledError:
                raise
            except Exception as e:
                failed = True
                name = type(e).__name__
                if "Offline" in name:
                    self._report("error", f"@{self.username} chưa phát LIVE. Đang thử lại…")
                else:
                    self._report("error", f"Chưa kết nối được ({name}). Đang thử lại…")
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            if self.stopped or ended:
                break
            if not failed:
                self._report("disconnected", "Mất kết nối TikTok. Đang thử lại…")
            await asyncio.sleep(min(30, 2 ** self.attempt))

    async def stop(self):
        self.stopped = True
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
