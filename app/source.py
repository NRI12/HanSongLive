"""Lấy từ vựng + âm thanh từ một máy chủ HanSong qua HTTP API của nó.

HanSongLive không đọc DB hay code của HanSong; chỉ cần URL + mật khẩu đăng nhập.
Âm thanh được cache ra đĩa để khi live không phụ thuộc mạng tới HanSong.
"""
import os
import threading
import time

import httpx

from . import db

AUDIO_PARTS = ("ko_word", "vi_word", "mix", "ko_ex", "vi_ex")
SOURCES = ("all", "today", "due", "hard", "new", "mastered", "random")


class SourceError(Exception):
    pass


class HanSongSource:
    def __init__(self, base_url: str, password: str = "", refresh_s: int = 300):
        self.base_url = base_url.rstrip("/")
        self.password = password
        self.refresh_s = refresh_s
        self._client: httpx.Client | None = None
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[float, list[dict]]] = {}
        self._file_locks: dict[str, threading.Lock] = {}
        self._file_locks_guard = threading.Lock()
        self.last_error = ""

    # ------------------------------------------------------------ http
    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, timeout=20, follow_redirects=True)
        return self._client

    def _login(self):
        r = self._http().post("/api/login", json={"password": self.password})
        if r.status_code != 200:
            raise SourceError(f"Đăng nhập HanSong thất bại: {r.json().get('detail', r.status_code)}")

    def _get(self, path, **params) -> httpx.Response:
        try:
            r = self._http().get(path, params=params)
            if r.status_code == 401:
                self._login()
                r = self._http().get(path, params=params)
        except httpx.HTTPError as e:
            raise SourceError(f"Không gọi được HanSong ({self.base_url}): {e}") from e
        if r.status_code != 200:
            raise SourceError(f"HanSong trả lỗi {r.status_code} cho {path}")
        return r

    # ------------------------------------------------------------ words
    def words(self, source: str = "all", force: bool = False) -> list[dict]:
        """Danh sách từ đã có âm thanh. Cache refresh_s giây; nếu HanSong lỗi thì dùng bản cache cũ."""
        source = source if source in SOURCES else "all"
        with self._lock:
            hit = self._cache.get(source)
            if hit and not force and time.time() - hit[0] < self.refresh_s:
                return hit[1]
            try:
                ws = [w for w in self._get("/api/words", source=source).json() if w.get("audio_ready")]
                self._cache[source] = (time.time(), ws)
                self.last_error = ""
                return ws
            except (SourceError, ValueError) as e:
                self.last_error = str(e)
                if hit:
                    return hit[1]
                raise SourceError(str(e)) from e

    def check(self) -> dict:
        try:
            n = len(self.words("all", force=True))
            return {"ok": True, "words": n, "detail": f"Đã kết nối HanSong: {n} từ có âm thanh"}
        except SourceError as e:
            return {"ok": False, "words": 0, "detail": str(e)}

    # ------------------------------------------------------------ audio
    def audio_path(self, wid: int, part: str) -> str:
        """Trả về file mp3 trên đĩa, tải từ HanSong nếu chưa có."""
        if part not in AUDIO_PARTS:
            raise SourceError("part không hợp lệ")
        d = os.path.join(db.DATA_DIR, "audio", str(int(wid)))
        p = os.path.join(d, f"{part}.mp3")
        if os.path.exists(p):
            return p
        # Tải sẵn ở nền và overlay có thể cùng xin một file. Mỗi file một khoá để chỉ một luồng ghi
        # (trên Windows, hai luồng cùng os.replace vào một file sẽ bị PermissionError).
        with self._file_locks_guard:
            lock = self._file_locks.setdefault(p, threading.Lock())
        with lock:
            if os.path.exists(p):
                return p
            r = self._get(f"/api/audio/{int(wid)}/{part}.mp3")
            os.makedirs(d, exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "wb") as f:
                f.write(r.content)
            os.replace(tmp, p)
        return p

    def prefetch(self, wid: int):
        for part in AUDIO_PARTS:
            try:
                self.audio_path(wid, part)
            except SourceError:
                pass
