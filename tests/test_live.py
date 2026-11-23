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


# ---------------------------------------------------------------- AI + dạng bài mới
from app import ai

AIW = [
    {"id": 10, "korean": "기다리다", "vietnamese": "chờ, đợi", "hanviet": "", "pos": "động từ", "romanization": "gidarida",
     "example_ko": "여기에서 기다리세요.", "example_vi": "Hãy đợi ở đây.", "level": 1},
    {"id": 11, "korean": "학교", "vietnamese": "trường học", "hanviet": "học hiệu", "pos": "danh từ", "romanization": "hakgyo",
     "example_ko": "학교에 가요.", "example_vi": "Tôi đi học.", "level": 1},
]


def fake_chat(calls):
    def chat(provider, model, key, system, user):
        calls.append((provider, model, key, "Kiểm tra" in user))
        return {"items": [
            {"id": 10, "cloze": {"answer": "기다리세요", "distractors": ["먹으세요", "자세요", "가세요", "기다리세요"]},
             "trans_wrong": ["Hãy ngồi ở đây.", "Đừng đợi ở đây.", "Tôi đã đợi ở đó.", "Hãy đợi ở đây."]},
            {"id": 11, "cloze": {"answer": "학원", "distractors": ["a", "b", "c"]},          # answer không nằm trong câu
             "trans_wrong": ["Tôi về nhà.", "학교"]},                                       # thiếu, có chữ Hàn
            {"id": 99, "cloze": {"answer": "x"}},                                          # id lạ
        ]}
    return chat


def test_ai_generate_items_validates_output():
    calls = []
    cfg = dict(ai.DEFAULT_AI, provider="openai", verify=True)
    rows = ai.generate_items(AIW, cfg, "sk-test", chat=fake_chat(calls))
    assert [(p, m, k) for p, m, k, _ in calls] == [("openai", "gpt-5.5", "sk-test")] * 2
    assert calls[1][3]                                        # lượt 2 là kiểm duyệt
    got = {(w, k): d for w, k, d in rows}
    assert set(got) == {(10, "cloze"), (10, "trans")}         # từ 11 bị loại vì AI làm sai
    assert got[(10, "cloze")] == {"answer": "기다리세요", "distractors": ["먹으세요", "자세요", "가세요"]}
    assert "Hãy đợi ở đây." not in got[(10, "trans")]["wrong"]  # trùng đáp án đúng bị bỏ


def test_new_question_kinds():
    cz = live.build_cloze(AIW[0], {"answer": "기다리세요", "distractors": ["먹으세요", "자세요", "가세요"]})
    assert cz["prompt"] == "여기에서 ＿＿＿." and cz["options"][cz["answer"]] == "기다리세요"
    assert cz["hint"] == "Hãy đợi ở đây." and cz["audio_reveal"] == "ko_ex" and cz["audio_q"] is None
    tr = live.build_trans(AIW[0], {"wrong": ["a", "b", "c"]})
    assert tr["prompt"] == "여기에서 기다리세요." and tr["options"][tr["answer"]] == "Hãy đợi ở đây." and tr["audio_q"] == "ko_ex"
    pool = [dict(w, id=i, hanviet=h) for i, (w, h) in enumerate(zip(WORDS, ["học hiệu", "", "thủy", "thư", "thân cố"]), 1)]
    hv = live.build_hanviet(pool[0], pool)
    assert hv["options"][hv["answer"]] == "học hiệu" and set(hv["options"]) == {"học hiệu", "thủy", "thư", "thân cố"}
    assert live.build_hanviet(pool[1], pool) is None            # từ thuần Hàn: không có âm Hán Việt
    # mode cloze nhưng chưa có nội dung AI -> quay về kiểu cơ bản
    assert live.make_question("cloze", WORDS, set(), {"cloze": {}, "trans": {}})["mode"] == "ko2vi"
    items = {"cloze": {10: {"answer": "기다리세요", "distractors": ["먹으세요", "자세요", "가세요"]}}, "trans": {}}
    assert live.make_question("cloze", AIW, set(), items)["mode"] == "cloze"
    kinds = {live.make_question("all", AIW, set(), items)["mode"] for _ in range(60)}
    assert kinds == {"ko2vi", "vi2ko", "cloze"}                 # hanviet thiếu 4 âm khác nhau, trans chưa có


def test_cloze_round_hides_romanization():
    items = {"cloze": {10: {"answer": "기다리세요", "distractors": ["먹으세요", "자세요", "가세요"]}}, "trans": {}}
    g = live.LiveGame(lambda recent, cfg: live.make_question("cloze", AIW, recent, items), clock=Clock(), persist=False)
    g.configure({"boss_every": 0, "listen_every": 0})
    g.start()
    q = g.state()["question"]
    assert q["mode"] == "cloze" and q["word"]["romanization"] == "" and q["hint"] == "Hãy đợi ở đây."
    g.handle(C("an", "기다리세요"))                              # gõ thẳng đáp án tiếng Hàn
    assert g.answers["an"]["correct"]


def test_api_ai_flow(client, monkeypatch):
    c = client
    c.put("/api/config", json={"hansong_url": "http://hansong.test", "hansong_password": "pw"})
    assert c.post("/api/ai/generate", json={"n": 5}).status_code == 400            # chưa có key
    c.put("/api/config", json={"openai_key": "sk-secret-123", "ai": {"provider": "openai", "model_openai": "gpt-x",
                                                                      "verify": False}}).raise_for_status()
    assert c.put("/api/config", json={"ai": {"model_openai": "bad model!"}}).status_code == 400
    a = c.get("/api/admin").json()["ai"]
    assert a["has_openai_key"] and a["model_openai"] == "gpt-x" and not a["verify"]
    assert "sk-secret-123" not in c.get("/api/admin").text

    def chat(provider, model, key, system, user):
        assert key == "sk-secret-123" and model == "gpt-x"
        import json as _j
        ws = _j.loads(user.split("Dữ liệu:\n", 1)[1])
        return {"items": [{"id": w["id"], "cloze": {"answer": w["example_ko"].split()[0],
                                                   "distractors": ["가요", "봐요", "와요"]},
                           "trans_wrong": ["Sai một.", "Sai hai.", "Sai ba."]} for w in ws]}
    monkeypatch.setattr(ai, "_chat", chat)
    monkeypatch.setattr(ai.generate_items, "__defaults__", (chat, None))
    c.post("/api/ai/clear")
    c.post("/api/ai/generate", json={"n": 5}).raise_for_status()
    for _ in range(200):                                       # job chạy nền: chờ tối đa 10 giây
        if not main.AI_JOB["running"]:
            break
        import time as _t; _t.sleep(0.05)
    assert main.AI_JOB["detail"].startswith("Xong"), main.AI_JOB["detail"]
    assert c.get("/api/admin").json()["ai"]["counts"] == {"cloze": 5, "trans": 5}
    q = main.picker(set(), dict(live.DEFAULT_CONFIG, mode="trans"))
    assert q["mode"] == "trans" and "Sai một." in q["options"]
    assert c.post("/api/ai/generate", json={"n": 5}).status_code == 400            # mọi từ đã có


# ---------------------------------------------------------------- bot Hami
from app import bot as botmod


def test_bot_parse_ask():
    assert botmod.parse_ask("bot ơi 사랑 nghĩa là gì") == "사랑 nghĩa là gì"
    assert botmod.parse_ask("Hami, chào bạn") == "chào bạn"
    assert botmod.parse_ask("@bot hello") == "hello"
    for t in ("bot", "bota", "A", "đội đỏ", "robot ơi"):
        assert botmod.parse_ask(t) is None


def test_bot_reacts_and_queues_asks():
    g, clock = make_game()
    g.configure({"boss_every": 0, "listen_every": 0})
    g.start()
    assert g.bot_lines[-1]["mood"] == "talk"                      # chào câu mới
    g.handle(C("an", "bot ơi 안녕 là gì"))
    g.handle(C("an", "bot ơi hỏi tiếp"))                          # cùng người trong 40 giây: bỏ qua
    assert [a["text"] for a in g.bot_asks] == ["안녕 là gì"] and "an" not in g.players  # câu hỏi bot không phải đáp án
    clock.t += 15.5; g.tick()                                      # còn <= 5 giây -> giục
    assert g.bot_lines[-1]["mood"] == "hurry"
    n = g.bot_seq
    g.handle({"type": "gift", "user": {"id": "u", "name": "Lan"}, "count": 1, "gift_name": "Rose", "diamonds": 1})
    assert g.bot_seq == n                                          # quà nhỏ ngay sau câu giục: nhường
    g.handle({"type": "gift", "user": {"id": "u", "name": "Lan"}, "count": 1, "gift_name": "Donut", "diamonds": 30})
    assert g.bot_lines[-1]["mood"] == "dance" and "Lan" in g.bot_lines[-1]["text"]   # quà lớn: luôn cảm ơn
    clock.t += 15; g.tick()
    assert g.phase == "reveal" and g.bot_lines[-1]["mood"] == "sad"   # không ai trả lời
    g.configure({"bot": 0})
    n = g.bot_seq
    g.skip()
    assert g.bot_seq == n and g.state()["bot"] is None


def test_bot_reply_never_leaks_answer_during_question():
    g, clock = make_game()
    g.configure({"boss_every": 0, "listen_every": 0})
    g.start()
    right = g.q["options"][g.q["answer"]]                         # "trường học"
    g.bot_reply("an", "학교 là gì", f"학교 nghĩa là {right} nha!")
    assert not any(right in l["text"] for l in g.bot_lines) and len(g.bot_hold) == 1
    g.bot_reply("binh", "chào bot", "Chào bạn nha! 👋")             # không dính đáp án: nói ngay
    assert g.bot_lines[-1]["text"] == "@binh Chào bạn nha! 👋"
    g.skip()                                                       # hiện đáp án -> mới nói câu bị giữ
    assert any(right in l["text"] for l in g.bot_lines) and not g.bot_hold


def test_ai_bot_reply_cleans_output():
    def chat(provider, model, key, system, user, timeout=0):
        assert "Hami" in system and timeout == 20
        return {"reply": "  Xem ở https://x.y nhé " + "a" * 200}
    r = ai.bot_reply(ai.DEFAULT_AI, "k", "an", "hỏi", chat=chat)
    assert "http" not in r and len(r) <= 141 and r.endswith("…")


# ---------------------------------------------------------------- hết credit AI (báo thật)
def test_ai_classify_credit_errors():
    assert isinstance(ai.classify("deepseek", 402, '{"error":{"message":"Insufficient Balance"}}'), ai.AICreditError)
    e = ai.classify("openai", 429, '{"error":{"code":"insufficient_quota"}}')
    assert isinstance(e, ai.AICreditError) and e.kind == "credit"
    assert ai.classify("openai", 401, "bad key").kind == "key"
    rate = ai.classify("openai", 429, '{"error":{"code":"rate_limit_exceeded"}}')   # quá tải tạm thời: không phải hết tiền
    assert not isinstance(rate, ai.AICreditError)

    def broke(*a, **k):
        raise ai.AICreditError("hết tiền")
    with pytest.raises(ai.AICreditError):
        ai.generate_items(AIW, ai.DEFAULT_AI, "k", chat=broke)


def test_support_line_and_ai_down_flow():
    g, clock = make_game()
    g.configure({"boss_every": 0, "listen_every": 0, "support_every": 2})
    g.start(); g.skip()
    assert g.bot_lines[-1]["mood"] != "love"                        # câu 1: chưa mời
    g.skip(); g.skip()
    assert g.bot_lines[-1]["text"] in botmod.LINES["support"]       # câu 2: mời ủng hộ (lời thật)
    g.set_ai_down("credit")
    assert g.bot_lines[-1]["text"] in botmod.LINES["ai_broke"] and g.state()["ai_down"] == "credit"
    n = g.bot_seq
    g.set_ai_down("credit")                                         # không đổi trạng thái: không nói lại
    assert g.bot_seq == n
    clock.t += 10
    g.bot_unavailable("Lan")
    assert "@Lan" in g.bot_lines[-1]["text"]
    n = g.bot_seq
    g.bot_unavailable("Tuấn")                                       # trong 30 giây: im lặng
    assert g.bot_seq == n
    g.set_ai_down("")
    assert g.bot_lines[-1]["text"] in botmod.LINES["ai_back"]
    assert not any("hết" in t and "credit" in t for t in botmod.LINES["support"])   # lời mời không bao giờ nói hết tiền


def test_bot_pump_marks_credit_down(client, monkeypatch):
    c = client
    c.put("/api/config", json={"deepseek_key": "sk-ds", "ai": {"provider": "deepseek"}}).raise_for_status()
    calls = []

    def broke(cfg, key, name, text, chat=None):
        calls.append(text)
        raise ai.AICreditError("deepseek: tài khoản AI đã hết tiền / hết hạn mức")
    monkeypatch.setattr(ai, "bot_reply", broke)
    g = main.GAME
    g.configure({"bot": 1, "bot_ai": 1})
    g.set_ai_down("")
    main.BOT.update(busy=False, last=0.0, down_at=0.0)
    g.bot_asks.append({"uid": "a", "name": "An", "text": "사랑?"})
    main.bot_pump()
    for _ in range(200):
        if not main.BOT["busy"]:
            break
        import time as _t; _t.sleep(0.05)
    assert calls == ["사랑?"] and g.ai_down == "credit"
    assert c.get("/api/admin").json()["ai"]["down"] == "credit"
    main.BOT["last"] = 0.0
    g.bot_asks.append({"uid": "b", "name": "Bình", "text": "hỏi tiếp"})
    main.bot_pump()                                                  # đang hết tiền: không gọi API nữa
    assert calls == ["사랑?"]
    c.put("/api/config", json={"deepseek_key": "sk-new"})            # lưu key mới -> lần sau thử lại ngay
    assert main.BOT["down_at"] == 0.0
    g.set_ai_down("")
