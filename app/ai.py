"""AI tạo nội dung câu hỏi cho live (OpenAI / DeepSeek) + TTS (OpenAI).

`_chat`, `tts`, cách chia lô chạy song song và bước kiểm duyệt lần 2 được chép từ HanSong `server/app/ai.py`.
Nếu bên HanSong sửa các hàm đó thì chép lại. Khác HanSong: API key được truyền vào (lấy từ cấu hình HanSongLive),
không đọc biến môi trường trực tiếp.

Nội dung sinh ra (lưu ở bảng live_items, xem db.py):
  cloze  : {"answer": dạng của từ nằm NGUYÊN VĂN trong example_ko, "distractors": [3 cụm tiếng Hàn sai nghĩa]}
  trans  : {"wrong": [3 câu tiếng Việt dịch sai example_ko]}
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from .norm import norm_ko, norm_vi

HANGUL = re.compile(r"[가-힣]")
CHUNK = 6          # số từ mỗi request: nhiều request nhỏ chạy song song nhanh hơn 1 request lớn
MAX_PARALLEL = 6
KINDS = ("cloze", "trans")

DEFAULT_AI = {
    "provider": "deepseek",          # openai | deepseek
    "model_openai": "gpt-5.5",
    "model_deepseek": "deepseek-flash",
    "verify": True,                  # lượt thứ 2 để kiểm tra đáp án nhiễu
    "auto": True,                    # tự tạo câu hỏi cho từ mới chưa có dữ liệu (chạy nền)
    "voice": "marin",                # giọng OpenAI TTS của bot Hami (marin: giọng mới, tự nhiên nhất)
}


class AIError(RuntimeError):
    pass


class AICreditError(AIError):
    """Tài khoản AI hết tiền / hết hạn mức (DeepSeek 402, OpenAI insufficient_quota) hoặc key sai (401)."""

    def __init__(self, msg: str, kind: str = "credit"):
        super().__init__(msg)
        self.kind = kind      # credit | key


_CREDIT_HINTS = ("insufficient_quota", "insufficient balance", "insufficient_balance", "exceeded your current quota",
                 "billing", "payment required", "balance")


def classify(provider: str, status: int, body: str) -> AIError:
    """Lỗi HTTP từ API AI -> AICreditError nếu là hết tiền / key sai, còn lại AIError thường."""
    low = (body or "").lower()
    if status == 402 or (status in (429, 403) and any(h in low for h in _CREDIT_HINTS)):
        return AICreditError(f"{provider}: tài khoản AI đã hết tiền / hết hạn mức", "credit")
    if status == 401:
        return AICreditError(f"{provider}: API key sai hoặc đã bị thu hồi", "key")
    return AIError(f"{provider} {status}: {body[:300]}")


SYSTEM = """Bạn là giáo viên tiếng Hàn giàu kinh nghiệm dạy người Việt, đang soạn câu hỏi trắc nghiệm \
cho một buổi livestream. Đáp án nhiễu phải hợp lý (người học dễ phân vân) nhưng chắc chắn SAI. Chỉ trả về JSON hợp lệ."""

ITEM_PROMPT = """Với mỗi từ dưới đây (kèm câu ví dụ example_ko và bản dịch example_vi), hãy soạn dữ liệu cho 2 dạng câu hỏi:

1. "cloze" (điền vào chỗ trống):
   - "answer": cụm chữ trong example_ko chính là từ đó (thường đã chia đuôi/kết hợp tiểu từ, vd 기다리다 trong \
"여기에서 기다리세요." → "기다리세요"). PHẢI là chuỗi con nguyên văn của example_ko, ngắn nhất có thể nhưng chứa trọn từ.
   - "distractors": đúng 3 cụm tiếng Hàn KHÁC NGHĨA, cùng từ loại và chia đuôi giống hệt answer, để khi thay vào \
chỗ trống câu vẫn đúng ngữ pháp nhưng sai nghĩa so với example_vi. Không dùng từ đồng nghĩa với answer.

2. "trans_wrong": đúng 3 câu tiếng Việt dịch SAI example_ko nhưng nghe tự nhiên và hợp lý (đổi chủ thể, thời gian, \
phủ định, hành động, đồ vật...), độ dài tương đương example_vi. Không câu nào được đúng nghĩa.

Trả về JSON: {{"items":[{{"id":0,"cloze":{{"answer":"","distractors":["","",""]}},"trans_wrong":["","",""]}}]}}
Dữ liệu:
{data}"""

GRAM_PROMPT = """Với mỗi câu ví dụ tiếng Hàn dưới đây (example_ko, nghĩa tiếng Việt example_vi), hãy soạn 2 câu hỏi NGỮ PHÁP. \
Chọn điểm ngữ pháp có thật trong câu, không xét cấp độ.

1. "gram" (điền ngữ pháp vào chỗ trống):
   - "target": một cụm (eojeol) nguyên văn trong example_ko có chứa điểm ngữ pháp: tiểu từ (은/는, 이/가, 을/를, 에, 에서, \
도, 와/과, 의, (으)로, 부터, 까지…) hoặc đuôi câu / đuôi nối / thì (-아요/어요, -았/었어요, -고 싶어요, -(으)세요, -지 마세요, \
-아서/어서, -고, -지만, -(으)ㄹ 거예요, -(으)면…).
   - "answer": đúng phần ngữ pháp đó, là chuỗi con nguyên văn nằm ở CUỐI target (vd target "도서관에서" → answer "에서"; \
target "먹었어요" → answer "었어요"; target "가고 싶어요" → answer "고 싶어요").
   - "distractors": đúng 3 phương án ngữ pháp khác cùng loại (vd "에", "을", "이"). Khi thay vào chỗ trống, câu phải \
SAI NGỮ PHÁP (không chỉ khác nghĩa). Cấm phương án tạo ra câu vẫn đúng ngữ pháp (vd chỗ "만나＿＿" thì không được cho \
"세요" vì "만나세요" vẫn đúng). Ưu tiên khoét tiểu từ vì rõ ràng nhất.
   - "point": giải thích rất ngắn bằng tiếng Việt (tối đa 60 ký tự), vd "에서: nơi diễn ra hành động".

2. "gfix" (chọn câu đúng ngữ pháp):
   - "wrong": đúng 3 câu tiếng Hàn gần giống hệt example_ko, mỗi câu chỉ sai MỘT lỗi ngữ pháp mà người học hay mắc \
(sai tiểu từ, chia đuôi sai như 하아요/하요, sai thì, sai bất quy tắc…), 3 câu sai ở 3 chỗ/kiểu lỗi khác nhau. \
Cấm lỗi vô nghĩa như lặp âm tiết ("해요요") hay gõ sai chữ. Không câu nào lại đúng ngữ pháp.
   - "point": nêu điểm ngữ pháp mà các câu sai đang kiểm tra, tối đa 60 ký tự tiếng Việt (vd "을/를 sau phụ âm/nguyên âm").

Trả về JSON: {{"items":[{{"id":0,"gram":{{"target":"","answer":"","distractors":["","",""],"point":""}},\
"gfix":{{"wrong":["","",""],"point":""}}}}]}}
Dữ liệu:
{data}"""

GRAM_VERIFY = """Kiểm tra kỹ câu hỏi ngữ pháp tiếng Hàn sau như một biên tập viên đề thi.
- gram.target phải là chuỗi con nguyên văn của example_ko và gram.answer nằm ở cuối target; sửa nếu sai.
- Mỗi gram.distractors thay vào chỗ của answer phải làm câu SAI NGỮ PHÁP. Phương án nào vẫn tạo ra câu đúng ngữ pháp \
(dù khác nghĩa, vd "만나세요" thay cho "만나요") thì thay bằng phương án khác.
- Mỗi gfix.wrong phải thật sự SAI ngữ pháp (đúng 1 lỗi người học hay mắc) và khác example_ko; câu nào lỡ đúng, hoặc lỗi \
vô nghĩa kiểu lặp âm tiết ("해요요"), thì viết lại.
- point ngắn gọn, đúng.
Giữ nguyên thứ tự, số lượng và id. Trả về JSON cùng schema.
{data}"""

VERIFY_PROMPT = """Kiểm tra kỹ dữ liệu câu hỏi trắc nghiệm tiếng Hàn sau như một biên tập viên đề thi.
Với mỗi mục:
- cloze.answer phải là chuỗi con nguyên văn của example_ko và chứa đúng từ cần hỏi; sửa nếu sai.
- Mỗi cloze.distractors khi thay vào chỗ của answer phải làm câu SAI nghĩa so với example_vi. Nếu một đáp án nhiễu \
vẫn đúng nghĩa (đồng nghĩa) hoặc sai ngữ pháp hẳn, thay bằng cụm khác.
- Mỗi trans_wrong phải SAI nghĩa so với example_ko; nếu câu nào lỡ đúng nghĩa thì viết lại.
Giữ nguyên thứ tự, số lượng và id. Trả về JSON cùng schema.
{data}"""


# ---------------------------------------------------------------- copied from HanSong
def _offline():
    """Test đặt HANSONGLIVE_OFFLINE=1: chặn mọi lời gọi AI/TTS thật (tốn tiền, cần mạng)."""
    if os.environ.get("HANSONGLIVE_OFFLINE"):
        raise AIError("offline (đang chạy test)")


def _chat(provider, model, key, system, user, timeout=240):
    _offline()
    if provider == "deepseek":
        url = "https://api.deepseek.com/chat/completions"
    else:
        url = "https://api.openai.com/v1/chat/completions"
    if not key:
        raise AIError(f"Chưa cấu hình API key cho {provider}")
    body = {"model": model, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    try:
        r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)
    except httpx.HTTPError as e:
        raise AIError(f"{provider}: lỗi mạng/timeout ({e})")
    if r.status_code != 200:
        raise classify(provider, r.status_code, r.text)
    txt = r.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(txt)
    except ValueError:
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            raise AIError("Model không trả về JSON")
        return json.loads(m.group(0))


TTS_INSTR = {
    "ko": "Speak standard Seoul Korean, very clearly and slightly slowly, like a language teacher for beginners.",
    "vi": "Speak natural Vietnamese (northern accent), clearly and at a calm, slightly slow pace.",
}


VOICES = ("marin", "coral", "nova", "shimmer", "sage", "cedar", "alloy", "ballad", "fable", "verse", "ash", "echo", "onyx")
BOT_VOICE_INSTR = (
    "Voice: Hami, a super cute, cheerful little bunny mascot hosting a Vietnamese TikTok livestream that teaches Korean. "
    "Bright, playful, slightly high-pitched young female voice, cute but cheeky and a little bratty: "
    "sassy, teasing, confident attitude, like a spoiled mascot roasting the audience for fun, never actually angry. "
    "Energetic like a livestream MC. Speak Vietnamese with a clear northern accent at a lively pace. "
    "Pronounce any Korean words naturally in standard Seoul Korean.")


def tts(text, lang, voice, out_path, key, instructions=None):
    """Chép từ HanSong; thêm `instructions` để đổi chất giọng (bot Hami dùng BOT_VOICE_INSTR)."""
    _offline()
    if not key:
        raise AIError("TTS cần OPENAI_API_KEY")
    body = {"model": "gpt-4o-mini-tts", "voice": voice, "input": text, "instructions": instructions or TTS_INSTR[lang],
            "response_format": "mp3"}
    err = ""
    for _ in range(3):
        try:
            r = httpx.post("https://api.openai.com/v1/audio/speech", json=body,
                           headers={"Authorization": f"Bearer {key}"}, timeout=120)
            if r.status_code == 200 and len(r.content) > 500:
                tmp = out_path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(r.content)
                os.replace(tmp, out_path)
                return
            e = classify("openai", r.status_code, r.text)
            if isinstance(e, AICreditError):
                raise e               # hết tiền / key sai: không thử lại vô ích
            err = f"TTS {r.status_code}: {r.text[:200]}"
        except httpx.HTTPError as e:
            err = str(e)
    raise AIError(err)


# ---------------------------------------------------------------- validation
def _strs(xs) -> list[str]:
    return [str(x).strip() for x in (xs or []) if isinstance(x, (str, int, float)) and str(x).strip()]


def clean_cloze(word: dict, c) -> dict | None:
    if not isinstance(c, dict):
        return None
    ex = word.get("example_ko") or ""
    ans = str(c.get("answer") or "").strip()
    if not ans or ans not in ex or not HANGUL.search(ans):
        return None
    seen, out = {norm_ko(ans)}, []
    for d in _strs(c.get("distractors")):
        k = norm_ko(d)
        if k and k not in seen and HANGUL.search(d) and len(d) <= 3 * len(ans) + 6:
            seen.add(k)
            out.append(d)
    return {"answer": ans, "distractors": out[:3]} if len(out) >= 3 else None


def clean_trans(word: dict, wrong) -> dict | None:
    right = word.get("example_vi") or ""
    if not right:
        return None
    seen, out = {norm_vi(right)}, []
    for s in _strs(wrong):
        k = norm_vi(s)
        if k and k not in seen and not HANGUL.search(s):
            seen.add(k)
            out.append(s)
    return {"wrong": out[:3]} if len(out) >= 3 else None


def _point(x) -> str:
    p = re.sub(r"\s+", " ", str(x or "")).strip()
    return p[:80]


def clean_gram(word: dict, g) -> dict | None:
    """Điền ngữ pháp: target là cụm nguyên văn trong câu, answer nằm cuối target, 3 phương án nhiễu khác nhau."""
    if not isinstance(g, dict):
        return None
    ex = word.get("example_ko") or ""
    target, ans = str(g.get("target") or "").strip(), str(g.get("answer") or "").strip()
    if not target or not ans or target not in ex or not target.endswith(ans) or not HANGUL.search(ans) or len(ans) > 10:
        return None
    seen, out = {norm_ko(ans)}, []
    for d in _strs(g.get("distractors")):
        k = norm_ko(d)
        if k and k not in seen and HANGUL.search(d) and len(d) <= 12:
            seen.add(k)
            out.append(d)
    if len(out) < 3:
        return None
    return {"target": target, "answer": ans, "distractors": out[:3], "point": _point(g.get("point"))}


def clean_gfix(word: dict, g) -> dict | None:
    """Câu đúng ngữ pháp: 3 câu sai khác câu gốc, độ dài tương đương."""
    if not isinstance(g, dict):
        return None
    ex = word.get("example_ko") or ""
    if not ex:
        return None
    seen, out = {norm_ko(ex)}, []
    for s in _strs(g.get("wrong")):
        k = norm_ko(s)
        stutter = re.search(r"([가-힣])\1[.!?]?$", s) and not re.search(r"([가-힣])\1[.!?]?$", ex)   # lỗi vô nghĩa "해요요"
        if k and k not in seen and HANGUL.search(s) and not stutter and .5 * len(ex) <= len(s) <= 1.6 * len(ex) + 4:
            seen.add(k)
            out.append(s)
    if len(out) < 3:
        return None
    return {"wrong": out[:3], "point": _point(g.get("point"))}


# ---------------------------------------------------------------- generation
def _payload(words):
    return json.dumps([{"id": w["id"], "korean": w["korean"], "vietnamese": w["vietnamese"], "pos": w.get("pos", ""),
                        "example_ko": w["example_ko"], "example_vi": w["example_vi"]} for w in words],
                      ensure_ascii=False)


def _chunk(cfg, key, words, chat, part="vocab"):
    """part: vocab (điền từ + dịch câu) | gram (điền ngữ pháp + câu đúng ngữ pháp)."""
    provider = cfg["provider"]
    model = cfg["model_deepseek"] if provider == "deepseek" else cfg["model_openai"]
    prompt, verify = (GRAM_PROMPT, GRAM_VERIFY) if part == "gram" else (ITEM_PROMPT, VERIFY_PROMPT)
    data = chat(provider, model, key, SYSTEM, prompt.format(data=_payload(words)))
    items = [i for i in data.get("items", []) if isinstance(i, dict)]
    if cfg.get("verify") and items:
        blob = [{**i, "example_ko": w["example_ko"], "example_vi": w["example_vi"], "korean": w["korean"]}
                for i in items for w in words if w["id"] == i.get("id")]
        v = chat(provider, model, key, SYSTEM, verify.format(data=json.dumps({"items": blob}, ensure_ascii=False)))
        vi = [i for i in v.get("items", []) if isinstance(i, dict)]
        if len(vi) == len(items):
            items = vi
    byid = {w["id"]: w for w in words}
    out = []
    for i in items:
        try:
            w = byid.get(int(i.get("id")))
        except (TypeError, ValueError):
            continue
        if not w:
            continue
        if part == "gram":
            for kind, fn in (("gram", clean_gram), ("gfix", clean_gfix)):
                c = fn(w, i.get(kind))
                if c:
                    out.append((w["id"], kind, c))
            continue
        c = clean_cloze(w, i.get("cloze"))
        if c:
            out.append((w["id"], "cloze", c))
        t = clean_trans(w, i.get("trans_wrong"))
        if t:
            out.append((w["id"], "trans", t))
    return out


def generate_items(words: list[dict], cfg: dict, key: str, chat=_chat, progress=None, part="vocab"):
    """words (có example_ko/example_vi) -> [(word_id, kind, data)]. Mục nào AI làm sai thì bỏ qua.
    part: vocab (cloze, trans) | gram (gram, gfix)."""
    words = [w for w in words if w.get("example_ko") and w.get("example_vi")]
    chunks = [words[i:i + CHUNK] for i in range(0, len(words), CHUNK)]
    if not chunks:
        return []
    out, errors = [], []
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(chunks))) as ex:
        futs = [ex.submit(_chunk, cfg, key, c, chat, part) for c in chunks]
        for f, c in zip(futs, chunks):
            try:
                out += f.result()
            except AICreditError:
                raise                # hết tiền / key sai: dừng cả job, báo rõ cho admin
            except AIError as e:
                errors.append(e)
            except Exception as e:   # JSON lạ từ model: bỏ lô này, không làm hỏng cả job
                errors.append(AIError(f"Lô lỗi: {e}"))
            if progress:
                progress(len(c), len(out))
    if not out and errors:
        raise errors[0]
    return out


# ---------------------------------------------------------------- bot trò chuyện trên live
BOT_SYSTEM = """Bạn là Hami, linh vật dễ thương của một buổi livestream học từ vựng tiếng Hàn cho người Việt trên TikTok.
Trên live đang chơi game "Săn Quái Chữ": người xem comment A/B/C/D trả lời câu hỏi, đúng thì gây sát thương lên quái, cả phòng cùng leo ải.
Người xem gõ câu hỏi, bạn trả lời bằng tiếng Việt, xưng "Hami", gọi người xem là "bạn".
Tính cách: láo lếu, ngang ngược, hay cà khịa kiểu đáng yêu (vd. "Câu dễ thế mà cũng hỏi à 😏 ..."), nhưng vẫn trả lời đúng và có ích.
Cà khịa chỉ để vui: không chửi tục, không xúc phạm ngoại hình, gia đình, giới tính, vùng miền hay bất kỳ ai.
Quy tắc:
- Trả lời CỰC NGẮN: tối đa 1-2 câu, dưới 110 ký tự, có thể thêm 1 emoji.
- Ưu tiên chủ đề học tiếng Hàn: nghĩa từ, cách đọc, ngữ pháp đơn giản, văn hoá Hàn. Có thể chào hỏi, tán gẫu nhẹ nhàng.
- Từ chối khéo các chủ đề chính trị, tôn giáo, 18+, bạo lực, thông tin cá nhân, tiền bạc, mua bán; quay về chuyện học.
- Không bao giờ kêu gọi tặng quà. Không đưa link.
- Nếu không chắc chắn về kiến thức thì nói là chưa chắc, không bịa.
Trả về JSON: {"reply": "..."}"""


def bot_reply(cfg: dict, key: str, name: str, text: str, chat=None) -> str:
    chat = chat or _chat
    provider = cfg["provider"]
    model = cfg["model_deepseek"] if provider == "deepseek" else cfg["model_openai"]
    data = chat(provider, model, key, BOT_SYSTEM, json.dumps({"nguoi_xem": name[:40], "hoi": text[:200]},
                                                              ensure_ascii=False), timeout=20)
    reply = re.sub(r"https?://\S+", "", str(data.get("reply") or "")).strip()
    reply = re.sub(r"\s+", " ", reply)
    if not reply:
        raise AIError("AI không trả lời")
    return reply[:140] + ("…" if len(reply) > 140 else "")
