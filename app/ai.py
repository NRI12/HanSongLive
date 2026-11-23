"""AI tạo nội dung câu hỏi cho live (OpenAI / DeepSeek) + TTS (OpenAI).

`_chat`, `tts`, cách chia lô chạy song song và bước kiểm duyệt lần 2 được chép từ HanSong `server/app/ai.py`.
Nếu bên HanSong sửa các hàm đó thì chép lại. Khác HanSong: API key được truyền vào (lấy từ cấu hình HanSongLive),
không đọc biến môi trường trực tiếp.

Nội dung sinh ra (lưu ở bảng live_items, xem db.py):
  cloze  : {"answer": dạng của từ nằm NGUYÊN VĂN trong example_ko, "distractors": [3 cụm tiếng Hàn sai nghĩa]}
  trans  : {"wrong": [3 câu tiếng Việt dịch sai example_ko]}
"""
import json
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

VERIFY_PROMPT = """Kiểm tra kỹ dữ liệu câu hỏi trắc nghiệm tiếng Hàn sau như một biên tập viên đề thi.
Với mỗi mục:
- cloze.answer phải là chuỗi con nguyên văn của example_ko và chứa đúng từ cần hỏi; sửa nếu sai.
- Mỗi cloze.distractors khi thay vào chỗ của answer phải làm câu SAI nghĩa so với example_vi. Nếu một đáp án nhiễu \
vẫn đúng nghĩa (đồng nghĩa) hoặc sai ngữ pháp hẳn, thay bằng cụm khác.
- Mỗi trans_wrong phải SAI nghĩa so với example_ko; nếu câu nào lỡ đúng nghĩa thì viết lại.
Giữ nguyên thứ tự, số lượng và id. Trả về JSON cùng schema.
{data}"""


# ---------------------------------------------------------------- copied from HanSong
def _chat(provider, model, key, system, user, timeout=240):
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


def tts(text, lang, voice, out_path, key):
    """Chưa dùng trong live: để sẵn cho dạng bài cần câu mới (không có audio bên HanSong)."""
    if not key:
        raise AIError("TTS cần OPENAI_API_KEY")
    body = {"model": "gpt-4o-mini-tts", "voice": voice, "input": text, "instructions": TTS_INSTR[lang],
            "response_format": "mp3"}
    err = ""
    for _ in range(3):
        try:
            r = httpx.post("https://api.openai.com/v1/audio/speech", json=body,
                           headers={"Authorization": f"Bearer {key}"}, timeout=120)
            if r.status_code == 200 and len(r.content) > 500:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                return
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


# ---------------------------------------------------------------- generation
def _payload(words):
    return json.dumps([{"id": w["id"], "korean": w["korean"], "vietnamese": w["vietnamese"], "pos": w.get("pos", ""),
                        "example_ko": w["example_ko"], "example_vi": w["example_vi"]} for w in words],
                      ensure_ascii=False)


def _chunk(cfg, key, words, chat):
    provider = cfg["provider"]
    model = cfg["model_deepseek"] if provider == "deepseek" else cfg["model_openai"]
    data = chat(provider, model, key, SYSTEM, ITEM_PROMPT.format(data=_payload(words)))
    items = [i for i in data.get("items", []) if isinstance(i, dict)]
    if cfg.get("verify") and items:
        blob = [{**i, "example_ko": w["example_ko"], "example_vi": w["example_vi"], "korean": w["korean"]}
                for i in items for w in words if w["id"] == i.get("id")]
        v = chat(provider, model, key, SYSTEM, VERIFY_PROMPT.format(data=json.dumps({"items": blob}, ensure_ascii=False)))
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
        c = clean_cloze(w, i.get("cloze"))
        if c:
            out.append((w["id"], "cloze", c))
        t = clean_trans(w, i.get("trans_wrong"))
        if t:
            out.append((w["id"], "trans", t))
    return out


def generate_items(words: list[dict], cfg: dict, key: str, chat=_chat, progress=None):
    """words (có example_ko/example_vi) -> [(word_id, kind, data)]. Mục nào AI làm sai thì bỏ qua."""
    words = [w for w in words if w.get("example_ko") and w.get("example_vi")]
    chunks = [words[i:i + CHUNK] for i in range(0, len(words), CHUNK)]
    if not chunks:
        return []
    out, errors = [], []
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(chunks))) as ex:
        futs = [ex.submit(_chunk, cfg, key, c, chat) for c in chunks]
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
Người xem gõ câu hỏi, bạn trả lời bằng tiếng Việt, thân thiện, vui vẻ, xưng "mình", gọi người xem là "bạn".
Quy tắc:
- Trả lời CỰC NGẮN: tối đa 1-2 câu, dưới 110 ký tự, có thể thêm 1 emoji.
- Ưu tiên chủ đề học tiếng Hàn: nghĩa từ, cách đọc, ngữ pháp đơn giản, văn hoá Hàn. Có thể chào hỏi, tán gẫu nhẹ nhàng.
- Từ chối khéo các chủ đề chính trị, tôn giáo, 18+, bạo lực, thông tin cá nhân, tiền bạc, mua bán; quay về chuyện học.
- Không bao giờ hứa hẹn hay kêu gọi tặng quà để đổi lấy điểm hay quyền lợi. Không đưa link.
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
