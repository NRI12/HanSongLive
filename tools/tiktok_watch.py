"""Nghe sự kiện từ một phòng TikTok LIVE bất kỳ (chỉ đọc) và in ra dict đã chuẩn hoá.

Dùng để thử đường nhận comment/quà thật mà không cần tự phát live và không đụng tới game:
    .venv/Scripts/python.exe tools/tiktok_watch.py <tài_khoản_đang_live> [khoá_ký_euler]
Comment nào là đáp án A/B/C/D thì in thêm đáp án game sẽ đọc được. Ctrl+C để dừng.
Không có khoá ký trên dòng lệnh thì lấy khoá đã lưu trong admin (data/live.db) hoặc TIKTOK_SIGN_API_KEY.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import db  # noqa: E402
from app.live import parse_answer  # noqa: E402
from app.tiktok import TikTokConnector  # noqa: E402

OPTS = ["a", "b", "c", "d"]


def emit(ev: dict):
    if ev["type"] == "audience":
        print(f"[người xem] {ev['count']}")
        return
    user = ev["user"]["name"]
    if ev["type"] == "comment":
        ans = parse_answer(ev["text"], OPTS, "vi")
        tag = f"  -> đáp án {'ABCD'[ans]}" if ans is not None else ""
        print(f"[comment] {user}: {ev['text']}{tag}")
    elif ev["type"] == "like":
        print(f"[tim] {user} x{ev['count']}")
    else:
        rest = {k: v for k, v in ev.items() if k not in ("type", "user")}
        print(f"[{ev['type']}] {user} {json.dumps(rest, ensure_ascii=False) if rest else ''}")


def status(s: dict):
    print(f"== {s['state']}: {s['detail']} (lần {s['attempt']})")


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    key = sys.argv[2] if len(sys.argv) > 2 else (db.get_conf("tiktok.sign_key") or os.environ.get("TIKTOK_SIGN_API_KEY"))
    conn = TikTokConnector(sys.argv[1], key, emit, status)
    conn.start()
    try:
        await conn.task
    finally:
        await conn.stop()


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
