"""Chế độ TikTok LIVE: người xem comment A/B/C/D để đoán nghĩa từ vựng.

Engine thuần (không phụ thuộc TikTok SDK). Mọi sự kiện đi vào qua `handle(event)` dưới dạng dict đã chuẩn hoá:
  {"type": "comment"|"gift"|"like"|"join"|"follow"|"share"|"audience", "user": {"id", "name"}, ...}
Đồng hồ được truyền vào để test được.

Theo quy định TikTok: quà chỉ tạo hiệu ứng cố định cho cả phòng, KHÔNG BAO GIỜ quy ra điểm.
  - mọi món quà: loại 1 đáp án sai của câu đang hỏi
  - quà lớn (>= gift_big kim cương): thêm 10 giây cho câu đang hỏi + phát lại âm thanh
  - quà rất lớn (>= gift_huge): tên người tặng hiện là "nhà tài trợ" của câu kế tiếp
  - tổng kim cương cả phòng đủ gift_goal: câu kế tiếp là câu boss
"""
import json
import random
import re
import threading
import time
import unicodedata
from collections import deque

from . import bot, db
from .norm import norm_ko, norm_vi

LETTERS = "ABCD"

DEFAULT_CONFIG = {
    "question_s": 20,      # thời gian trả lời mỗi câu
    "reveal_s": 8,         # thời gian hiện đáp án (phát âm thanh 2 luồng)
    "board_every": 8,      # cứ N câu thì hiện bảng xếp hạng
    "board_s": 10,
    "like_goal": 300,      # đủ N tim -> câu kế tiếp nhân đôi điểm
    "share_goal": 10,      # đủ N lượt chia sẻ -> câu kế tiếp nhân đôi điểm
    "gift_goal": 300,      # tổng kim cương cả phòng đủ N -> câu kế tiếp là câu boss
    "gift_big": 30,        # 1 lần tặng >= N kim cương -> +10 giây, phát lại âm thanh
    "gift_huge": 100,      # 1 lần tặng >= N kim cương -> nhà tài trợ câu kế tiếp
    "boss_every": 10,      # cứ N câu có 1 câu boss (x3 điểm, thời gian ngắn hơn). 0 = tắt
    "listen_every": 5,     # cứ N câu có 1 câu nghe (chỉ phát âm, không hiện chữ). 0 = tắt
    "teams": 1,            # bật đội Đỏ / Xanh
    "vote": 1,             # bình chọn kiểu câu trong lúc hiện bảng xếp hạng
    "live_counts": 1,      # hiện số người chọn từng đáp án ngay trong lúc hỏi
    "safe": 1,             # dồn nội dung vào vùng an toàn, chừa chỗ cho giao diện TikTok (comment, ô nhập, tên host)
    "safe_top": 12,        # % chiều cao phía trên dành cho TikTok (tên host, số người xem)
    "safe_bottom": 62,     # nội dung overlay kết thúc ở % này; phía dưới là comment + ô nhập của TikTok
    "bot": 1,              # bot linh vật Hami
    "bot_ai": 1,           # người xem gõ "bot ..." để hỏi, AI trả lời
    "bot_voice": 1,        # Hami đọc to câu thoại bằng giọng dễ thương (OpenAI TTS, cần OpenAI key)
    "round_len": 20,       # mỗi vòng N câu; câu cuối là "chung kết vòng" (x3), xong vinh danh Vua vòng. 0 = tắt
    "sfx": 1,              # hiệu ứng âm thanh trên overlay (tích tắc, ting, reo hò…)
    "support_every": 12,   # cứ N câu Hami mời thả tim / follow / ủng hộ kênh 1 lần (nói thật, không đổi quà lấy điểm). 0 = tắt
    "source": "all",       # nguồn từ: all | today | due | hard | new | mastered
    "mode": "all",         # ko2vi | vi2ko | mix (2 kiểu trên) | cloze | trans | hanviet | all (trộn mọi kiểu đang có)
}
LIMITS = {"question_s": (8, 120), "reveal_s": (3, 30), "board_every": (0, 50), "board_s": (4, 30),
          "like_goal": (0, 100000), "share_goal": (0, 10000), "gift_goal": (0, 1000000),
          "gift_big": (1, 1000000), "gift_huge": (1, 1000000), "boss_every": (0, 100), "listen_every": (0, 100),
          "teams": (0, 1), "vote": (0, 1), "live_counts": (0, 1), "safe": (0, 1), "safe_top": (0, 30),
          "safe_bottom": (40, 100), "bot": (0, 1), "bot_ai": (0, 1), "bot_voice": (0, 1),
          "support_every": (0, 100), "round_len": (0, 100), "sfx": (0, 1)}
SOURCES = ("all", "today", "due", "hard", "new", "mastered")
MODES = ("ko2vi", "vi2ko", "mix", "cloze", "trans", "hanviet", "all")
KINDS = ("ko2vi", "vi2ko", "cloze", "trans", "hanviet")   # các kiểu câu thật sự
BLANK = "＿＿＿"
SPECIALS = ("boss", "listen")
BOSS_MULT = 3
EXTRA_S = 10           # quà lớn cộng thêm bao nhiêu giây
EXTRA_MAX = 30         # tối đa cộng thêm cho 1 câu
TEAMS = {"red": "Đỏ", "blue": "Xanh"}
TEAM_ICON = {"red": "🔴", "blue": "🔵"}
VOTE_OPTS = [("ko2vi", "Hàn → Việt"), ("vi2ko", "Việt → Hàn"), ("listen", "Nghe đoán nghĩa")]


def clean_config(raw: dict, base: dict | None = None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update(base or {})
    for k, v in (raw or {}).items():
        if k in LIMITS:
            try:
                lo, hi = LIMITS[k]
                cfg[k] = max(lo, min(hi, int(v)))
            except (TypeError, ValueError):
                pass
        elif k == "source" and v in SOURCES:
            cfg[k] = v
        elif k == "mode" and v in MODES:
            cfg[k] = v
    if cfg["gift_huge"] < cfg["gift_big"]:
        cfg["gift_huge"] = cfg["gift_big"]
    return cfg


def week_key(t: float) -> str:
    return time.strftime("%G-W%V", time.localtime(t))


# ---------------------------------------------------------------- answer parsing
_LETTER_RE = re.compile(r"^(?:đáp án|dap an|đáp|chọn|chon|câu|cau)?\s*([a-d1-4])\s*[\.\!\)\s]*$", re.I)
_TEAM_RE = re.compile(r"^(?:doi|team|#)\s*(do|red|xanh|blue)$")
_VOTE_RE = re.compile(r"^(?:so|chon|vote|#)?\s*([1-3])\s*[\.\!\s]*$")


def plain(s: str) -> str:
    """Bỏ dấu tiếng Việt, chữ thường, gộp khoảng trắng: dùng cho lệnh comment."""
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def parse_answer(text: str, options: list[str], lang: str) -> int | None:
    """Trả về chỉ số đáp án (0..n-1) hoặc None nếu comment không phải câu trả lời."""
    t = (text or "").strip()
    if not t:
        return None
    m = _LETTER_RE.match(t)
    if m:
        ch = m.group(1).upper()
        idx = int(ch) - 1 if ch.isdigit() else LETTERS.index(ch)
        return idx if idx < len(options) else None
    # gõ thẳng đáp án
    if lang == "ko":
        key = norm_ko(t)
        for i, o in enumerate(options):
            if key and key == norm_ko(o):
                return i
    else:
        key = norm_vi(t)
        for i, o in enumerate(options):
            if key and key == norm_vi(o):
                return i
    return None


def is_score_cmd(text: str) -> bool:
    return norm_vi(text) in ("điểm", "diem", "top", "hạng", "hang", "điểm của tôi")


def parse_team(text: str) -> str | None:
    m = _TEAM_RE.match(plain(text))
    if not m:
        return None
    return "red" if m.group(1) in ("do", "red") else "blue"


def parse_vote(text: str) -> int | None:
    m = _VOTE_RE.match(plain(text))
    return int(m.group(1)) - 1 if m else None


# ---------------------------------------------------------------- question building
def build_question(word: dict, pool: list[dict], mode: str) -> dict | None:
    """word + pool (các từ khác) -> câu hỏi 4 lựa chọn. pool phải chứa korean/vietnamese/id."""
    if mode == "mix":
        mode = random.choice(("ko2vi", "vi2ko"))
    field, other = ("vietnamese", "korean") if mode == "ko2vi" else ("korean", "vietnamese")
    norm = norm_ko if field == "korean" else norm_vi
    right = word[field]
    seen = {norm(right)}
    wrong = []
    for p in pool:
        k = norm(p[field])
        if p["id"] != word["id"] and k and k not in seen:
            seen.add(k)
            wrong.append(p[field])
        if len(wrong) == 3:
            break
    if not wrong:
        return None
    options = wrong + [right]
    random.shuffle(options)
    return {
        "word_id": word["id"],
        "mode": mode,
        "prompt": word[other],
        "prompt_lang": "ko" if other == "korean" else "vi",
        "answer_lang": "ko" if field == "korean" else "vi",
        "options": options,
        "answer": options.index(right),
        "word": _word(word),
    }


def _word(word: dict) -> dict:
    return {k: word.get(k, "") for k in ("id", "korean", "romanization", "vietnamese", "hanviet", "pos",
                                         "example_ko", "example_vi")}


def _shuffled(right: str, wrong: list[str]) -> tuple[list[str], int]:
    options = list(wrong[:3]) + [right]
    random.shuffle(options)
    return options, options.index(right)


def build_hanviet(word: dict, pool: list[dict]) -> dict | None:
    """Hiện từ tiếng Hàn, chọn âm Hán Việt. Không cần AI."""
    right = (word.get("hanviet") or "").strip()
    if not right:
        return None
    seen, wrong = {norm_vi(right)}, []
    for p in pool:
        h = (p.get("hanviet") or "").strip()
        if h and p["id"] != word["id"] and norm_vi(h) not in seen:
            seen.add(norm_vi(h))
            wrong.append(h)
        if len(wrong) == 3:
            break
    if len(wrong) < 3:
        return None
    options, ans = _shuffled(right, wrong)
    return {"word_id": word["id"], "mode": "hanviet", "prompt": word["korean"], "prompt_lang": "ko",
            "answer_lang": "vi", "options": options, "answer": ans, "hint": word.get("vietnamese", ""),
            "audio_q": "ko_word", "word": _word(word)}


def build_cloze(word: dict, item: dict) -> dict | None:
    """Câu ví dụ bị khoét chỗ trống, chọn cụm tiếng Hàn đúng. item do AI tạo (ai.clean_cloze)."""
    ex, ans = word.get("example_ko") or "", item.get("answer") or ""
    if not ans or ans not in ex or len(item.get("distractors") or []) < 3:
        return None
    options, idx = _shuffled(ans, item["distractors"])
    return {"word_id": word["id"], "mode": "cloze", "prompt": ex.replace(ans, BLANK, 1), "prompt_lang": "ko",
            "answer_lang": "ko", "options": options, "answer": idx, "hint": word.get("example_vi", ""),
            "audio_q": None, "audio_reveal": "ko_ex", "word": _word(word)}


def build_trans(word: dict, item: dict) -> dict | None:
    """Nghe + đọc câu tiếng Hàn, chọn bản dịch đúng. item do AI tạo (ai.clean_trans)."""
    right = word.get("example_vi") or ""
    if not right or not word.get("example_ko") or len(item.get("wrong") or []) < 3:
        return None
    options, idx = _shuffled(right, item["wrong"])
    return {"word_id": word["id"], "mode": "trans", "prompt": word["example_ko"], "prompt_lang": "ko",
            "answer_lang": "vi", "options": options, "answer": idx, "hint": "",
            "audio_q": "ko_ex", "word": _word(word)}


def make_question(mode: str, words: list[dict], recent: set, items: dict, pool_size=40) -> dict | None:
    """Chọn từ + dựng câu hỏi theo mode. items = {"cloze": {word_id: data}, "trans": {...}} (nội dung AI).
    mode mix/all: thử lần lượt các kiểu theo thứ tự ngẫu nhiên, kiểu nào thiếu dữ liệu thì bỏ qua."""
    if len(words) < 2:
        return None
    if mode == "all":
        order = random.sample(KINDS, len(KINDS))
    elif mode == "mix":
        order = random.sample(("ko2vi", "vi2ko"), 2)
    else:
        order = [mode]
    for kind in order + ["ko2vi"]:          # thiếu dữ liệu thì quay về kiểu cơ bản
        if kind in ("cloze", "trans"):
            got = items.get(kind) or {}
            cands = [w for w in words if w["id"] in got]
        elif kind == "hanviet":
            cands = [w for w in words if (w.get("hanviet") or "").strip()]
        else:
            cands = words
        if not cands:
            continue
        fresh = [w for w in cands if w["id"] not in recent] or cands
        word = random.choice(fresh)
        if kind == "hanviet":
            pool = random.sample(cands, len(cands))
        else:
            pool = random.sample(words, min(len(words), pool_size))
        if kind == "cloze":
            q = build_cloze(word, items["cloze"][word["id"]])
        elif kind == "trans":
            q = build_trans(word, items["trans"][word["id"]])
        elif kind == "hanviet":
            q = build_hanviet(word, pool)
        else:
            q = build_question(word, pool, kind)
        if q:
            return q
    return None


# ---------------------------------------------------------------- engine
class LiveGame:
    def __init__(self, picker, clock=time.time, persist=True):
        """picker(recent_ids:set, cfg:dict) -> question dict (build_question) hoặc None."""
        self.picker = picker
        self.clock = clock
        self.persist = persist
        self.lock = threading.RLock()
        self.cfg = dict(DEFAULT_CONFIG)
        self.phase = "idle"          # idle | question | reveal | board
        self.phase_end = 0.0
        self.qid = 0
        self.q: dict | None = None
        self.q_duration = 0          # thời lượng câu hiện tại (đã tính câu boss + giây cộng thêm)
        self.extra = 0               # số giây quà đã cộng cho câu hiện tại
        self.replay = 0              # tăng lên = overlay phát lại âm thanh đề
        self.q_comments = 0          # số comment nhận được trong lúc hỏi câu này
        self.special: str | None = None       # boss | listen | None
        self.queued: deque = deque(maxlen=3)  # vòng đặc biệt đã xếp hàng (admin, mục tiêu quà)
        self.sponsor: str | None = None
        self.sponsors: deque = deque(maxlen=5)
        self.answers: dict[str, dict] = {}    # user_id -> {idx, at, correct, points}
        self.hints: list[int] = []            # các đáp án sai đã bị loại
        self.double = False                   # câu hiện tại x2
        self.double_next = False
        self.rounds = 0
        self.recent: deque = deque(maxlen=40)
        self.players: dict[str, dict] = {}    # điểm trong phiên live
        self.teams = {k: {"score": 0, "members": 0} for k in TEAMS}
        self.vote: dict | None = None         # đang mở bình chọn: {"counts": [..], "voters": set()}
        self.vote_mode: str | None = None     # kết quả bình chọn, áp dụng tới lần hiện bảng kế tiếp
        self.feed: deque = deque(maxlen=12)
        self.feed_seq = 0
        self.likes = 0
        self.like_mark = 0
        self.shares = 0
        self.share_mark = 0
        self.diamonds = 0
        self.diamond_mark = 0
        self.follows = 0
        self.viewers = 0
        self.last_join = 0.0
        self.last_result: dict | None = None
        self.message = ""
        self._saved: dict[str, dict] = {}     # phần điểm đã ghi vào DB, để chỉ cộng phần chênh lệch
        self.bot_lines: deque = deque(maxlen=8)   # câu thoại của bot cho overlay: {seq, text, mood, at}
        self.bot_seq = 0
        self.bot_last = -1e9
        self.bot_join_at = -1e9
        self.hurried = False
        self.bot_asks: deque = deque(maxlen=3)   # câu người xem hỏi bot, main.py lấy ra gọi AI
        self.bot_cool: dict[str, float] = {}     # user_id -> lần hỏi bot gần nhất
        self.bot_hold: list[dict] = []           # câu AI trả lời có lộ đáp án: giữ lại tới lúc hiện đáp án
        self.ai_down = ""                        # "" | credit | key: API AI hỏng thật (main.py báo vào)
        self.greet_buf: list[dict] = []          # người mới vào phòng chờ được Hami chào (gom nhóm)
        self.greet_at = -1e9
        self.recent_ans: deque = deque(maxlen=6)   # dải "vừa trả lời" trên overlay
        self.round_no = 1                        # vòng hiện tại (round_len câu / vòng)
        self.round_q = 0                         # số câu đã hỏi trong vòng
        self.round_end: dict | None = None       # đang vinh danh cuối vòng: {no, podium, king}
        self.king_uid: str | None = None         # Vua vòng trước: đội vương miện
        self.ai_off_at = -1e9

    # -------------------------------------------------------- helpers
    def _push(self, kind: str, text: str, **extra):
        self.feed_seq += 1
        self.feed.append({"seq": self.feed_seq, "kind": kind, "text": text, "at": self.clock(), **extra})

    def _bot_raw(self, text: str, mood: str):
        self.bot_seq += 1
        self.bot_last = self.clock()
        self.bot_lines.append({"seq": self.bot_seq, "text": text, "mood": mood, "at": self.bot_last})

    def _bot(self, kind: str, force: bool = True, **kw):
        """force=False: câu phụ (chào người mới…), bỏ qua nếu bot vừa nói trong 5 giây để không lấn câu quan trọng."""
        if not self.cfg["bot"] or (not force and self.clock() - self.bot_last < 5):
            return
        self._bot_raw(*bot.line(kind, **kw))

    def bot_reply(self, name: str, ask: str, reply: str):
        """Câu trả lời AI cho người xem. Nếu đang hỏi mà câu hỏi/câu trả lời dính tới đáp án thì giữ tới lúc hiện đáp án."""
        with self.lock:
            line = {"text": f"@{name[:18]} {reply}", "mood": "talk"}
            if self.phase == "question" and self.q:
                q = self.q
                secrets = [q["options"][q["answer"]], q["word"].get("korean", ""), q["word"].get("vietnamese", "")]
                if bot.leaks(ask, secrets) or bot.leaks(reply, secrets):
                    self.bot_hold.append(line)
                    return
            self._bot_raw(line["text"], line["mood"])

    def set_ai_down(self, kind: str):
        """main.py gọi khi API AI hết tiền / key hỏng ("credit"/"key") hoặc chạy lại được (""). Chỉ nói khi đổi trạng thái."""
        with self.lock:
            if kind == self.ai_down:
                return
            was, self.ai_down = self.ai_down, kind
            if kind == "credit":
                self._bot("ai_broke")
            elif kind == "key":
                self._bot("ai_key")
            elif was:
                self._bot("ai_back")

    def bot_unavailable(self, name: str):
        """Có người hỏi bot lúc AI đang hỏng: trả lời soạn sẵn, tối đa 1 lần / 30 giây."""
        with self.lock:
            if self.clock() - self.ai_off_at >= 30:
                self.ai_off_at = self.clock()
                self._bot("ai_off" if self.ai_down != "key" else "ai_key", force=False, name=name)

    def _player(self, user: dict) -> dict:
        uid = str(user["id"])
        p = self.players.get(uid)
        if not p:
            p = self.players[uid] = {"id": uid, "name": user.get("name") or uid, "score": 0, "correct": 0,
                                     "answered": 0, "streak": 0, "best_streak": 0, "gifts": 0, "diamonds": 0,
                                     "team": None, "round_score": 0, "avatar": None}
        if user.get("name"):
            p["name"] = user["name"][:40]
        if user.get("avatar"):
            p["avatar"] = user["avatar"]
        return p

    def _rank(self, uid: str) -> int:
        order = sorted(self.players.values(), key=lambda p: (-p["score"], p["name"]))
        for i, p in enumerate(order):
            if p["id"] == uid:
                return i + 1
        return 0

    def _goal(self, total: int, mark: int, goal: int) -> tuple[bool, int]:
        """(đạt mốc?, mark mới). Dùng chung cho tim, chia sẻ, kim cương."""
        if goal and total - mark >= goal:
            return True, total - (total - mark) % goal
        return False, mark

    # -------------------------------------------------------- control
    def configure(self, raw: dict):
        with self.lock:
            self.cfg = clean_config(raw, self.cfg)

    def start(self):
        with self.lock:
            if self.phase == "idle":
                self._next_question()

    def pause(self):
        with self.lock:
            self.phase = "idle"
            self.q = None
            self.vote = None
            self.message = "Tạm dừng"

    def skip(self):
        with self.lock:
            if self.phase == "question":
                self._reveal()
            else:
                self._next_question()

    def queue(self, kind: str) -> bool:
        """Admin ép vòng đặc biệt cho câu kế tiếp: boss | listen | double."""
        with self.lock:
            if kind == "double":
                self.double_next = True
                self._push("system", "⚡ Câu tiếp theo nhân đôi điểm!", alert=True)
                return True
            if kind not in SPECIALS:
                return False
            self.queued.append(kind)
            self._push("system", "👹 Sắp có CÂU BOSS x3 điểm!" if kind == "boss" else "🎧 Sắp có CÂU NGHE!",
                       alert=True)
            return True

    def reset_scores(self):
        with self.lock:
            self.players.clear()
            self._saved.clear()
            self.rounds = 0
            self.likes = self.like_mark = 0
            self.shares = self.share_mark = 0
            self.diamonds = self.diamond_mark = 0
            self.follows = 0
            self.double_next = False
            self.teams = {k: {"score": 0, "members": 0} for k in TEAMS}
            self.vote_mode = None
            self.round_no, self.round_q, self.round_end, self.king_uid = 1, 0, None, None
            self.recent_ans.clear()
            self._push("system", "Đã xoá bảng điểm phiên này")

    def _greet(self):
        """Gom người mới vào phòng thành 1 câu chào, tối đa 1 câu / 12 giây, không chen ngang câu bot vừa nói."""
        if not self.greet_buf or not self.cfg["bot"]:
            self.greet_buf = [] if not self.cfg["bot"] else self.greet_buf
            return
        now = self.clock()
        if now - self.greet_at < 12 or now - self.bot_last < 2.5:
            return
        names = [g["name"] for g in self.greet_buf]
        self.greet_buf = []
        self.greet_at = now
        if len(names) == 1:
            self._bot("greet1", a=names[0])
        elif len(names) == 2:
            self._bot("greet2", a=names[0], b=names[1])
        else:
            self._bot("greetN", a=names[-1], b=names[-2], n=len(names) - 2)

    def _end_round(self):
        """Hết câu chung kết: vinh danh top 3 của vòng, Vua vòng có vương miện tới hết vòng sau."""
        order = sorted((p for p in self.players.values() if p["round_score"] > 0),
                       key=lambda p: (-p["round_score"], p["name"]))
        podium = [{"name": p["name"], "avatar": p["avatar"], "score": p["round_score"]} for p in order[:3]]
        king = order[0] if order else None
        self.king_uid = king["id"] if king else None
        self.round_end = {"no": self.round_no, "podium": podium, "king": podium[0] if podium else None}
        self.vote = None
        self.phase = "board"
        self.phase_end = self.clock() + self.cfg["board_s"] + 4
        if king:
            self._bot("round_king", name=king["name"], no=self.round_no, score=king["round_score"])
        else:
            self._bot("round_none", no=self.round_no)

    def _close_vote(self):
        v, self.vote = self.vote, None
        if not v:
            return
        total = sum(v["counts"])
        if not total:
            self.vote_mode = None
            return
        i = max(range(len(VOTE_OPTS)), key=lambda j: v["counts"][j])
        self.vote_mode = VOTE_OPTS[i][0]
        self._push("vote", f"🗳 Khán giả chọn: {VOTE_OPTS[i][1]} ({v['counts'][i]}/{total} phiếu)", alert=True)

    def _next_question(self):
        self._close_vote()
        if self.round_end:                    # vừa vinh danh xong: sang vòng mới
            self.round_end = None
            self.round_no += 1
            self.round_q = 0
            for p in self.players.values():
                p["round_score"] = 0
        n = self.qid + 1
        special = None
        final = bool(self.cfg["round_len"]) and self.round_q + 1 >= self.cfg["round_len"]
        if final:
            special = "final"
        elif self.queued:
            special = self.queued.popleft()
        elif self.cfg["boss_every"] and n % self.cfg["boss_every"] == 0:
            special = "boss"
        elif self.vote_mode == "listen" or (self.cfg["listen_every"] and n % self.cfg["listen_every"] == 0):
            special = "listen"
        pcfg = dict(self.cfg)
        if special == "listen":
            pcfg["mode"] = "ko2vi"          # câu nghe: phát tiếng Hàn, chọn nghĩa Việt
        elif self.vote_mode in ("ko2vi", "vi2ko"):
            pcfg["mode"] = self.vote_mode
        q = self.picker(set(self.recent), pcfg)
        if not q:
            self.phase, self.q = "idle", None
            self.message = "Cần ít nhất 2 từ có âm thanh trong nguồn từ đã chọn"
            return
        self.qid = n
        self.q = q
        self.special = special
        self.round_q += 1
        self.recent_ans.clear()
        self.recent.append(q["word_id"])
        self.answers = {}
        self.hints = []
        self.extra = 0
        self.replay = 0
        self.q_comments = 0
        self.double, self.double_next = self.double_next, False
        self.sponsor = self.sponsors.popleft() if self.sponsors else None
        self.last_result = None
        self.message = ""
        self.phase = "question"
        dur = self.cfg["question_s"]
        if special in ("boss", "final"):
            dur = max(8, round(dur * 0.6))
        self.q_duration = dur
        self.phase_end = self.clock() + dur
        self.hurried = False
        if self.sponsor:
            self._bot("q_sponsor", name=self.sponsor)
        elif special in SPECIALS or special == "final":
            self._bot("q_" + special)
        elif q["mode"] in ("cloze", "trans", "hanviet"):
            self._bot("q_" + q["mode"])
        else:
            self._bot("q")

    def _reveal(self):
        q = self.q
        counts = [0] * len(q["options"])
        for a in self.answers.values():
            counts[a["idx"]] += 1
        winners = sorted((a for a in self.answers.values() if a["correct"]), key=lambda a: a["at"])
        self.last_result = {
            "counts": counts,
            "total": len(self.answers),
            "correct": len(winners),
            "fastest": [{"name": self.players[a["uid"]]["name"], "points": a["points"]} for a in winners[:3]],
        }
        self.rounds += 1
        self.phase = "reveal"
        self.phase_end = self.clock() + self.cfg["reveal_s"]
        if self.persist:
            if self.answers:
                self._save([self.players[u] for u in self.answers])
            self._log_round(len(winners))
        total = len(self.answers)
        if not total:
            self._bot("reveal_none")
        else:
            pct = round(100 * len(winners) / total)
            name = self.players[winners[0]["uid"]]["name"] if winners else ""
            kind = "reveal_zero" if not winners else "reveal_low" if pct < 40 else "reveal_mid" if pct < 80 \
                else "reveal_high"
            self._bot(kind, pct=pct, name=name)
        for line in self.bot_hold:
            self._bot_raw(line["text"], line["mood"])
        self.bot_hold = []
        every = self.cfg["support_every"]
        if every and self.rounds % every == 0:
            self._bot("support")

    def tick(self):
        with self.lock:
            if self.phase == "question" and not self.hurried and self.q_duration >= 10 \
                    and 0 < self.phase_end - self.clock() <= 5:
                self.hurried = True
                self._bot("hurry")
            self._greet()
            if self.phase == "idle" or self.clock() < self.phase_end:
                return
            if self.phase == "question":
                self._reveal()
            elif self.phase == "reveal":
                every = self.cfg["board_every"]
                if self.special == "final" and self.players:
                    self._end_round()
                elif every and self.rounds % every == 0 and self.players:
                    self.phase = "board"
                    self.phase_end = self.clock() + self.cfg["board_s"]
                    if self.cfg["vote"]:
                        self.vote = {"counts": [0] * len(VOTE_OPTS), "voters": set()}
                        self._bot("board_vote")
                    else:
                        lead = min(self.players.values(), key=lambda p: (-p["score"], p["name"]))
                        self._bot("board", name=lead["name"])
                else:
                    self._next_question()
            elif self.phase == "board":
                self._next_question()

    # -------------------------------------------------------- events
    def handle(self, ev: dict):
        with self.lock:
            t = ev.get("type")
            if t == "audience":
                self.viewers = int(ev.get("count") or 0)
                return
            user = ev.get("user") or {}
            if not user.get("id"):
                return
            name = (user.get("name") or "")[:40]
            if t == "comment":
                self._comment(user, ev.get("text") or "")
            elif t == "gift":
                self._gift(user, ev)
            elif t == "like":
                self._like(int(ev.get("count") or 1))
            elif t == "join":
                now = self.clock()
                if now - self.last_join >= 4:      # phòng đông: không để lượt vào phòng lấp hết feed
                    self.last_join = now
                    self._push("join", f"👋 Chào {name}! Comment A/B/C/D để chơi")
                uid = str(user["id"])
                if len(self.greet_buf) < 30 and all(g["uid"] != uid for g in self.greet_buf):
                    self.greet_buf.append({"uid": uid, "name": name})
            elif t == "follow":
                self.follows += 1
                self._push("follow", f"➕ {name} đã theo dõi. Cảm ơn bạn!", alert=True, tier=1)
                self._bot("follow", name=name)
            elif t == "share":
                self._share(name)

    def _comment(self, user: dict, text: str):
        if self.phase == "question":
            self.q_comments += 1
        if is_score_cmd(text):
            p = self._player(user)
            team = f" · đội {TEAMS[p['team']]}" if p["team"] else ""
            self._push("score", f"📊 {p['name']}: {p['score']} điểm · hạng {self._rank(p['id'])} · "
                                f"đúng {p['correct']}/{p['answered']}{team}")
            return
        ask = bot.parse_ask(text)
        if ask is not None and self.cfg["bot"]:
            uid = str(user["id"])
            now = self.clock()
            if self.cfg["bot_ai"] and now - self.bot_cool.get(uid, -1e9) >= 40:   # mỗi người hỏi tối đa 1 lần / 40 giây
                self.bot_cool[uid] = now
                self.bot_asks.append({"uid": uid, "name": (user.get("name") or uid)[:40], "text": ask})
            return
        if self.cfg["teams"]:
            team = parse_team(text)
            if team:
                self._join_team(user, team)
                return
        if self.phase == "board" and self.vote is not None:
            v = parse_vote(text)
            uid = str(user["id"])
            if v is not None and uid not in self.vote["voters"]:
                self.vote["voters"].add(uid)
                self.vote["counts"][v] += 1
            return
        if self.phase != "question" or not self.q:
            return
        idx = parse_answer(text, self.q["options"], self.q["answer_lang"])
        if idx is None:
            return
        uid = str(user["id"])
        if uid in self.answers:       # chỉ tính câu trả lời đầu tiên, chống spam đủ 4 đáp án
            return
        p = self._player(user)
        now = self.clock()
        ok = idx == self.q["answer"]
        points = 0
        p["answered"] += 1
        if ok:
            first = not any(a["correct"] for a in self.answers.values())
            remain = min(1.0, max(0.0, self.phase_end - now) / (self.q_duration or self.cfg["question_s"]))
            p["streak"] += 1
            p["best_streak"] = max(p["best_streak"], p["streak"])
            points = 10 + round(10 * remain) + (5 if first else 0) + (min(10, p["streak"]) if p["streak"] >= 3 else 0)
            if self.double:
                points *= 2
            if self.special in ("boss", "final"):
                points *= BOSS_MULT
            p["score"] += points
            p["round_score"] += points
            p["correct"] += 1
            if p["team"]:
                self.teams[p["team"]]["score"] += points
            if p["streak"] >= 5 and p["streak"] % 5 == 0:
                self._push("streak", f"🔥 {p['name']} đúng liên tiếp {p['streak']} câu!", alert=True, tier=2)
                self._bot("streak", name=p["name"], n=p["streak"])
        else:
            if p["streak"] >= 5:
                self._push("streak", f"💔 {p['name']} mất chuỗi {p['streak']} câu")
                self._bot("streak_lost", name=p["name"], n=p["streak"])
            p["streak"] = 0
        self.answers[uid] = {"uid": uid, "idx": idx, "at": now, "correct": ok, "points": points}
        self.recent_ans.append({"name": p["name"], "avatar": p["avatar"], "letter": LETTERS[idx],
                                "seq": len(self.answers)})

    def _join_team(self, user: dict, team: str):
        p = self._player(user)
        if p["team"] == team:
            return
        if p["team"]:                 # không cho đổi đội giữa phiên, tránh nhảy sang đội đang thắng
            self._push("team", f"{TEAM_ICON[p['team']]} {p['name']} đã ở đội {TEAMS[p['team']]} rồi")
            return
        p["team"] = team
        self.teams[team]["members"] += 1
        self._push("team", f"{TEAM_ICON[team]} {p['name']} vào đội {TEAMS[team]}")

    def _gift(self, user: dict, ev: dict):
        p = self._player(user)
        n = max(1, int(ev.get("count") or 1))
        unit = max(0, int(ev.get("diamonds") or 0))
        total = max(n, unit * n)      # không rõ giá quà thì coi mỗi món 1 kim cương
        p["gifts"] += n
        p["diamonds"] += total
        cfg = self.cfg
        tier = 3 if total >= cfg["gift_huge"] else 2 if total >= cfg["gift_big"] else 1
        gift = (ev.get("gift_name") or "quà")[:40]
        msg = f"🎁 {p['name']} tặng {gift} ×{n}"
        effects = []
        if self.phase == "question" and self.q:
            wrong = [i for i in range(len(self.q["options"])) if i != self.q["answer"] and i not in self.hints]
            if len(wrong) > 1:        # luôn chừa lại ít nhất 1 đáp án sai
                self.hints.append(random.choice(wrong))
                effects.append("loại 1 đáp án sai")
            if tier >= 2 and self.extra < EXTRA_MAX:
                add = min(EXTRA_S, EXTRA_MAX - self.extra)
                self.extra += add
                self.phase_end += add
                self.q_duration += add
                self.replay += 1
                effects.append(f"+{add} giây")
        if tier >= 3:
            self.sponsors.append(p["name"])
            effects.append("tài trợ câu kế tiếp")
        if effects:
            msg += " → " + ", ".join(effects) + "!"
        self._push("gift", msg, alert=tier >= 2, tier=tier, who=p["name"], gift=gift, count=n)
        self._bot("gift_big" if tier >= 2 else "gift", force=tier >= 2, name=p["name"])
        self.diamonds += total
        hit, self.diamond_mark = self._goal(self.diamonds, self.diamond_mark, cfg["gift_goal"])
        if hit:
            self.queued.append("boss")
            self._push("goal", f"💎 Cả phòng đủ {cfg['gift_goal']} kim cương! Sắp có CÂU BOSS x3", alert=True, tier=3)
            self._bot("goal")
        if self.persist:
            self._save([p])

    def _like(self, n: int):
        self.likes += max(1, min(100000, n))
        hit, self.like_mark = self._goal(self.likes, self.like_mark, self.cfg["like_goal"])
        if hit:
            self.double_next = True
            self._push("like", f"❤️ Đủ {self.cfg['like_goal']} tim! Câu tiếp theo nhân đôi điểm", alert=True, tier=2)
            self._bot("goal")

    def _share(self, name: str):
        self.shares += 1
        self._push("share", f"🔁 {name} đã chia sẻ live")
        self._bot("share", force=False, name=name)
        hit, self.share_mark = self._goal(self.shares, self.share_mark, self.cfg["share_goal"])
        if hit:
            self.double_next = True
            self._push("goal", f"🔁 Đủ {self.cfg['share_goal']} lượt chia sẻ! Câu tiếp theo nhân đôi điểm",
                       alert=True, tier=2)

    # -------------------------------------------------------- persistence
    def _save(self, players: list[dict]):
        keys = ("score", "correct", "answered", "gifts", "diamonds")
        week = week_key(self.clock())
        try:
            with db.tx() as c:
                for p in players:
                    old = self._saved.get(p["id"], {})
                    d = {k: p[k] - old.get(k, 0) for k in keys}
                    c.execute(
                        "INSERT INTO live_players(user_id,name,score,correct,answered,best_streak,gifts,diamonds) "
                        "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, "
                        "score=score+excluded.score, correct=correct+excluded.correct, "
                        "answered=answered+excluded.answered, best_streak=MAX(best_streak,excluded.best_streak), "
                        "gifts=gifts+excluded.gifts, diamonds=diamonds+excluded.diamonds, updated_at=datetime('now')",
                        (p["id"], p["name"], d["score"], d["correct"], d["answered"], p["best_streak"], d["gifts"],
                         d["diamonds"]))
                    if d["score"] or d["diamonds"]:
                        c.execute(
                            "INSERT INTO live_weekly(week,user_id,name,score,diamonds) VALUES(?,?,?,?,?) "
                            "ON CONFLICT(week,user_id) DO UPDATE SET name=excluded.name, "
                            "score=score+excluded.score, diamonds=diamonds+excluded.diamonds",
                            (week, p["id"], p["name"], d["score"], d["diamonds"]))
                    self._saved[p["id"]] = {k: p[k] for k in keys}
        except Exception as e:  # không để lỗi DB làm dừng game
            self._push("system", f"Lỗi lưu điểm: {e}")

    def _log_round(self, correct: int):
        try:
            with db.tx() as c:
                c.execute("INSERT INTO live_rounds(word_id,mode,special,answered,correct,comments,viewers) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (self.q["word_id"], self.q["mode"], self.special or "", len(self.answers), correct,
                           self.q_comments, self.viewers))
        except Exception as e:
            self._push("system", f"Lỗi lưu thống kê: {e}")

    # -------------------------------------------------------- snapshot for overlay
    def state(self, boards: dict | None = None) -> dict:
        with self.lock:
            now = self.clock()
            cfg = self.cfg
            q = None
            if self.q and self.phase in ("question", "reveal"):
                reveal = self.phase == "reveal"
                listen = self.special == "listen"
                counts = [0] * len(self.q["options"])
                if reveal or cfg["live_counts"]:
                    for a in self.answers.values():
                        counts[a["idx"]] += 1
                q = {
                    "id": self.qid,
                    "mode": self.q["mode"],
                    "special": self.special,
                    "listen": listen,
                    "prompt": "🎧" if listen and not reveal else self.q["prompt"],
                    "prompt_lang": self.q["prompt_lang"],
                    "options": self.q["options"],
                    "hints": list(self.hints),
                    "double": self.double,
                    "mult": (2 if self.double else 1) * (BOSS_MULT if self.special in ("boss", "final") else 1),
                    "sponsor": self.sponsor,
                    "extra": self.extra,
                    "replay": self.replay,
                    "word_id": self.q["word_id"],
                    "answered": len(self.answers),
                    "counts": counts if (reveal or cfg["live_counts"]) else None,
                    "answer": self.q["answer"] if reveal else None,
                    "hint": self.q.get("hint", "") if not listen else "",
                    "audio_q": self.q.get("audio_q", "ko_word" if self.q["prompt_lang"] == "ko" else "vi_word"),
                    "audio_reveal": self.q.get("audio_reveal", "mix"),
                    "word": self.q["word"] if reveal else
                    {"romanization": self.q["word"]["romanization"]
                     if self.q["mode"] in ("ko2vi", "hanviet") and not listen else ""},
                    "result": self.last_result if reveal else None,
                }
            top = sorted(self.players.values(), key=lambda p: (-p["score"], p["name"]))
            supporters = sorted((p for p in self.players.values() if p["diamonds"]),
                                key=lambda p: (-p["diamonds"], p["name"]))
            streakers = sorted((p for p in self.players.values() if p["streak"] >= 3),
                               key=lambda p: (-p["streak"], p["name"]))

            def goal(total, mark, g):
                return {"value": total - mark if g else total, "goal": g,
                        "progress": min(1.0, (total - mark) / g) if g else 0}

            nxt = self.queued[0] if self.queued else None
            out = {
                "phase": self.phase,
                "remaining": max(0.0, round(self.phase_end - now, 2)) if self.phase != "idle" else 0,
                "duration": {"question": self.q_duration, "reveal": cfg["reveal_s"],
                             "board": cfg["board_s"]}.get(self.phase, 0),
                "question": q,
                "round": self.rounds,
                "message": self.message,
                "top": [{**{k: p[k] for k in ("name", "score", "streak", "correct", "team", "avatar", "round_score")},
                         "crown": p["id"] == self.king_uid} for p in top[:10]],
                "round_info": {"no": self.round_no, "q": self.round_q, "len": cfg["round_len"]},
                "round_end": self.round_end,
                "recent_ans": list(self.recent_ans) if self.phase == "question" else [],
                "supporters": [{"name": p["name"], "gifts": p["gifts"], "diamonds": p["diamonds"]}
                               for p in supporters[:5]],
                "hot": [{"name": p["name"], "streak": p["streak"]} for p in streakers[:3]],
                "all_time": [],
                "weekly": [],
                "weekly_fans": [],
                "players": len(self.players),
                "likes": self.likes,
                "like_progress": (self.likes - self.like_mark) / cfg["like_goal"] if cfg["like_goal"] else 0,
                "like_goal": cfg["like_goal"],
                "goals": {"likes": goal(self.likes, self.like_mark, cfg["like_goal"]),
                          "diamonds": goal(self.diamonds, self.diamond_mark, cfg["gift_goal"]),
                          "shares": goal(self.shares, self.share_mark, cfg["share_goal"])},
                "double_next": self.double_next,
                "next_special": nxt,
                "teams": ({k: {"name": TEAMS[k], **v} for k, v in self.teams.items()} if cfg["teams"] else None),
                "vote": ({"options": [o[1] for o in VOTE_OPTS], "counts": list(self.vote["counts"])}
                         if self.vote is not None else None),
                "vote_mode": self.vote_mode,
                "viewers": self.viewers,
                "follows": self.follows,
                "feed": list(self.feed),
                "config": dict(cfg),
                "ai_down": self.ai_down,
                "bot": {"name": bot.NAME, "lines": list(self.bot_lines),
                        "mood": {"idle": "sleep", "board": "happy"}.get(self.phase, "idle")} if cfg["bot"] else None,
            }
            out.update(boards or {})
            return out


def save_items(rows: list[tuple[int, str, dict]], words: list[dict]):
    """Lưu nội dung AI. Ghi kèm chữ Hàn của từ để biết nếu bên HanSong đổi từ ở id đó."""
    kor = {w["id"]: w["korean"] for w in words}
    with db.tx() as c:
        for wid, kind, data in rows:
            if wid in kor:
                c.execute("INSERT INTO live_items(word_id,kind,korean,data) VALUES(?,?,?,?) "
                          "ON CONFLICT(word_id,kind) DO UPDATE SET korean=excluded.korean, data=excluded.data, "
                          "created_at=datetime('now')", (wid, kind, kor[wid], json.dumps(data, ensure_ascii=False)))


def load_items(words: list[dict]) -> dict:
    """{"cloze": {word_id: data}, "trans": {...}} chỉ gồm các từ còn tồn tại và chưa bị đổi chữ."""
    kor = {w["id"]: w["korean"] for w in words}
    out: dict = {"cloze": {}, "trans": {}}
    for r in db.q("SELECT word_id, kind, korean, data FROM live_items"):
        if kor.get(r["word_id"]) == r["korean"] and r["kind"] in out:
            out[r["kind"]][r["word_id"]] = json.loads(r["data"])
    return out


def item_counts() -> dict:
    return {r["kind"]: r["n"] for r in db.q("SELECT kind, COUNT(*) AS n FROM live_items GROUP BY kind")}


def all_time_top(n=5) -> list[dict]:
    return db.q("SELECT name, score, correct, answered, best_streak FROM live_players ORDER BY score DESC LIMIT ?",
                (n,))


def weekly_top(n=5, t: float | None = None) -> list[dict]:
    return db.q("SELECT name, score FROM live_weekly WHERE week=? AND score>0 ORDER BY score DESC LIMIT ?",
                (week_key(t or time.time()), n))


def weekly_fans(n=3, t: float | None = None) -> list[dict]:
    return db.q("SELECT name, diamonds FROM live_weekly WHERE week=? AND diamonds>0 ORDER BY diamonds DESC LIMIT ?",
                (week_key(t or time.time()), n))


def round_stats(n=20) -> dict:
    recent = db.q("SELECT at, word_id, mode, special, answered, correct, comments, viewers FROM live_rounds "
                  "ORDER BY id DESC LIMIT ?", (n,))
    by_kind = db.q("SELECT CASE WHEN special='' THEN mode ELSE special END AS kind, COUNT(*) AS rounds, "
                   "ROUND(AVG(answered),1) AS answered, ROUND(AVG(comments),1) AS comments, "
                   "ROUND(AVG(viewers),1) AS viewers, "
                   "ROUND(100.0*SUM(correct)/MAX(1,SUM(answered)),0) AS correct_pct "
                   "FROM (SELECT * FROM live_rounds ORDER BY id DESC LIMIT 500) GROUP BY kind ORDER BY rounds DESC")
    return {"recent": recent, "by_kind": by_kind}
