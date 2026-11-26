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
    "q": ["Ra đòn đi cả nhà! Chọn A, B, C hay D nào ⚔️", "Đúng là đánh trúng {mon} đó, nhanh tay nha!",
          "Trả lời nhanh = đòn mạnh hơn! 💪", "Ai trả lời đúng đầu tiên được CHÍ MẠNG đó ⚡", "Tập trung nè, mình đọc đây~"],
    "q_listen": ["👻 Quái tàng hình! Chỉ nghe thôi, chọn nghĩa nha~", "Bịt mắt lại, nghe kỹ rồi đánh nhé! 🎧"],
    "q_cloze": ["Điền vào chỗ trống để ra đòn nè! 🧩", "Từ nào vừa khít chỗ trống ta? 🧩"],
    "q_trans": ["Câu này nghĩa là gì nhỉ? Nghe mình đọc nè~", "Dịch câu để chém quái nha cả nhà! 📝"],
    "q_hanviet": ["Âm Hán Việt của từ này là gì ta? 🈶", "Người Việt mình có lợi thế ở câu này đó!"],
    "spawn": ["{mon} xuất hiện ở ải {floor}! Đánh nó nào ⚔️", "Ải {floor}: {mon} tới rồi! Comment A/B/C/D để ra đòn!",
              "Cẩn thận, {mon} đó! Cả nhà cùng đánh nha 💪"],
    "spawn_boss": ["👹 BOSS {mon}! Nó đánh mất 2 tim đó, tập trung nha!", "Ải {floor} là BOSS {mon}! Cả phòng hợp sức nào 🔥"],
    "greet1": ["Chào {a}! Comment A/B/C/D đánh quái cùng Hami nha 👋", "Ơ {a} tới kìa! 안녕하세요~ Vào đánh quái đi nè 👋",
               "Xin chào {a}! Trả lời đúng là gây sát thương đó 👋"],
    "greet2": ["Chào {a} và {b}! Vào đánh quái cùng Hami nha 👋", "{a} với {b} tới rồi kìa! 안녕하세요~ 👋"],
    "greetN": ["Chào {a}, {b} và {n} bạn nữa! Comment A/B/C/D để đánh quái nha 👋",
               "Đông vui quá! Chào {a}, {b} và {n} bạn mới nha 🥰"],
    "hurry": ["Còn 5 giây! Chốt đi nào! ⏰", "Nhanh lên nhanh lên! 😱", "Sắp hết giờ rồi đó~"],
    "reveal_none": ["Chưa ai ra đòn cả... comment A/B/C/D để đánh quái nha 🥺"],
    "reveal_hit": ["Trúng {dmg} sát thương! Quái còn {hp} máu 💪", "Đánh hay lắm! Cả phòng gây {dmg} sát thương ⚔️"],
    "reveal_crit": ["{name} chí mạng! Nhanh như chớp ⚡", "Đòn đầu tiên của {name} đau lắm đó ⚡"],
    # khen người trả lời đúng (gọi tên); {crit} = người nhanh nhất
    "cheer1": ["{a} đúng rồi! Giỏi quá đi 👏", "Chuẩn luôn {a} ơi! Đòn đẹp lắm ⚔️", "{a} trả lời đúng, quái đau lắm đó 💪"],
    "cheer1_crit": ["{a} vừa đúng vừa nhanh, CHÍ MẠNG luôn ⚡", "Nhanh như chớp, {a} chí mạng rồi ⚡"],
    "cheer2": ["{a} và {b} đúng rồi! Phối hợp đỉnh quá 👏", "Giỏi lắm {a} với {b}! {a} nhanh nhất, chí mạng ⚡"],
    "cheerN": ["{a}, {b} và {n} bạn nữa trả lời đúng! Cả phòng giỏi quá 👏",
               "{a} nhanh nhất, chí mạng! {b} và {n} bạn nữa cũng đúng rồi 🎉",
               "Wow, {total} bạn trả lời đúng! {a} ra đòn đầu tiên ⚡"],
    # bảng xếp hạng phiên này
    "top_new": ["{name} vừa vượt lên dẫn đầu với {score} điểm! 👑", "Đổi ngôi rồi! {name} lên top 1 👑",
                "{name} chiếm top 1 rồi kìa, ai đuổi kịp không? 👑"],
    "top_now": ["Đang dẫn đầu là {name} với {score} điểm 👑 Ai vượt được không?",
                "Top 1 vẫn là {name}, {score} điểm! Cố lên cả nhà 💪"],
    "top_now2": ["{name} đang giữ top 1 đó, {second} bám sát phía sau nha 🔥",
                 "{name} dẫn đầu, {second} đứng thứ hai! Còn kịp lật kèo đó 🔥"],
    "hit_room": ["Ui da! Quái phản đòn, mất {lose} tim 😵 Còn {hearts} tim thôi!", "Đánh trượt nhiều quá, quái đánh lại rồi 😱 Còn {hearts} tim!"],
    "kill": ["Hạ gục {mon}! {name} tung đòn kết liễu 🎉", "{mon} gục rồi! MVP là {mvp} 🏆"],
    "kill_boss": ["👑 BOSS {mon} đã bị hạ! Cả phòng đỉnh quá 🎉🎉", "Hạ boss rồi! {name} ra đòn cuối, {mvp} là MVP 👑"],
    "record": ["KỶ LỤC MỚI! Cả phòng lên tới ải {floor} 🏆🎉", "Chưa từng đi xa thế này! Kỷ lục ải {floor} 🎉"],
    "fail": ["Cả phòng bị {mon} hạ rồi 😭 Quay về ải {back} làm lại nha!", "Huhu thua rồi... về ải {back} gom sức đánh lại nào 💪"],
    "door_vote": ["Chọn cửa vào ải {floor}: comment 1, 2 hoặc 3! 🚪", "Cửa nào đây cả nhà? Comment 1, 2, 3 nha 🚪"],
    "levelup": ["{name} lên cấp {lv}! {title} của phòng mình đó 🎉", "Chúc mừng {name} đạt cấp {lv} ⬆️✨"],
    "streak": ["{name} đúng {n} câu liền! Đỉnh quá đi 🔥", "Ai cản được {name} đây?! 🔥 x{n}"],
    "streak_lost": ["Tiếc ghê {name} ơi, chuỗi {n} câu dừng rồi 😢", "Không sao {name}, làm lại chuỗi mới nha!"],
    "follow": ["Cảm ơn {name} đã follow! 🥰", "Chào mừng {name} vào nhà nha! 💕"],
    "share": ["Cảm ơn {name} đã share live! 🔁💖"],
    "like_goal": ["Đủ mốc tim rồi! Câu sau x2 sát thương 💥", "Cảm ơn cả nhà thả tim! Đòn sau mạnh gấp đôi 💥"],
    "share_goal": ["Đủ mốc chia sẻ! Cảm ơn cả nhà nhiều lắm 💖", "Share nhiều quá, Hami vui ghê 💃"],
    # lời mời xen kẽ: chỉ tim / follow / share, không nhắc tới quà
    "support": ["Thích buổi học thì thả tim ❤️ và follow kênh nha!", "Thả tim đủ mốc là câu sau x2 sát thương đó ❤️",
                "Share live cho bạn bè cùng đánh quái nhé 🔁", "Follow kênh để không bỏ lỡ buổi săn quái sau nha 💕"],
    # CHỈ dùng khi API AI thật sự hết tiền / key hỏng (main.py bắt AICreditError)
    "ai_broke": ["Ôi, tài khoản AI của Hami hết credit thật rồi 😭 Tạm thời mình chưa trả lời câu hỏi được, cả nhà vẫn đánh quái bình thường nha",
                 "Hami hết tiền gọi AI mất rồi 😢 Cả nhà vẫn chơi bình thường nha, chủ kênh sẽ nạp lại sớm 🙏"],
    "ai_key": ["Hami đang mất kết nối AI 😵 Chờ chủ kênh sửa chút nha, mình vẫn đánh quái được!"],
    "ai_off": ["@{name} Hami đang hết credit AI nên chưa trả lời được 😢 Đánh quái tiếp với mình nha!",
               "@{name} AI của Hami tạm nghỉ vì hết credit, lát nữa hỏi lại mình nha 🙏"],
    "ai_back": ["Hami có AI trở lại rồi! Hỏi mình bằng \"bot ơi …\" nha 🎉"],
}
MOOD = {"q": "talk", "q_listen": "talk", "q_cloze": "talk", "q_trans": "talk", "q_hanviet": "talk",
        "spawn": "wow", "spawn_boss": "hurry", "hurry": "hurry", "reveal_none": "sad", "reveal_hit": "happy",
        "reveal_crit": "wow", "hit_room": "sad", "kill": "dance", "kill_boss": "dance", "record": "dance",
        "fail": "sad", "door_vote": "talk", "levelup": "dance", "streak": "wow", "streak_lost": "sad",
        "follow": "love", "share": "love", "like_goal": "dance", "share_goal": "love", "support": "love",
        "ai_broke": "sad", "ai_key": "sad", "ai_off": "sad", "ai_back": "dance",
        "greet1": "wave", "greet2": "wave", "greetN": "wave",
        "cheer1": "happy", "cheer1_crit": "wow", "cheer2": "happy", "cheerN": "dance", "top_new": "wow", "top_now": "happy", "top_now2": "happy"}


def line(kind: str, **kw) -> tuple[str, str]:
    """(text, mood). Tên người xem được cắt ngắn để bong bóng không bị tràn."""
    kw = {k: (str(v)[:18] + "…" if k in ("name", "a", "b", "mvp", "second") and len(str(v)) > 19 else v) for k, v in kw.items()}
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
