"""Chế độ TikTok LIVE "Săn Quái Chữ": cả phòng cùng đánh quái bằng cách comment A/B/C/D trả lời câu hỏi tiếng Hàn.

Vòng lặp chính:
  - Leo ải 1, 2, 3… mỗi ải 1 con quái. Cứ `boss_every` ải có 1 BOSS; hết boss thì sang vùng mới (đổi nền) và
    ải đầu vùng là điểm hồi sinh.
  - Mỗi câu = 1 lượt đánh. Ai trả lời đúng gây sát thương (= điểm cá nhân), người đúng đầu tiên được chí mạng.
    Sát thương chỉ tính lúc hiện đáp án: đang hỏi mà máu quái tụt là lộ ai đúng.
  - Có người trả lời mà dưới 50% đúng: quái phản đòn, cả phòng mất tim. Hết tim thì về điểm hồi sinh.
  - Quái có đặc tính (TRAITS) đổi kiểu câu/thời gian/máu. Hạ quái xong cả phòng chọn 1 trong 3 cửa = đặc tính quái sau.
  - Cấp độ + danh hiệu cá nhân tính từ tổng sát thương mọi thời đại (live_players.score).
  - Tim đủ mốc: câu sau x2 sát thương. Chia sẻ đủ mốc: hồi 1 tim cho cả phòng.
Quà tặng KHÔNG có tác dụng gì trong game (người dùng yêu cầu bỏ hẳn); chỉ ghi số kim cương vào DB để kiểm tra SDK.

Engine thuần (không phụ thuộc TikTok SDK). Sự kiện vào qua `handle(event)` dạng dict đã chuẩn hoá:
  {"type": "comment"|"gift"|"like"|"join"|"follow"|"share"|"audience", "user": {"id", "name"}, ...}
Đồng hồ được truyền vào để test được.
"""
import json
import math
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
    "question_s": 20,      # thời gian trả lời mỗi câu (= 1 lượt đánh)
    "reveal_s": 7,         # hiện đáp án + hoạt cảnh ra đòn (phát âm thanh 2 luồng)
    "clear_s": 12,         # màn hạ quái / thua (kèm bình chọn cửa)
    "hearts": 5,           # số tim chung của cả phòng
    "turns": 4,            # số câu ước tính để hạ 1 quái thường (máu quái tính theo số người đang chơi)
    "boss_every": 5,       # cứ N ải có 1 boss, cũng là độ dài 1 vùng / điểm hồi sinh. 0 = không có boss
    "like_goal": 300,      # đủ N tim -> câu kế tiếp x2 sát thương
    "share_goal": 10,      # đủ N lượt chia sẻ -> hồi 1 tim cho cả phòng
    "vote": 1,             # hạ quái xong: bình chọn 1 trong 3 cửa (đặc tính quái kế tiếp)
    "live_counts": 1,      # hiện số người chọn từng đáp án ngay trong lúc hỏi
    "safe": 1,             # dồn nội dung vào vùng an toàn, chừa chỗ cho giao diện TikTok (comment, ô nhập, tên host)
    "safe_top": 12,        # % chiều cao phía trên dành cho TikTok (tên host, số người xem)
    "safe_bottom": 62,     # nội dung overlay kết thúc ở % này; phía dưới là comment + ô nhập của TikTok
    "bot": 1,              # bot linh vật Hami
    "bot_ai": 1,           # người xem gõ "bot ..." để hỏi, AI trả lời
    "bot_voice": 1,        # Hami đọc to câu thoại bằng giọng dễ thương (OpenAI TTS, cần OpenAI key)
    "sfx": 1,              # hiệu ứng âm thanh trên overlay (đấm, chém, tích tắc…)
    "support_every": 12,   # cứ N câu Hami mời thả tim / follow / share 1 lần. 0 = tắt
    "read_wait_s": 8,      # câu mới: đồng hồ chờ overlay đọc đề + Hami nói xong, tối đa N giây. 0 = chạy ngay
    "source": "all",       # nguồn từ: all | today | due | hard | new | mastered
    "mode": "all",         # ko2vi | vi2ko | mix (2 kiểu trên) | cloze | trans | hanviet | all (trộn mọi kiểu đang có)
}
LIMITS = {"question_s": (8, 120), "reveal_s": (3, 30), "clear_s": (4, 40), "hearts": (1, 20), "turns": (1, 20),
          "boss_every": (0, 50), "like_goal": (0, 100000), "share_goal": (0, 10000), "vote": (0, 1),
          "live_counts": (0, 1), "safe": (0, 1), "safe_top": (0, 30), "safe_bottom": (40, 100), "bot": (0, 1),
          "bot_ai": (0, 1), "bot_voice": (0, 1), "support_every": (0, 100), "sfx": (0, 1), "read_wait_s": (0, 20)}
SOURCES = ("all", "today", "due", "hard", "new", "mastered")
MODES = ("ko2vi", "vi2ko", "mix", "cloze", "trans", "hanviet", "all")
KINDS = ("ko2vi", "vi2ko", "cloze", "trans", "hanviet")   # các kiểu câu thật sự
BLANK = "＿＿＿"

# ---------------------------------------------------------------- quái, vùng, cấp độ
TRAITS = {
    "fast": {"icon": "⚡", "name": "Nhanh nhẹn", "desc": "ít thời gian hơn"},
    "stealth": {"icon": "👻", "name": "Tàng hình", "desc": "chỉ nghe, không thấy chữ"},
    "armor": {"icon": "🛡", "name": "Giáp dày", "desc": "máu x1.5"},
    "mirror": {"icon": "🪞", "name": "Đảo ngược", "desc": "hỏi Việt → Hàn"},
    "heal": {"icon": "💚", "name": "Tự hồi máu", "desc": "hồi máu khi bị đánh trượt"},
    "rage": {"icon": "🔥", "name": "Cuồng nộ", "desc": "phản đòn mất 2 tim"},
}
DOOR_TRAITS = ("fast", "stealth", "armor", "mirror", "heal")
FAST_MULT = 0.65
BOSS_HP = 2.0         # boss nhiều máu gấp N quái thường
ZONES = (("forest", "Rừng Từ Vựng"), ("desert", "Sa Mạc Ngữ Pháp"), ("castle", "Lâu Đài Kính Ngữ"),
         ("talltrees", "Rừng Cổ Thụ"))
MON_KIND = ("Quái", "Yêu tinh", "Quỷ con", "Ma")
MON_ADJ = ("Quên Từ", "Sai Chính Tả", "Lười Học", "Nói Ngọng", "Ham Ngủ", "Mắt Lồi", "Cáu Kỉnh", "Ăn Vụng",
           "Răng Sún", "Lắm Mồm", "Đãng Trí", "Phát Âm Sai", "Bỏ Bài", "Ngủ Gật")
BOSS_NAMES = ("Đại Vương Quên Từ", "Chúa Tể Ngữ Pháp", "Vua Đãng Trí", "Trùm Phát Âm Sai", "Bạo Chúa Kính Ngữ",
              "Ma Vương Bỏ Bài")
DMG_PER_PLAYER = 11    # sát thương trung bình 1 người/câu (≈60% đúng × ~18 điểm), dùng để tính máu quái
TITLES = ((20, "👑", "Huyền thoại"), (15, "⭐", "Anh hùng"), (10, "🔮", "Pháp sư"), (6, "🛡", "Hiệp sĩ"),
          (3, "🗡", "Kiếm sĩ"), (1, "🌱", "Tân binh"))


def level_of(total: int) -> int:
    """Cấp độ từ tổng sát thương mọi thời đại: 40 → cấp 2, 160 → 3, 360 → 4, 640 → 5…"""
    return 1 + int(math.sqrt(max(0, total) / 40))


def title_of(lv: int) -> tuple[str, str]:
    return next((icon, name) for m, icon, name in TITLES if lv >= m)


def clean_config(raw: dict, base: dict | None = None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg.update({k: v for k, v in (base or {}).items() if k in DEFAULT_CONFIG})
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
    return cfg


def week_key(t: float) -> str:
    return time.strftime("%G-W%V", time.localtime(t))


# ---------------------------------------------------------------- answer parsing
_LETTER_RE = re.compile(r"^(?:đáp án|dap an|đáp|chọn|chon|câu|cau)?\s*([a-d1-4])\s*[\.\!\)\s]*$", re.I)
_VOTE_RE = re.compile(r"^(?:cua|so|chon|vote|#)?\s*([1-3])\s*[\.\!\s]*$")


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
    return norm_vi(text) in ("điểm", "diem", "top", "hạng", "hang", "điểm của tôi", "cấp", "cap", "level")


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
        self.phase = "idle"          # idle | question | reveal | clear (hạ quái) | fail (cả phòng bị hạ)
        self.phase_end = 0.0
        self.read_until = 0.0     # câu hỏi: trước mốc này đồng hồ đứng yên (đang đọc đề)
        self.qid = 0
        self.q: dict | None = None
        self.q_duration = 0
        self.q_comments = 0          # số comment nhận được trong lúc hỏi câu này
        self.special: str | None = None       # listen (quái tàng hình) | None
        self.answers: dict[str, dict] = {}    # user_id -> {idx, at, correct, points, crit}
        self.double = False                   # câu hiện tại x2 sát thương (mốc tim)
        self.double_next = False
        self.rounds = 0
        self.recent: deque = deque(maxlen=40)
        self.players: dict[str, dict] = {}    # người chơi trong phiên live
        # --- săn quái
        self.floor = 1
        self.monster: dict | None = None
        self.pending: int | None = None       # ải sẽ sinh quái ở câu kế tiếp (sau khi hạ quái / thua)
        self.refill = False                   # câu kế tiếp hồi đầy tim (sau khi thua)
        self.hearts = DEFAULT_CONFIG["hearts"]
        self.mon_dmg: dict[str, int] = {}     # sát thương từng người lên quái hiện tại
        self.after: str | None = None         # sau màn đáp án: clear | fail | None
        self.outcome: dict | None = None      # dữ liệu màn hạ quái / thua
        self.next_trait: str | None = None    # kết quả bình chọn cửa
        self.force_boss = False               # admin gọi boss cho quái kế tiếp
        self.force_trait: str | None = None   # admin chọn đặc tính quái kế tiếp (thắng kết quả bình chọn)
        self.active: deque = deque(maxlen=3)  # tập người trả lời ở 3 câu gần nhất -> tính máu quái
        self.kills = 0
        self.best_floor = 0                   # ải cao nhất từng hạ (kỷ lục của kênh)
        self.king_uid: str | None = None      # MVP con quái vừa hạ: đội vương miện
        self.vote: dict | None = None         # đang mở bình chọn cửa: {"doors": [...], "counts", "voters"}
        # --- tương tác
        self.feed: deque = deque(maxlen=12)
        self.feed_seq = 0
        self.likes = 0
        self.like_mark = 0
        self.shares = 0
        self.share_mark = 0
        self.diamonds = 0
        self.follows = 0
        self.viewers = 0
        self.last_join = 0.0
        self.last_result: dict | None = None
        self.message = ""
        self._saved: dict[str, dict] = {}     # phần điểm đã ghi vào DB, để chỉ cộng phần chênh lệch
        self.bot_lines: deque = deque(maxlen=8)   # câu thoại của bot cho overlay: {seq, text, mood, at}
        self.bot_seq = 0
        self.bot_last = -1e9
        self.hurried = False
        self.bot_asks: deque = deque(maxlen=3)   # câu người xem hỏi bot, main.py lấy ra gọi AI
        self.bot_cool: dict[str, float] = {}     # user_id -> lần hỏi bot gần nhất
        self.bot_hold: list[dict] = []           # câu AI trả lời có lộ đáp án: giữ lại tới lúc hiện đáp án
        self.ai_down = ""                        # "" | credit | key: API AI hỏng thật (main.py báo vào)
        self.greet_buf: list[dict] = []          # người mới vào phòng chờ được Hami chào (gom nhóm)
        self.greet_at = -1e9
        self.leader: str | None = None   # top 1 phiên này (Hami báo khi đổi ngôi)
        self.leader_said = 0
        self.recent_ans: deque = deque(maxlen=6)   # dải "vừa ra đòn" trên overlay
        self.ai_off_at = -1e9
        if persist:
            try:
                self.best_floor = int(db.get_conf("best_floor", 0) or 0)
            except Exception:
                self.best_floor = 0

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
            base = 0
            if self.persist:
                try:
                    row = db.q1("SELECT score FROM live_players WHERE user_id=?", (uid,))
                    base = int(row["score"]) if row else 0
                except Exception:
                    base = 0
            p = self.players[uid] = {"id": uid, "name": user.get("name") or uid, "score": 0, "correct": 0,
                                     "answered": 0, "streak": 0, "best_streak": 0, "gifts": 0, "diamonds": 0,
                                     "avatar": None, "base": base, "level": level_of(base)}
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
        """(đạt mốc?, mark mới). Dùng chung cho tim, chia sẻ."""
        if goal and total - mark >= goal:
            return True, total - (total - mark) % goal
        return False, mark

    def _every(self) -> int:
        """Độ dài 1 vùng (số ải). boss_every=0 vẫn đổi vùng mỗi 5 ải."""
        return self.cfg["boss_every"] or 5

    def _checkpoint(self, floor: int) -> int:
        return (floor - 1) // self._every() * self._every() + 1

    def _is_boss_floor(self, floor: int) -> bool:
        return bool(self.cfg["boss_every"]) and floor % self.cfg["boss_every"] == 0

    def _brief(self, p: dict, **extra) -> dict:
        icon, title = title_of(p["level"])
        return {"name": p["name"], "avatar": p["avatar"], "level": p["level"], "title": title, "icon": icon, **extra}

    # -------------------------------------------------------- control
    def configure(self, raw: dict):
        with self.lock:
            self.cfg = clean_config(raw, self.cfg)
            self.hearts = min(self.hearts, self.cfg["hearts"])

    def start(self):
        with self.lock:
            if self.phase == "idle":
                if self.monster is None:
                    self.hearts = self.cfg["hearts"]
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
            elif self.phase == "reveal":
                self._after_reveal()
            else:
                self._next_question()

    def queue(self, kind: str) -> bool:
        """Admin tạo cao trào: boss (quái kế tiếp là boss) | double (câu sau x2) | heart (+1 tim)
        | một đặc tính trong DOOR_TRAITS (quái kế tiếp mang đặc tính đó, vd. stealth = câu nghe)."""
        with self.lock:
            if kind in DOOR_TRAITS:
                self.force_trait = kind
                t = TRAITS[kind]
                self._push("system", f"{t['icon']} Quái kế tiếp: {t['name']} ({t['desc']})")
            elif kind == "double":
                self.double_next = True
                self._push("system", "⚡ Câu tiếp theo x2 sát thương!", alert=True)
            elif kind == "boss":
                self.force_boss = True
                self._push("system", "👹 Con quái kế tiếp là BOSS!", alert=True)
            elif kind == "heart":
                self.hearts = min(self.cfg["hearts"], self.hearts + 1)
                self._push("system", "💖 Hồi 1 tim cho cả phòng!", alert=True)
            else:
                return False
            return True

    def reset_scores(self):
        """Làm lại từ ải 1, xoá điểm phiên (điểm mọi thời đại + kỷ lục vẫn giữ). Dừng game, bấm Bắt đầu để chơi lại."""
        with self.lock:
            self.players.clear()
            self._saved.clear()
            self.leader, self.leader_said = None, 0
            self.rounds = 0
            self.likes = self.like_mark = 0
            self.shares = self.share_mark = 0
            self.diamonds = self.follows = self.kills = 0
            self.double_next = self.double = self.force_boss = False
            self.force_trait = None
            self.floor, self.monster, self.pending, self.refill = 1, None, None, False
            self.hearts = self.cfg["hearts"]
            self.mon_dmg, self.after, self.outcome, self.next_trait, self.king_uid = {}, None, None, None, None
            self.active.clear()
            self.recent_ans.clear()
            self.phase, self.q, self.vote = "idle", None, None
            self.message = "Đã làm mới: bắt đầu lại từ ải 1"
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

    # -------------------------------------------------------- quái
    def _spawn(self, floor: int):
        boss = self.force_boss or self._is_boss_floor(floor)
        self.force_boss = False
        if boss:
            traits = ["rage", random.choice(DOOR_TRAITS)]
        elif self.force_trait or self.next_trait:
            traits = [self.force_trait or self.next_trait]
        elif floor == 1:
            traits = []
        else:
            traits = [random.choice(DOOR_TRAITS)]
        self.next_trait = self.force_trait = None
        active = len(set().union(*self.active)) if self.active else 0
        hp = max(30, max(1, active) * DMG_PER_PLAYER * self.cfg["turns"] * (1 + 0.04 * (floor - 1)))
        if "armor" in traits:
            hp *= 1.5
        if boss:
            hp *= BOSS_HP
        hp = int(round(hp / 10)) * 10
        zone_id, zone_name = ZONES[(floor - 1) // self._every() % len(ZONES)]
        name = random.choice(BOSS_NAMES) if boss else f"{random.choice(MON_KIND)} {random.choice(MON_ADJ)}"
        self.floor = floor
        self.monster = {"floor": floor, "name": name, "boss": boss, "traits": traits, "hp": hp, "max_hp": hp,
                        "seed": random.randrange(1 << 30), "zone": zone_id, "zone_name": zone_name}
        self.mon_dmg = {}
        self._bot("spawn_boss" if boss else "spawn", mon=name, floor=floor)

    def _close_vote(self):
        v, self.vote = self.vote, None
        if not v:
            return
        total = sum(v["counts"])
        best = max(v["counts"])
        i = random.choice([j for j, c in enumerate(v["counts"]) if c == best])
        self.next_trait = v["doors"][i]
        if total and not self.force_trait:      # admin đã chọn đặc tính thì không báo kết quả bình chọn
            t = TRAITS[self.next_trait]
            self._push("vote", f"🚪 Cả phòng chọn cửa {i + 1}: {t['icon']} {t['name']} ({v['counts'][i]}/{total} phiếu)",
                       alert=True)

    def _next_question(self):
        self._close_vote()
        if self.refill:
            self.refill = False
            self.hearts = self.cfg["hearts"]
        spawned = False
        if self.monster is None or self.pending:
            self._spawn(self.pending or self.floor)
            self.pending = None
            spawned = True
        m = self.monster
        special = "listen" if "stealth" in m["traits"] else None
        pcfg = dict(self.cfg)
        if special:
            pcfg["mode"] = "ko2vi"          # quái tàng hình: phát tiếng Hàn, chọn nghĩa Việt
        elif "mirror" in m["traits"]:
            pcfg["mode"] = "vi2ko"
        q = self.picker(set(self.recent), pcfg)
        if not q:
            self.phase, self.q = "idle", None
            self.message = "Cần ít nhất 2 từ có âm thanh trong nguồn từ đã chọn"
            return
        self.qid += 1
        self.q = q
        self.special = special
        self.recent_ans.clear()
        self.recent.append(q["word_id"])
        self.answers = {}
        self.q_comments = 0
        self.double, self.double_next = self.double_next, False
        self.last_result = None
        self.after = None
        self.outcome = None
        self.message = ""
        self.phase = "question"
        dur = self.cfg["question_s"]
        if "fast" in m["traits"]:
            dur = max(8, round(dur * FAST_MULT))
        self.q_duration = dur
        # chờ overlay đọc đề + Hami nói xong (overlay gọi ready()); quá read_wait_s thì đồng hồ tự chạy
        self.read_until = self.clock() + self.cfg["read_wait_s"]
        self.phase_end = self.read_until + dur
        self.hurried = False
        if spawned:
            return                          # vừa nói câu "quái xuất hiện"
        if special:
            self._bot("q_listen")
        elif q["mode"] in ("cloze", "trans", "hanviet"):
            self._bot("q_" + q["mode"])
        else:
            self._bot("q", mon=m["name"])

    def ready(self, qid: int) -> bool:
        """Overlay báo đã đọc đề xong: bắt đầu đếm ngược ngay. Gọi trùng / câu cũ thì bỏ qua."""
        with self.lock:
            now = self.clock()
            if self.phase != "question" or qid != self.qid or now >= self.read_until:
                return False
            self.read_until = now
            self.phase_end = now + self.q_duration
            return True

    def _reveal(self):
        q, m = self.q, self.monster
        counts = [0] * len(q["options"])
        for a in self.answers.values():
            counts[a["idx"]] += 1
        winners = sorted((a for a in self.answers.values() if a["correct"]), key=lambda a: a["at"])
        hp_before = m["hp"]
        hits, killer, leveled = [], None, []
        for a in winners:
            p = self.players[a["uid"]]
            if m["hp"] > 0 and killer is None and m["hp"] - a["points"] <= 0:
                killer = p
            m["hp"] = max(0, m["hp"] - a["points"])
            self.mon_dmg[a["uid"]] = self.mon_dmg.get(a["uid"], 0) + a["points"]
            hits.append(self._brief(p, dmg=a["points"], crit=a["crit"]))
            lv = level_of(p["base"] + p["score"])
            if lv > p["level"]:
                leveled.append((p, title_of(lv) != title_of(p["level"])))
                p["level"] = lv
        total = len(self.answers)
        killed = m["hp"] <= 0
        attack, healed = None, 0
        if total and not killed and len(winners) / total < 0.5:
            lose = 2 if "rage" in m["traits"] else 1
            self.hearts = max(0, self.hearts - lose)
            attack = {"hearts": lose}
            if "heal" in m["traits"]:
                healed = min(m["max_hp"] - m["hp"], round(m["max_hp"] * 0.15))
                m["hp"] += healed
        if total:
            self.active.append(set(self.answers))
        self.last_result = {
            "counts": counts, "total": total, "correct": len(winners),
            "hits": hits[:8], "more": max(0, len(hits) - 8), "dmg": sum(h["dmg"] for h in hits),
            "hp_before": hp_before, "hp_after": m["hp"], "killed": killed, "attack": attack, "healed": healed,
            "last_hit": self._brief(killer) if killer else None,
        }
        self.rounds += 1
        self.phase = "reveal"
        self.phase_end = self.clock() + self.cfg["reveal_s"]
        if self.persist:
            if self.answers:
                self._save([self.players[u] for u in self.answers])
            self._log_round(len(winners))
        for p, new_title in leveled:
            icon, title = title_of(p["level"])
            self._push("level", f"⬆️ {p['name']} lên cấp {p['level']}" + (f" · {icon} {title}!" if new_title else ""),
                       alert=new_title, tier=2)
        if killed:
            self.after = "clear"
            self._kill(killer)
        elif self.hearts <= 0:
            self.after = "fail"
            self._fail()
        elif not total:
            self._bot("reveal_none")
        else:
            if hits:                        # khen người đúng, gọi tên (người đầu tiên = nhanh nhất, chí mạng)
                names = [h["name"] for h in hits]
                if len(names) == 1:
                    self._bot("cheer1_crit" if random.random() < .5 else "cheer1", a=names[0])
                elif len(names) == 2:
                    self._bot("cheer2", a=names[0], b=names[1])
                else:
                    self._bot("cheerN", a=names[0], b=names[1], n=len(winners) - 2, total=len(winners))
            if attack:
                self._bot("hit_room", lose=attack["hearts"], hearts=self.hearts)
            if leveled:
                p = leveled[-1][0]
                self._bot("levelup", name=p["name"], lv=p["level"], title=title_of(p["level"])[1])
            else:
                self._announce_top()
        for line in self.bot_hold:
            self._bot_raw(line["text"], line["mood"])
        self.bot_hold = []
        every = self.cfg["support_every"]
        if every and self.rounds % every == 0 and not killed:
            self._bot("support")

    TOP_EVERY = 5   # không đổi top 1 thì cứ N câu nhắc lại người đang dẫn đầu

    def _announce_top(self):
        """Báo khi có người vượt lên top 1 phiên này, hoặc định kỳ nhắc ai đang dẫn đầu."""
        top = sorted((p for p in self.players.values() if p["score"] > 0), key=lambda p: (-p["score"], p["name"]))
        if not top:
            return
        lead = top[0]
        if lead["id"] != self.leader:
            changed = self.leader is not None
            self.leader, self.leader_said = lead["id"], self.rounds
            if changed:
                self._bot("top_new", name=lead["name"], score=lead["score"])
                return
        if self.rounds - self.leader_said >= self.TOP_EVERY:
            self.leader_said = self.rounds
            if len(top) > 1 and random.random() < .5:
                self._bot("top_now2", name=lead["name"], second=top[1]["name"])
            else:
                self._bot("top_now", name=lead["name"], score=lead["score"])

    def _mvp(self) -> list[dict]:
        order = sorted(self.mon_dmg.items(), key=lambda kv: (-kv[1], self.players[kv[0]]["name"]))
        return [self._brief(self.players[uid], dmg=d, uid=uid) for uid, d in order[:3]]

    def _kill(self, killer: dict | None):
        m = self.monster
        mvp = self._mvp()
        self.king_uid = mvp[0].pop("uid") if mvp else None
        for x in mvp:
            x.pop("uid", None)
        self.kills += 1
        record = m["floor"] > self.best_floor
        if record:
            self.best_floor = m["floor"]
            if self.persist:
                try:
                    db.set_conf("best_floor", self.best_floor)
                except Exception as e:
                    self._push("system", f"Lỗi lưu kỷ lục: {e}")
        nxt = m["floor"] + 1
        self.pending = nxt
        self.outcome = {"kind": "clear", "floor": m["floor"], "name": m["name"], "boss": m["boss"], "mvp": mvp,
                        "last_hit": self._brief(killer) if killer else None, "record": record,
                        "next_floor": nxt, "next_boss": self._is_boss_floor(nxt) or self.force_boss,
                        "new_zone": (nxt - 1) % self._every() == 0}
        self._push("clear", f"{'👑' if m['boss'] else '⚔️'} Đã hạ {m['name']}! Qua ải {m['floor']}", alert=True,
                   tier=3 if m["boss"] else 2)
        if record and m["floor"] > 1:
            self._push("record", f"🏆 KỶ LỤC MỚI: ải {m['floor']}!", alert=True, tier=3)
            self._bot("record", floor=m["floor"])
        elif killer:
            self._bot("kill_boss" if m["boss"] else "kill", mon=m["name"], name=killer["name"],
                      mvp=mvp[0]["name"] if mvp else killer["name"])

    def _fail(self):
        m = self.monster
        mvp = self._mvp()
        for x in mvp:
            x.pop("uid", None)
        back = self._checkpoint(m["floor"])
        self.pending = back
        self.refill = True
        self.outcome = {"kind": "fail", "floor": m["floor"], "name": m["name"], "boss": m["boss"], "mvp": mvp,
                        "back_to": back}
        self._push("fail", f"💀 Cả phòng bị {m['name']} hạ gục! Quay về ải {back}", alert=True, tier=2)
        self._bot("fail", mon=m["name"], back=back)

    def _after_reveal(self):
        if self.after == "clear":
            self.phase = "clear"
            self.phase_end = self.clock() + self.cfg["clear_s"]
            nxt = self.outcome["next_floor"]
            if self.cfg["vote"] and not self.outcome["next_boss"]:
                self.vote = {"doors": random.sample(DOOR_TRAITS, 3), "counts": [0, 0, 0], "voters": set()}
                self._bot("door_vote", floor=nxt)
        elif self.after == "fail":
            self.phase = "fail"
            self.phase_end = self.clock() + max(4, self.cfg["clear_s"] - 4)
        else:
            self._next_question()

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
                self._after_reveal()
            elif self.phase in ("clear", "fail"):
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
                    self._push("join", f"👋 Chào {name}! Comment A/B/C/D để đánh quái")
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
            icon, title = title_of(p["level"])
            self._push("score", f"📊 {p['name']}: {p['score']} sát thương · hạng {self._rank(p['id'])} · "
                                f"cấp {p['level']} {icon} {title}")
            return
        ask = bot.parse_ask(text)
        if ask is not None and self.cfg["bot"]:
            uid = str(user["id"])
            now = self.clock()
            if self.cfg["bot_ai"] and now - self.bot_cool.get(uid, -1e9) >= 40:   # mỗi người hỏi tối đa 1 lần / 40 giây
                self.bot_cool[uid] = now
                self.bot_asks.append({"uid": uid, "name": (user.get("name") or uid)[:40], "text": ask})
            return
        if self.phase == "clear" and self.vote is not None:
            v = parse_vote(text)
            uid = str(user["id"])
            if v is not None and uid not in self.vote["voters"]:
                self._player(user)
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
        points, crit = 0, False
        p["answered"] += 1
        if ok:
            crit = not any(a["correct"] for a in self.answers.values())
            remain = min(1.0, max(0.0, self.phase_end - now) / (self.q_duration or self.cfg["question_s"]))
            p["streak"] += 1
            p["best_streak"] = max(p["best_streak"], p["streak"])
            points = 10 + round(10 * remain) + (5 if crit else 0) + (min(10, p["streak"]) if p["streak"] >= 3 else 0)
            if self.double:
                points *= 2
            p["score"] += points
            p["correct"] += 1
            if p["streak"] >= 5 and p["streak"] % 5 == 0:
                self._push("streak", f"🔥 {p['name']} đúng liên tiếp {p['streak']} câu!", alert=True, tier=2)
                self._bot("streak", name=p["name"], n=p["streak"])
        else:
            if p["streak"] >= 5:
                self._push("streak", f"💔 {p['name']} mất chuỗi {p['streak']} câu")
                self._bot("streak_lost", name=p["name"], n=p["streak"])
            p["streak"] = 0
        self.answers[uid] = {"uid": uid, "idx": idx, "at": now, "correct": ok, "points": points, "crit": crit}
        self.recent_ans.append({"name": p["name"], "avatar": p["avatar"], "letter": LETTERS[idx],
                                "level": p["level"], "seq": len(self.answers)})

    def _gift(self, user: dict, ev: dict):
        """Quà không có tác dụng gì trong game: chỉ ghi nhận số kim cương (để kiểm tra SDK có gửi giá quà không)."""
        p = self._player(user)
        n = max(1, int(ev.get("count") or 1))
        unit = max(0, int(ev.get("diamonds") or 0))
        total = max(n, unit * n)      # không rõ giá quà thì coi mỗi món 1 kim cương
        p["gifts"] += n
        p["diamonds"] += total
        self.diamonds += total
        if self.persist:
            self._save([p])

    def _like(self, n: int):
        self.likes += max(1, min(100000, n))
        hit, self.like_mark = self._goal(self.likes, self.like_mark, self.cfg["like_goal"])
        if hit:
            self.double_next = True
            self._push("like", f"❤️ Đủ {self.cfg['like_goal']} tim! Câu tiếp theo x2 sát thương", alert=True, tier=2)
            self._bot("like_goal")

    def _share(self, name: str):
        self.shares += 1
        self._push("share", f"🔁 {name} đã chia sẻ live")
        self._bot("share", force=False, name=name)
        hit, self.share_mark = self._goal(self.shares, self.share_mark, self.cfg["share_goal"])
        if hit:
            if self.hearts < self.cfg["hearts"]:
                self.hearts += 1
                self._push("goal", f"🔁 Đủ {self.cfg['share_goal']} lượt chia sẻ! Hồi 1 tim 💖", alert=True, tier=2)
            else:
                self.double_next = True
                self._push("goal", f"🔁 Đủ {self.cfg['share_goal']} lượt chia sẻ! Tim đầy nên câu sau x2 sát thương",
                           alert=True, tier=2)
            self._bot("share_goal")

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
        special = "boss" if self.monster and self.monster["boss"] else (self.special or "")
        try:
            with db.tx() as c:
                c.execute("INSERT INTO live_rounds(word_id,mode,special,answered,correct,comments,viewers) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (self.q["word_id"], self.q["mode"], special, len(self.answers), correct,
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
                    "double": self.double,
                    "mult": 2 if self.double else 1,
                    "word_id": self.q["word_id"],
                    "answered": len(self.answers),
                    "counts": counts if (reveal or cfg["live_counts"]) else None,
                    "answer": self.q["answer"] if reveal else None,
                    "hint": self.q.get("hint", "") if not listen else "",
                    "audio_q": self.q.get("audio_q", "ko_word" if self.q["prompt_lang"] == "ko" else "vi_word"),
                    # hiện đáp án: đọc ngôn ngữ còn lại (không dùng bản `mix` 2 tai, nghe như bị lặp)
                    "audio_reveal": self.q.get("audio_reveal", "vi_word" if self.q["prompt_lang"] == "ko" else "ko_word"),
                    "word": self.q["word"] if reveal else
                    {"romanization": self.q["word"]["romanization"]
                     if self.q["mode"] in ("ko2vi", "hanviet") and not listen else ""},
                    "result": self.last_result if reveal else None,
                }
            m = self.monster
            monster = None
            if m:
                monster = {**{k: m[k] for k in ("floor", "name", "boss", "hp", "max_hp", "seed", "zone", "zone_name")},
                           "traits": [{"id": t, **TRAITS[t]} for t in m["traits"]]}
                if self.phase == "reveal" and self.last_result:
                    monster["hp"] = self.last_result["hp_after"]
            top = sorted(self.players.values(), key=lambda p: (-p["score"], p["name"]))

            def goal(total, mark, g):
                return {"value": total - mark if g else total, "goal": g,
                        "progress": min(1.0, (total - mark) / g) if g else 0}

            zone_floor = self.floor if not m else m["floor"]
            out = {
                "phase": self.phase,
                # đang đọc đề: đồng hồ đứng yên ở mức đầy
                "remaining": (0 if self.phase == "idle" else
                              min(self.q_duration, max(0.0, round(self.phase_end - now, 2))) if self.phase == "question"
                              else max(0.0, round(self.phase_end - now, 2))),
                "reading": self.phase == "question" and now < self.read_until,
                "duration": {"question": self.q_duration, "reveal": cfg["reveal_s"], "clear": cfg["clear_s"],
                             "fail": max(4, cfg["clear_s"] - 4)}.get(self.phase, 0),
                "question": q,
                "monster": monster,
                "room": {"hearts": self.hearts, "max_hearts": cfg["hearts"], "floor": zone_floor,
                         "checkpoint": self._checkpoint(zone_floor), "best_floor": self.best_floor,
                         "kills": self.kills, "zone_len": self._every()},
                "outcome": self.outcome if self.phase in ("clear", "fail") else None,
                "round": self.rounds,
                "message": self.message,
                "top": [{**self._brief(p), "score": p["score"], "streak": p["streak"],
                         "crown": p["id"] == self.king_uid} for p in top[:10]],
                "recent_ans": list(self.recent_ans) if self.phase == "question" else [],
                "hot": [{"name": p["name"], "streak": p["streak"]}
                        for p in sorted((p for p in self.players.values() if p["streak"] >= 3),
                                        key=lambda p: (-p["streak"], p["name"]))[:3]],
                "weekly": [],
                "players": len(self.players),
                "likes": self.likes,
                "goals": {"likes": goal(self.likes, self.like_mark, cfg["like_goal"]),
                          "shares": goal(self.shares, self.share_mark, cfg["share_goal"])},
                "double_next": self.double_next,
                "force_boss": self.force_boss,
                "vote": ({"doors": [{"id": d, **TRAITS[d]} for d in self.vote["doors"]],
                          "counts": list(self.vote["counts"])} if self.vote is not None else None),
                "viewers": self.viewers,
                "follows": self.follows,
                "feed": list(self.feed),
                "config": dict(cfg),
                "ai_down": self.ai_down,
                "bot": {"name": bot.NAME, "lines": list(self.bot_lines),
                        "mood": {"idle": "sleep", "clear": "dance", "fail": "sad"}.get(self.phase, "idle")}
                if cfg["bot"] else None,
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


def round_stats(n=20) -> dict:
    recent = db.q("SELECT at, word_id, mode, special, answered, correct, comments, viewers FROM live_rounds "
                  "ORDER BY id DESC LIMIT ?", (n,))
    by_kind = db.q("SELECT CASE WHEN special='' THEN mode ELSE special END AS kind, COUNT(*) AS rounds, "
                   "ROUND(AVG(answered),1) AS answered, ROUND(AVG(comments),1) AS comments, "
                   "ROUND(AVG(viewers),1) AS viewers, "
                   "ROUND(100.0*SUM(correct)/MAX(1,SUM(answered)),0) AS correct_pct "
                   "FROM (SELECT * FROM live_rounds ORDER BY id DESC LIMIT 500) GROUP BY kind ORDER BY rounds DESC")
    return {"recent": recent, "by_kind": by_kind}
