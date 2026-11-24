"""Bot linh vật "Hami" trên overlay: câu thoại theo sự kiện + nhận diện comment hỏi bot.

Engine (live.LiveGame) gọi `line(kind, **kw)` để lấy câu thoại ngẫu nhiên, rồi đẩy vào hàng `bot_lines` với một mood.
Overlay đổi mood thành animation: talk | happy | sad | wow | love | dance | hurry | wave | sleep.
Câu trả lời AI (người xem gõ "bot ..." / "hami ...") do main.py gọi ai.bot_reply ở luồng nền.
"""
import random
import re
import unicodedata

NAME = "Hami"

LINES = {
    "q": ["Câu mới tới rồi! Chọn A, B, C hay D nào~", "Câu này dễ ợt, đúng không cả nhà? 😆", "Nhanh tay là có thêm điểm đó nha!",
          "Tập trung nè, mình đọc đây~", "Ai trả lời đầu tiên được +5 điểm đó!"],
    "q_boss": ["👹 CÂU BOSS! x3 điểm, ít giờ hơn, cố lên!", "Boss xuất hiện rồi! Ai hạ được boss nào? 💪"],
    "q_listen": ["🎧 Câu nghe! Nghe kỹ rồi chọn nghĩa nha~", "Bịt mắt lại, chỉ nghe thôi nhé! 🎧"],
    "q_cloze": ["Điền vào chỗ trống nè, đọc gợi ý tiếng Việt nha!", "Từ nào vừa khít chỗ trống ta? 🧩"],
    "q_trans": ["Câu này nghĩa là gì nhỉ? Nghe mình đọc nè~", "Dịch câu nha cả nhà! 📝"],
    "q_final": ["🏁 Câu CHUNG KẾT vòng! x3 điểm, quyết định Vua vòng đó!", "Câu cuối của vòng rồi! Ai sẽ là Vua vòng đây? 👑"],
    "greet1": ["Chào {a}! Comment A/B/C/D chơi cùng Hami nha 👋", "Ơ {a} tới kìa! 안녕하세요~ Vào chơi đi nè 👋",
               "Xin chào {a}! Đoán nghĩa từ tiếng Hàn cùng mình nha 👋"],
    "greet2": ["Chào {a} và {b}! Vào chơi cùng Hami nha 👋", "{a} với {b} tới rồi kìa! 안녕하세요~ 👋"],
    "greetN": ["Chào {a}, {b} và {n} bạn nữa! Comment A/B/C/D để chơi nha 👋",
               "Đông vui quá! Chào {a}, {b} và {n} bạn mới nha 🥰"],
    "round_king": ["👑 {name} là Vua vòng {no} với {score} điểm! Chúc mừng nha!", "Vòng {no} kết thúc! Vương miện thuộc về {name} 👑🎉"],
    "round_none": ["Vòng {no} kết thúc! Vòng sau cả nhà cùng chơi nha 💪"],
    "q_hanviet": ["Âm Hán Việt của từ này là gì ta? 🈶", "Người Việt mình có lợi thế ở câu này đó!"],
    "q_sponsor": ["Câu này do {name} tài trợ! Cảm ơn nhiều nha 💎"],
    "hurry": ["Còn 5 giây! Chốt đi nào! ⏰", "Nhanh lên nhanh lên! 😱", "Sắp hết giờ rồi đó~"],
    "reveal_none": ["Chưa ai trả lời cả... comment A/B/C/D thử đi nè 🥺"],
    "reveal_zero": ["Ôi câu này khó quá ha 😵 Nhớ từ này nha!", "Không ai đúng luôn... lần sau cẩn thận nha 😢"],
    "reveal_low": ["Câu này hơi khó nhỉ, chỉ {pct}% đúng thôi 🤏", "Ghi nhớ từ này nha, câu sau gỡ lại!"],
    "reveal_mid": ["{pct}% cả phòng đúng, giỏi ghê! 👏", "{name} nhanh nhất câu này đó! ⚡"],
    "reveal_high": ["Cả phòng giỏi quá! {pct}% đúng luôn 🎉", "Dễ quá đúng không? {name} nhanh như chớp ⚡"],
    "streak": ["{name} đúng {n} câu liền! Đỉnh quá đi 🔥", "Ai cản được {name} đây?! 🔥 x{n}"],
    "streak_lost": ["Tiếc ghê {name} ơi, chuỗi {n} câu dừng rồi 😢", "Không sao {name}, làm lại chuỗi mới nha!"],
    "gift": ["Cảm ơn {name} nha 💖", "Yêu {name} quá đi 🥰", "{name} tặng quà kìa, cảm ơn bạn nhiều! 💕"],
    "gift_big": ["Wow {name} ơi!! Cảm ơn bạn nhiều lắm 💎✨", "{name} chơi lớn quá! Mình nhảy cảm ơn nè 💃"],
    "follow": ["Cảm ơn {name} đã follow! 🥰", "Chào mừng {name} vào nhà nha! 💕"],
    "share": ["Cảm ơn {name} đã share live! 🔁💖"],
    "join": ["Chào {name}! Comment A/B/C/D chơi cùng mình nha 👋", "Ơ {name} tới kìa! Vào chơi đi nè~ 👋",
             "Xin chào {name}! 안녕하세요~ 👋"],
    "goal": ["Đủ mốc rồi! Cả nhà tuyệt vời quá 🎉", "Yeahhh! Cảm ơn cả nhà nhiều lắm 💃"],
    "board": ["{name} đang dẫn đầu! Ai vượt được không nè? 🏆", "Top 1 hiện tại: {name}! 👑"],
    "board_vote": ["Bình chọn kiểu câu tiếp nè: comment 1, 2 hoặc 3!"],
    "team": ["Đội {team} đang dẫn trước! Đội kia cố lên! 🔴🔵"],
    # lời mời ủng hộ xen kẽ: chỉ nói sự thật, không hứa đổi quà lấy điểm/quyền lợi
    "support": ["Thích buổi học thì thả tim ❤️ và follow kênh nha!", "Cảm ơn cả nhà đã học cùng Hami 💕 Ủng hộ kênh để mình live đều hơn nha!",
                "Share live cho bạn bè cùng học tiếng Hàn nhé 🔁", "Thấy hay thì tặng Hami bông hồng nha, mình vui lắm 🌹"],
    # CHỈ dùng khi API AI thật sự hết tiền / key hỏng (main.py bắt AICreditError)
    "ai_broke": ["Ôi, tài khoản AI của Hami hết credit thật rồi 😭 Tạm thời mình chưa trả lời câu hỏi được, ủng hộ kênh để mình sớm được nạp lại nha 💖",
                 "Hami hết tiền gọi AI mất rồi 😢 Cả nhà vẫn chơi đoán từ bình thường nha, ủng hộ kênh giúp mình nạp lại với 🙏"],
    "ai_key": ["Hami đang mất kết nối AI 😵 Chờ chủ kênh sửa chút nha, mình vẫn chơi đoán từ được!"],
    "ai_off": ["@{name} Hami đang hết credit AI nên chưa trả lời được 😢 Chơi đoán từ tiếp với mình nha!",
               "@{name} AI của Hami tạm nghỉ vì hết credit, ủng hộ kênh để mình sớm trả lời lại nha 🙏"],
    "ai_back": ["Hami có AI trở lại rồi! Hỏi mình bằng \"bot ơi …\" nha 🎉"],
}
MOOD = {"q": "talk", "q_boss": "wow", "q_listen": "talk", "q_cloze": "talk", "q_trans": "talk", "q_hanviet": "talk",
        "q_sponsor": "love", "hurry": "hurry", "reveal_none": "sad", "reveal_zero": "sad", "reveal_low": "sad",
        "reveal_mid": "happy", "reveal_high": "dance", "streak": "wow", "streak_lost": "sad", "gift": "love",
        "gift_big": "dance", "follow": "love", "share": "love", "join": "wave", "goal": "dance", "board": "happy",
        "board_vote": "talk", "team": "happy", "support": "love", "ai_broke": "sad", "ai_key": "sad", "ai_off": "sad",
        "ai_back": "dance", "q_final": "wow",
        "greet1": "wave", "greet2": "wave", "greetN": "wave", "round_king": "dance", "round_none": "happy"}


def line(kind: str, **kw) -> tuple[str, str]:
    """(text, mood). Tên người xem được cắt ngắn để bong bóng không bị tràn."""
    kw = {k: (str(v)[:18] + "…" if k in ("name", "a", "b") and len(str(v)) > 19 else v) for k, v in kw.items()}
    return random.choice(LINES[kind]).format(**kw), MOOD[kind]


def _plain(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


_ASK_RE = re.compile(r"^\s*(?:@?bot|@?hami|b[ée] hami)(?:\s*(?:ơi|oi|ới))?[\s,:!?.]+(\S.{1,})$", re.I | re.S)


def parse_ask(text: str) -> str | None:
    """'bot ơi 사랑 nghĩa là gì' -> '사랑 nghĩa là gì'. Trả None nếu không phải câu hỏi bot."""
    m = _ASK_RE.match(unicodedata.normalize("NFC", text or ""))
    return m.group(1).strip()[:200] if m else None


def leaks(text: str, secrets: list[str]) -> bool:
    """Câu bot/câu hỏi có chứa đáp án câu đang hỏi không (so bỏ dấu, bỏ khoảng trắng)."""
    t = re.sub(r"\s", "", _plain(text))
    for s in secrets:
        k = re.sub(r"\s", "", _plain(s))
        if len(k) >= 2 and k in t:
            return True
    return False


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2190-\u21FF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+")


def speech_text(text: str) -> str:
    """Câu thoại -> chữ để đọc: bỏ emoji, '@Lan ...' thành 'Lan ơi, ...'."""
    t = _EMOJI.sub("", text or "")
    t = re.sub(r"^@(\S+)\s+", lambda m: f"{m.group(1)} ơi, ", t)
    t = t.replace("…", "...").replace("~", "")
    return re.sub(r"\s+", " ", t).strip()


def static_lines() -> list[str]:
    """Các câu không có chỗ điền tên/số: tạo giọng sẵn lúc khởi động để khi live phát ngay."""
    return [t for v in LINES.values() for t in v if "{" not in t]
