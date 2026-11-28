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
    "q": ["A, B, C hay D? Chọn lẹ đi, đừng bắt Hami chờ 😤", "Câu dễ ợt, ai sai là Hami cười vào mặt đó nha 😏",
          "Nhanh tay lên! Chậm là đòn yếu xìu à 💅", "Ai đúng đầu tiên được CHÍ MẠNG, mấy người chậm chạp thì ngồi xem ⚡",
          "Im lặng nghe Hami đọc nè, cấm hỏi lại 🙄"],
    "q_listen": ["👻 Quái tàng hình! Không có chữ đâu, dỏng tai lên mà nghe 😤", "Nghe cho kỹ vào, Hami không đọc lại lần hai đâu 🎧"],
    "q_cloze": ["Điền chỗ trống đi, câu này mà sai thì về học lại lớp 1 🧩", "Chỗ trống to thế kia mà còn không điền được à? 🧩"],
    "q_trans": ["Câu này nghĩa là gì? Hami đọc một lần thôi, nghe cho tử tế 😏", "Dịch câu đi, đừng có đoán bừa nha 📝"],
    "q_gram": ["Câu NGỮ PHÁP nè! Điền tiểu từ hay đuôi câu cho đúng, sai là Hami bắt lỗi liền 😏",
               "Ngữ pháp đó cả nhà! Đừng chọn theo cảm giác nha 📘"],
    "q_gfix": ["Câu nào đúng ngữ pháp? Ba câu kia sai lè, soi kỹ vào 😤", "Bắt lỗi ngữ pháp nè, mắt tinh lên coi ✅"],
    "q_hanviet": ["Âm Hán Việt là gì? Người Việt mà sai câu này thì quê lắm đó 🈶",
                  "Câu cho điểm đó, sai là Hami nhớ mặt từng người 😤"],
    "spawn": ["{mon} lò dò tới ải {floor} rồi kìa! Xử nó đi chứ còn đứng đó 😤",
              "Ải {floor}: {mon} ra mặt! Comment A/B/C/D, đừng để nó cười vào mặt 😏",
              "{mon} nhìn ngứa mắt ghê, cả phòng đập nó đi 💢"],
    "spawn_flip": ["Ải {floor}: LẬT THẺ! Comment 2 số kiểu \"3 8\" để lật, ghép đúng chữ Hàn với nghĩa là đánh {mon} 😏",
                   "Ải lật thẻ nè! Nhớ kỹ vị trí, comment 2 số để lật. Lật bừa là Hami cười đó 🃏"],
    "spawn_race": ["Ải {floor}: ĐUA XE với {mon}! Trả lời đúng là xe chạy, nhanh thì chạy xa. Thua xe quái là quê lắm 🏎",
                   "Đua xe nè! Đúng thì xe chạy, để xe quái về đích trước là mất tim đó nha 😤🏁"],
    "flip_match": ["{name} lật trúng cặp! Trí nhớ cũng được đó 😏", "Trúng rồi {name}! Mấy người kia nhớ vị trí đi chứ 🃏"],
    "flip_timeout": ["Hết giờ mà lật chưa xong! Mất {lose} tim, xáo bài lại nè 😤", "Chậm quá, quái đánh mất {lose} tim rồi. Thẻ xáo lại, nhớ lại từ đầu đi 🙄"],
    "race_lost": ["Xe quái về đích trước! Mất {lose} tim, đua lại từ đầu, quê chưa 😤", "Để quái thắng đua luôn hả? Mất {lose} tim, còn {hearts} tim. Đua lại 🏁"],
    "spawn_boss": ["👹 BOSS {mon} tới! Nó đánh mất 2 tim đó, đứa nào sai là Hami ghim 😤",
                   "Ải {floor} là BOSS {mon}! Lề mề là toang cả phòng nha 🔥"],
    "greet1": ["Ơ {a} tới rồi à? Đứng xem chi, comment A/B/C/D vào đánh quái đi 😏",
               "{a} vào trễ thế! Thôi vào đánh luôn đi, Hami không chờ đâu 😤",
               "Chào {a}, vào đây là phải chơi, cấm đứng xem chùa 👋"],
    "greet2": ["{a} với {b} rủ nhau tới xem chùa à? Vào đánh quái lẹ 😏", "{a} và {b} tới rồi, đừng có lặn mất nha 👋"],
    "greetN": ["{a}, {b} với {n} bạn nữa vào rồi! Đông thế mà đánh yếu là Hami cười đó 😏",
               "Chào {a}, {b} và {n} bạn nữa. Vào là phải ra đòn, cấm xem chùa 👋"],
    "combo": ["{n} người ra đòn một lúc! Coi bộ cũng ra gì đó chứ 😏", "Combo {n} người! Quái run rồi kìa, đánh tiếp đi 🔥",
              "{n} chiến binh xông lên! Lúc nào cũng hăng vậy thì tốt 😤"],
    "hurry": ["Còn 5 giây! Ngủ gật hết rồi à? ⏰", "Nhanh lên! Chậm như rùa vậy 😱", "Hết giờ tới nơi rồi kìa, chốt đi 😤"],
    "reveal_none": ["Không ai trả lời luôn? Cả phòng đi ngủ hết rồi à 🙄"],
    "reveal_hit": ["Trúng {dmg} sát thương. Quái còn {hp} máu, đánh mạnh lên coi 💪",
                   "{dmg} sát thương thôi hả? Tạm được 😏"],
    "reveal_crit": ["{name} chí mạng! Hami công nhận đó, nhưng đừng có kiêu ⚡", "Đòn đầu của {name} đau ra trò ⚡"],
    # khen người trả lời đúng (gọi tên); {crit} = người nhanh nhất
    "cheer1": ["{a} đúng rồi. Cũng giỏi đấy, đừng tưởng bở 😏", "Chuẩn rồi {a}! Hami tạm công nhận đó ⚔️",
               "Có mỗi {a} đúng, mấy người còn lại làm gì vậy? 😤"],
    "cheer1_crit": ["{a} nhanh như chớp, CHÍ MẠNG luôn! Hami nể chút xíu thôi ⚡", "{a} chí mạng rồi, mấy người kia học hỏi đi 😏"],
    "cheer2": ["{a} với {b} đúng. Có hai người biết chơi, phần còn lại đâu? 😤", "{a} nhanh nhất, chí mạng! {b} cũng được đó 😏"],
    "cheerN": ["{a}, {b} và {n} bạn nữa đúng rồi! Phòng này cũng không đến nỗi tệ 😏",
               "{a} nhanh nhất, chí mạng! {b} với {n} bạn nữa cũng được, tạm tha 🎉",
               "{total} người đúng! Ra dáng phết đấy, {a} ra đòn đầu tiên ⚡"],
    # bảng xếp hạng phiên này
    "top_new": ["{name} vừa cướp top 1 với {score} điểm! Ai dám giành lại không? 👑", "Đổi ngôi rồi! {name} lên top 1, mấy người kia ngủ quên à? 👑",
                "{name} chiếm top 1 rồi đó, có ai đủ trình đuổi kịp không? 😏"],
    "top_now": ["Top 1 vẫn là {name}, {score} điểm. Không ai vượt nổi à? 😏",
                "{name} đang đè đầu cả phòng với {score} điểm 👑 Có ai dám không?"],
    "top_now2": ["{name} giữ top 1, {second} hít khói phía sau 😏",
                 "{name} dẫn đầu, {second} đứng thứ hai. Cố lên coi, đừng để bị bỏ xa 🔥"],
    "hit_room": ["Đó, đánh trượt nhiều chưa! Quái đánh lại mất {lose} tim. Còn {hearts} tim thôi đó 😤",
                 "Trượt lia lịa luôn, quái phản đòn rồi! Còn {hearts} tim, tập trung giùm cái 💢"],
    "kill": ["{mon} gục rồi! {name} ra đòn kết liễu, ngầu đấy 😎", "Hạ {mon} rồi! MVP là {mvp}, mấy người khác xem mà học 🏆"],
    "kill_boss": ["👑 BOSS {mon} nằm rồi! Phòng này cũng ra gì đó chứ 😎", "Hạ boss rồi! {name} ra đòn cuối, {mvp} là MVP. Hami công nhận 👑"],
    "record": ["KỶ LỤC MỚI! Lên tới ải {floor} luôn, không ngờ phòng này làm được đó 🏆", "Ải {floor}, xa nhất từ trước tới giờ! Hami hơi bất ngờ đó 😏🎉"],
    "fail": ["Thua {mon} rồi! Quay về ải {back}, học lại đi cả nhà 🙄", "Bị {mon} hạ gục, quê chưa? Về ải {back} làm lại 😤"],
    "door_vote": ["Chọn cửa vào ải {floor}: comment 1, 2 hoặc 3, chọn lẹ 🚪", "Cửa nào? 1, 2 hay 3, đừng bắt Hami chờ 😤"],
    "levelup": ["{name} lên cấp {lv}, thành {title} rồi! Đừng có vênh váo nha 😏", "{name} lên cấp {lv}! Cũng chăm phết đó ⬆️"],
    "streak": ["{name} đúng {n} câu liền! Ai cản nổi đây? 🔥", "{name} đúng liền {n} câu, mấy người khác ngồi xem à? 🔥"],
    "streak_lost": ["Ha, {name} đứt chuỗi {n} câu rồi! Kiêu cho lắm vào 😏", "{name} mất chuỗi {n} câu, làm lại từ đầu đi 🙄"],
    "follow": ["{name} follow rồi! Có mắt nhìn người đó 😎", "Cảm ơn {name} đã follow, giờ thì đừng có bỏ đi nha 😏"],
    "share": ["{name} share live rồi! Biết điều đó 😎"],
    "like_goal": ["Đủ mốc tim rồi! Câu sau x2 sát thương, đánh cho ra hồn nha 💥", "Thả tim cũng chăm đó! Đòn sau mạnh gấp đôi 💥"],
    "share_goal": ["Đủ mốc chia sẻ! Phòng này biết điều ghê 😎", "Share nhiều thế, Hami tạm hài lòng 💅"],
    # lời mời xen kẽ: chỉ tim / follow / share, không nhắc tới quà
    "support": ["Xem chùa mãi thế? Thả tim với follow đi chứ 😏", "Thả tim đủ mốc là câu sau x2 sát thương, đừng có lười ❤️",
                "Share live rủ bạn vào đánh quái đi, đừng ích kỷ 🔁", "Chưa follow thì follow đi, buổi sau lại vào bị Hami mắng tiếp 😤"],
    # CHỈ dùng khi API AI thật sự hết tiền / key hỏng (main.py bắt AICreditError). Giữ đúng sự thật, không xin quà.
    "ai_broke": ["Tài khoản AI của Hami hết credit thật rồi 😤 Giờ Hami chưa trả lời câu hỏi được, cả nhà cứ đánh quái tiếp đi",
                 "Hami hết tiền gọi AI thật rồi đó 🙄 Vẫn chơi bình thường nha, chủ kênh sẽ nạp lại sau"],
    "ai_key": ["Hami đang mất kết nối AI 😤 Chờ chủ kênh sửa chút, vẫn đánh quái được nha!"],
    "ai_off": ["@{name} AI của Hami đang hết credit nên chưa trả lời được đâu, hỏi lại sau đi 😤",
               "@{name} AI hết credit rồi, không trả lời được đâu. Lo đánh quái đi 🙄"],
    "ai_back": ["Hami có AI lại rồi! Muốn hỏi gì thì gõ \"bot ơi …\", hỏi cho đàng hoàng nha 😏"],
}
MOOD = {"q": "talk", "q_listen": "talk", "q_cloze": "talk", "q_trans": "talk", "q_hanviet": "talk", "q_gram": "talk", "q_gfix": "talk",
        "spawn": "wow", "spawn_flip": "wow", "spawn_race": "hurry", "flip_match": "happy", "flip_timeout": "sad", "race_lost": "sad", "spawn_boss": "hurry", "hurry": "hurry", "combo": "wow", "reveal_none": "sad", "reveal_hit": "happy",
        "reveal_crit": "wow", "hit_room": "sad", "kill": "dance", "kill_boss": "dance", "record": "dance",
        "fail": "sad", "door_vote": "talk", "levelup": "dance", "streak": "wow", "streak_lost": "sad",
        "follow": "love", "share": "love", "like_goal": "dance", "share_goal": "love", "support": "love",
        "ai_broke": "sad", "ai_key": "sad", "ai_off": "sad", "ai_back": "dance",
        "greet1": "wave", "greet2": "wave", "greetN": "wave",
        "cheer1": "happy", "cheer1_crit": "wow", "cheer2": "happy", "cheerN": "dance", "top_new": "wow", "top_now": "happy", "top_now2": "happy"}


# thứ tự đọc trên overlay (xem live._bot_raw): INTRO nói trước khi đọc đề câu mới;
# SOFT là câu phụ, sang câu hỏi khác mà chưa kịp nói thì bỏ. Các câu còn lại (khen gọi tên, phản đòn, hạ quái…) không bao giờ bỏ.
INTRO = {"q", "q_listen", "q_cloze", "q_trans", "q_hanviet", "q_gram", "q_gfix", "spawn", "spawn_boss", "spawn_flip", "spawn_race"}
SOFT = {"flip_match", "top_now", "top_now2", "support", "greet1", "greet2", "greetN", "share", "combo", "hurry", "like_goal",
        "share_goal", "reveal_none", "ai_off"}


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
