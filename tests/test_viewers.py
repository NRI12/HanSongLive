from app import db, viewers


def _ev(kind, uid="u1", name="Lan", **kw):
    return {"type": kind, "user": {"id": uid, "name": name}, **kw}


def test_record_flush_and_counts():
    db.conn()
    db.q("DELETE FROM live_viewers")
    for e in (_ev("join"), _ev("comment", text="a"), _ev("like", count=15), _ev("like", count=5),
              _ev("share"), _ev("follow"), _ev("gift", count=3), _ev("comment", uid="mock:Lan"), _ev("audience")):
        viewers.record(e)
    assert viewers.flush() == 1                   # người mock + audience không được lưu
    viewers.record(_ev("comment", name="Lan mới"))
    viewers.flush()
    r = db.q1("SELECT * FROM live_viewers WHERE user_id='u1'")
    assert (r["name"], r["joins"], r["comments"], r["likes"], r["shares"], r["follows"], r["gifts"], r["sessions"]) == \
        ("Lan mới", 1, 2, 20, 1, 1, 3, 1)
    assert viewers.summary()["total"] == 1
    assert viewers.flush() == 0


def test_new_session_after_gap():
    db.conn()
    db.q("DELETE FROM live_viewers")
    viewers.record(_ev("join", uid="u2"))
    viewers.flush()
    with db.tx() as c:
        c.execute("UPDATE live_viewers SET last_seen='2020-01-01 00:00:00' WHERE user_id='u2'")
    viewers.record(_ev("comment", uid="u2"))
    viewers.flush()
    assert db.q1("SELECT sessions FROM live_viewers WHERE user_id='u2'")["sessions"] == 2


def test_csv_has_bom_and_header():
    db.conn()
    viewers.record(_ev("join", uid="u3", name="Tú"))
    viewers.flush()
    out = viewers.to_csv()
    assert out.startswith("﻿user_id,ten,") and "Tú" in out
