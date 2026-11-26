"""Sổ người xem: lưu mọi người từng vào phòng / tương tác (comment, tim, chia sẻ, follow, quà).

Sự kiện được cộng dồn trong bộ nhớ (`record`, gọi từ luồng sự kiện) rồi ghi xuống DB theo lô (`flush`,
gọi định kỳ từ ticker), vì tim có thể tới hàng trăm lần/phút. Người mock (`mock:`) không được lưu.
"""
import csv
import io
import threading
import time

from . import db

FIELDS = ("joins", "comments", "likes", "shares", "follows", "gifts")
_KIND = {"join": "joins", "comment": "comments", "like": "likes", "share": "shares", "follow": "follows", "gift": "gifts"}
SESSION_GAP_S = 3 * 3600   # vắng quá 3 giờ rồi quay lại thì tính là 1 buổi live mới

_lock = threading.Lock()
_pending: dict[str, dict] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def record(ev: dict):
    field = _KIND.get(ev.get("type"))
    user = ev.get("user") or {}
    uid = str(user.get("id") or "")
    if not field or not uid or uid.startswith("mock:"):
        return
    n = int(ev.get("count") or 1) if field in ("likes", "gifts") else 1
    with _lock:
        p = _pending.setdefault(uid, {"name": "", **{f: 0 for f in FIELDS}})
        p["name"] = str(user.get("name") or uid)[:60]
        p[field] += max(1, n)
        p["at"] = _now()


def flush() -> int:
    """Ghi các thay đổi đang chờ. Trả về số người được ghi."""
    with _lock:
        batch = dict(_pending)
        _pending.clear()
    if not batch:
        return 0
    gap = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - SESSION_GAP_S))
    with db.tx() as c:
        for uid, p in batch.items():
            c.execute(
                "INSERT INTO live_viewers(user_id,name,first_seen,last_seen,sessions,joins,comments,likes,shares,follows,gifts) "
                "VALUES(?,?,?,?,1,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
                "sessions=sessions + (last_seen < ?), last_seen=excluded.last_seen, "
                "joins=joins+excluded.joins, comments=comments+excluded.comments, likes=likes+excluded.likes, "
                "shares=shares+excluded.shares, follows=follows+excluded.follows, gifts=gifts+excluded.gifts",
                (uid, p["name"], p["at"], p["at"], *(p[f] for f in FIELDS), gap))
    return len(batch)


def summary() -> dict:
    today = time.strftime("%Y-%m-%d")
    r = db.q1("SELECT COUNT(*) total, SUM(last_seen >= ?) today, SUM(comments > 0) commenters, "
              "SUM(sessions > 1) regulars FROM live_viewers", (today,))
    return {k: int(v or 0) for k, v in r.items()}


def listing(limit: int = 100, order: str = "recent") -> list[dict]:
    by = {"recent": "last_seen DESC", "active": "comments + shares*5 + follows*5 + likes/20 DESC",
          "loyal": "sessions DESC, last_seen DESC"}.get(order, "last_seen DESC")
    return db.q(f"SELECT * FROM live_viewers ORDER BY {by} LIMIT ?", (max(1, min(5000, limit)),))


def to_csv() -> str:
    rows = db.q("SELECT user_id,name,first_seen,last_seen,sessions," + ",".join(FIELDS) +
                " FROM live_viewers ORDER BY last_seen DESC")
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["user_id", "ten", "lan_dau", "lan_cuoi", "so_buoi", "vao_phong", "comment", "tim", "chia_se", "follow", "qua"])
    for r in rows:
        w.writerow(list(r.values()))
    return "﻿" + out.getvalue()   # BOM để Excel đọc đúng tiếng Việt
