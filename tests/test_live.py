"""Engine + API, không cần mạng: HanSong và TikTok đều được giả lập."""
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, live, main, source, tiktok

WORDS = [
    {"id": i, "korean": ko, "romanization": "r", "vietnamese": vi, "hanviet": "", "pos": "danh từ",
     "example_ko": ko + " 좋아요", "example_vi": vi + " thì tốt", "level": 1, "audio_ready": 1}
    for i, (ko, vi) in enumerate([("학교", "trường học"), ("사과", "quả táo"), ("물", "nước"),
                                  ("책", "sách"), ("친구", "bạn bè")], start=1)
]


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def make_game(mode="ko2vi"):
    clock = Clock()
    pick = lambda recent, cfg: live.build_question(WORDS[0], WORDS, cfg["mode"])
    g = live.LiveGame(pick, clock=clock, persist=False)
    g.configure({"mode": mode, "question_s": 20, "reveal_s": 5, "board_every": 2, "like_goal": 300})
    return g, clock


def C(uid, text): return {"type": "comment", "user": {"id": uid, "name": uid}, "text": text}


def test_parse_answer():
    opts = ["nước", "trường học", "sách", "quả táo"]
    assert live.parse_answer("b", opts, "vi") == 1
    assert live.parse_answer(" C ", opts, "vi") == 2
    assert live.parse_answer("4", opts, "vi") == 3
    assert live.parse_answer("đáp án a", opts, "vi") == 0
    assert live.parse_answer("Trường học!", opts, "vi") == 1
    assert live.parse_answer("hay quá", opts, "vi") is None
    assert live.parse_answer("학 교", ["물", "학교"], "ko") == 1
    assert live.parse_answer("D", ["a", "b", "c"], "vi") is None


def test_round_scoring_and_phases():
    g, clock = make_game()
    g.start()
    s = g.state()
    assert s["phase"] == "question" and s["question"]["prompt"] == "학교" and s["question"]["answer"] is None
    right = "ABCD"[g.q["answer"]]
    wrong = "ABCD"[(g.q["answer"] + 1) % 4]
    g.handle(C("an", right))            # đúng, nhanh nhất
    clock.t += 10
    g.handle(C("binh", right))          # đúng, chậm hơn
    g.handle(C("chi", wrong))
    g.handle(C("chi", right))           # đổi đáp án không được tính
    g.handle(C("dung", "hello"))        # không phải câu trả lời
    p = g.players
    assert p["an"]["score"] == 10 + 10 + 5
    assert p["binh"]["score"] == 10 + 5
    assert p["chi"]["score"] == 0 and p["chi"]["answered"] == 1
    assert "dung" not in p
    clock.t += 10.1
    g.tick()
    s = g.state()
    assert s["phase"] == "reveal" and s["question"]["answer"] == g.q["answer"]
    assert s["question"]["result"]["correct"] == 2 and s["question"]["result"]["total"] == 3
    assert s["question"]["result"]["fastest"][0]["name"] == "an"
    g.handle(C("an", right))            # trả lời khi đang hiện đáp án: bỏ qua
    assert g.players["an"]["answered"] == 1
    clock.t += 5.1; g.tick()
    assert g.phase == "question" and g.qid == 2
    clock.t += 20.1; g.tick(); clock.t += 5.1; g.tick()
    assert g.phase == "board"           # board_every=2
    clock.t += 10.1; g.tick()
    assert g.phase == "question"


def test_streak_bonus_and_score_command():
    g, clock = make_game()
    for _ in range(3):
        g.start() if g.phase == "idle" else g.skip()
        if g.phase == "reveal":
            g.skip()
        g.handle(C("an", "ABCD"[g.q["answer"]]))
        g.skip()
    assert g.players["an"]["streak"] == 3
    assert g.players["an"]["score"] == 25 * 3 + 3      # chuỗi 3 -> +3
    g.handle(C("an", "điểm"))
    assert "78 điểm" in g.feed[-1]["text"] and "hạng 1" in g.feed[-1]["text"]


def test_gift_removes_wrong_option_and_likes_double():
    g, clock = make_game()
    g.start()
    for _ in range(5):
        g.handle({"type": "gift", "user": {"id": "u", "name": "Lan"}, "count": 1, "gift_name": "Rose"})
    hints = g.state()["question"]["hints"]
    assert len(hints) == 2 and g.q["answer"] not in hints   # luôn chừa 1 đáp án sai
    assert g.players["u"]["gifts"] == 5 and g.players["u"]["score"] == 0  # quà không quy ra điểm
    g.handle({"type": "like", "user": {"id": "v", "name": "V"}, "count": 299})
    assert not g.double_next
    g.handle({"type": "like", "user": {"id": "v", "name": "V"}, "count": 1})
    assert g.double_next
    g.skip(); g.skip()
    assert g.double and not g.double_next
    g.handle(C("an", "ABCD"[g.q["answer"]]))
    assert g.players["an"]["score"] == 50


def test_vi2ko_mode():
    g, _ = make_game("vi2ko")
    g.start()
    q = g.state()["question"]
    assert q["prompt"] == "trường học" and q["prompt_lang"] == "vi" and "학교" in q["options"]
    g.handle(C("an", "학교"))
    assert g.answers["an"]["correct"]


def test_tiktok_normalize():
    u = SimpleNamespace(id=123, nickname="Hoa", display_id="hoa99")
    assert tiktok.normalize("comment", SimpleNamespace(user=u, content="B")) == \
        {"type": "comment", "user": {"id": "123", "name": "Hoa"}, "text": "B"}
    gift = SimpleNamespace(name="Rose", diamond_count=1)
    assert tiktok.normalize("gift", SimpleNamespace(user=u, gift=gift, streaking=True, repeat_count=3)) is None
    g = tiktok.normalize("gift", SimpleNamespace(user=u, gift=gift, streaking=False, repeat_count=3))
    assert g["count"] == 3 and g["gift_name"] == "Rose"
    assert tiktok.normalize("audience", SimpleNamespace(total=42)) == {"type": "audience", "count": 42}
    assert tiktok.normalize("comment", SimpleNamespace(user=SimpleNamespace(id=0), content="x")) is None


def fake_hansong(request: httpx.Request):
    if request.url.path == "/api/login":
        return httpx.Response(200, json={"ok": True}, headers={"set-cookie": "hs_token=ok; Path=/"})
    if request.headers.get("cookie") != "hs_token=ok":
        return httpx.Response(401, json={"detail": "unauthorized"})
    if request.url.path == "/api/words":
        return httpx.Response(200, json=WORDS)
    if request.url.path.startswith("/api/audio/"):
        return httpx.Response(200, content=b"ID3fake-mp3")
    return httpx.Response(404)


@pytest.fixture
def client(monkeypatch):
    orig = source.HanSongSource._http
    def _http(self):
        if self._client is None:
            self._client = httpx.Client(base_url=self.base_url, transport=httpx.MockTransport(fake_hansong))
        return orig(self)
    monkeypatch.setattr(source.HanSongSource, "_http", _http)
    with TestClient(main.app) as c:
        yield c


def test_api_flow(client):
    c = client
    c.put("/api/config", json={"hansong_url": "http://hansong.test", "hansong_password": "pw"}).raise_for_status()
    assert c.post("/api/hansong/check").json()["words"] == 5
    assert c.put("/api/config", json={"hansong_url": "ftp://x"}).status_code == 400
    assert c.put("/api/config", json={"tiktok_username": "bad name!"}).status_code == 400
    c.put("/api/config", json={"tiktok_username": "@han.song", "tiktok_sign_key": "secret-key",
                               "game": {"question_s": 3, "mode": "ko2vi", "source": "bogus"}})
    a = c.get("/api/admin").json()
    assert a["tiktok"] == {"username": "han.song", "has_sign_key": True}
    assert "secret-key" not in str(a) and "pw" not in str(a["hansong"])
    assert a["game"]["config"]["question_s"] == 8   # kẹp về tối thiểu 8 giây
    assert a["game"]["config"]["source"] == "all"

    assert c.post("/api/mock", json={"text": "A"}).status_code == 400     # chưa bật chế độ thử
    c.post("/api/connect", json={"mode": "mock"})
    st = c.post("/api/game", json={"action": "start"}).json()
    q = st["question"]
    assert st["phase"] == "question" and len(q["options"]) == 4
    ans = main.GAME.q["answer"]
    c.post("/api/mock", json={"name": "Lan", "text": "ABCD"[ans]}).raise_for_status()
    c.post("/api/game", json={"action": "skip"})
    s = c.get("/api/overlay/state").json()
    assert s["phase"] == "reveal" and s["top"][0]["name"] == "Lan" and s["question"]["word"]["example_ko"]
    r = c.get(f"/audio/{q['word_id']}/mix.mp3")
    assert r.status_code == 200 and r.content == b"ID3fake-mp3"
    assert c.get("/audio/1/../../etc.mp3").status_code == 404
    row = db.q1("SELECT * FROM live_players WHERE user_id='mock:Lan'")
    assert row["score"] > 0 and row["correct"] == 1
    c.post("/api/game", json={"action": "reset"})
    assert c.get("/api/overlay/state").json()["players"] == 0
    assert db.q1("SELECT score FROM live_players WHERE user_id='mock:Lan'")["score"] == row["score"]  # all-time giữ
    assert c.get("/admin").status_code == 200 and c.get("/overlay").status_code == 200


def test_auth(client, monkeypatch):
    monkeypatch.setattr(main, "LIVE_PASSWORD", "pw")
    c = client
    c.cookies.clear()
    assert c.get("/api/admin").status_code == 401
    assert c.get("/api/overlay/state").status_code == 401
    assert c.get(f"/api/overlay/state?k={main.overlay_token()}").status_code == 200
    assert c.get("/api/overlay/state?k=wrong").status_code == 401
    assert c.post("/api/login", json={"password": "nope"}).status_code == 401
    c.post("/api/login", json={"password": "pw"}).raise_for_status()
    assert c.get("/api/admin").status_code == 200


def G(uid, diamonds, count=1):
    return {"type": "gift", "user": {"id": uid, "name": uid}, "count": count, "gift_name": "Quà", "diamonds": diamonds}


def answer(g, uid, ok=True):
    g.handle(C(uid, "ABCD"[g.q["answer"] if ok else (g.q["answer"] + 1) % 4]))


def test_gift_tiers_never_give_points():
    g, clock = make_game()
    g.configure({"gift_big": 30, "gift_huge": 100, "gift_goal": 0})
    g.start()
    end = g.phase_end
    g.handle(G("a", 1))                                  # quà nhỏ: chỉ loại 1 đáp án
    assert g.phase_end == end and len(g.hints) == 1 and g.feed[-1]["tier"] == 1
    g.handle(G("b", 5, count=6))                         # 30 kim cương: +10 giây, phát lại âm
    assert g.phase_end == end + 10 and g.state()["question"]["replay"] == 1 and g.feed[-1]["alert"]
    for _ in range(4):
        g.handle(G("b", 30))
    assert g.phase_end == end + 30                       # tối đa +30 giây mỗi câu
    g.handle(G("c", 100))                                # nhà tài trợ câu kế tiếp
    assert all(p["score"] == 0 for p in g.players.values())
    assert g.players["b"]["diamonds"] == 150
    g.skip(); g.skip()
    assert g.state()["question"]["sponsor"] == "c"
    assert g.state()["supporters"][0]["name"] == "b"


def test_room_goals_boss_and_double():
    g, clock = make_game()
    g.configure({"gift_goal": 50, "share_goal": 2, "boss_every": 0, "listen_every": 0})
    g.start()
    g.handle(G("a", 25, count=2))
    assert list(g.queued) == ["boss"] and g.state()["goals"]["diamonds"]["value"] == 0
    for u in ("x", "y"):
        g.handle({"type": "share", "user": {"id": u, "name": u}})
    assert g.double_next
    g.skip(); g.skip()
    s = g.state()["question"]
    assert s["special"] == "boss" and s["mult"] == 6 and g.q_duration == 12   # 20 * 0.6
    answer(g, "an")
    assert g.players["an"]["score"] == 25 * 6


def test_listen_round_hides_prompt():
    g, clock = make_game("vi2ko")
    g.configure({"listen_every": 1, "boss_every": 0})
    g.start()
    q = g.state()["question"]
    assert q["listen"] and q["prompt"] == "🎧" and q["mode"] == "ko2vi" and q["word"]["romanization"] == ""
    g.skip()
    assert g.state()["question"]["prompt"] == "학교"


def test_live_counts_streak_alerts_and_teams():
    g, clock = make_game()
    g.configure({"boss_every": 0, "listen_every": 0})
    g.start()
    g.handle(C("an", "đội đỏ"))
    g.handle(C("an", "doi xanh"))                        # không được đổi đội
    g.handle(C("binh", "Team Xanh"))
    assert g.players["an"]["team"] == "red" and g.players["binh"]["team"] == "blue"
    answer(g, "an"); answer(g, "binh", ok=False)
    q = g.state()["question"]
    assert sum(q["counts"]) == 2 and q["answer"] is None
    g.configure({"live_counts": 0})
    assert g.state()["question"]["counts"] is None
    assert g.teams["red"]["score"] == 25 and g.teams["blue"]["score"] == 0
    for _ in range(4):
        g.skip(); g.skip(); answer(g, "an")
    assert g.players["an"]["streak"] == 5 and any(f["kind"] == "streak" and f.get("alert") for f in g.feed)
    g.skip(); g.skip(); answer(g, "an", ok=False)
    assert "mất chuỗi 5" in g.feed[-1]["text"]


def test_vote_sets_mode_until_next_board():
    g, clock = make_game("ko2vi")
    g.configure({"board_every": 1, "boss_every": 0, "listen_every": 0})
    g.start()
    answer(g, "an")
    clock.t += 20.1; g.tick(); clock.t += 5.1; g.tick()
    assert g.phase == "board" and g.state()["vote"]["counts"] == [0, 0, 0]
    g.handle(C("an", "2")); g.handle(C("an", "1")); g.handle(C("binh", "số 2")); g.handle(C("chi", "1"))
    assert g.vote["counts"] == [1, 2, 0]
    clock.t += 10.1; g.tick()
    assert g.vote_mode == "vi2ko" and g.q["mode"] == "vi2ko" and g.state()["vote"] is None


def test_join_throttle():
    g, clock = make_game()
    for i in range(5):
        g.handle({"type": "join", "user": {"id": f"u{i}", "name": f"u{i}"}})
    assert sum(f["kind"] == "join" for f in g.feed) == 1
    clock.t += 4
    g.handle({"type": "join", "user": {"id": "z", "name": "z"}})
    assert sum(f["kind"] == "join" for f in g.feed) == 2


def test_api_queue_stats_weekly(client):
    c = client
    c.put("/api/config", json={"hansong_url": "http://hansong.test", "hansong_password": "pw",
                               "game": {"boss_every": 0, "listen_every": 0}})
    c.post("/api/connect", json={"mode": "mock"})
    c.post("/api/game", json={"action": "pause"})
    c.post("/api/game", json={"action": "reset"})
    c.post("/api/game", json={"action": "start"})
    assert main.GAME.phase == "question"
    assert c.post("/api/game", json={"action": "boss"}).json()["next_special"] == "boss"
    assert c.post("/api/game", json={"action": "nope"}).status_code == 400
    c.post("/api/mock", json={"type": "gift", "name": "Fan", "count": 2, "diamonds": 50}).raise_for_status()
    c.post("/api/mock", json={"name": "Vy", "text": "ABCD"[main.GAME.q["answer"]]})
    c.post("/api/game", json={"action": "skip"})
    st = c.get("/api/stats").json()
    assert st["recent"][0]["answered"] == 1 and st["by_kind"]
    assert db.q1("SELECT diamonds FROM live_players WHERE user_id='mock:Fan'")["diamonds"] == 100
    assert live.weekly_fans(3)[0]["name"] == "Fan"
    assert any(r["name"] == "Vy" for r in live.weekly_top(5))
    c.post("/api/game", json={"action": "skip"})
    assert main.GAME.special == "boss"
