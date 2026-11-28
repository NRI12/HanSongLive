"""Lộ trình học theo ngày (giáo án buổi live).

Mỗi buổi ~60 câu: 3 điểm ngữ pháp MỚI theo giáo trình chuẩn (bắt đầu từ sơ cấp 2, bỏ mức dễ) + 2 điểm ÔN, câu ngữ pháp do AI
đặt mới quanh đúng điểm đó (ưu tiên dùng từ trong kho HanSong), đan xen với câu từ vựng lấy từ kho HanSong.
Toàn bộ câu hỏi được soạn sẵn và lưu lại (`live_plans`) để chủ kênh xem trước ở /plan, xoá câu, chọn buổi nào chạy.
Đang chạy 1 buổi (`live_config.plan_active = {id, pos}`) thì game ra đúng các câu đó theo thứ tự; hết thì quay về chế độ thường.
Cấp độ trong giáo trình chỉ dùng để xếp thứ tự bài, không hiện trên overlay (người dùng không muốn hiện TOPIK/cấp độ).
"""
import copy
import datetime
import json
import random
from concurrent.futures import ThreadPoolExecutor

from . import ai, db, live

# ---------------------------------------------------------------- giáo trình chuẩn (thứ tự bài), bỏ sơ cấp 1
SYLLABUS = [
    # sơ cấp 2
    ("-(으)면", "nếu, khi (điều kiện)", "Sơ cấp 2"),
    ("-아서/어서", "vì… nên / rồi (trình tự)", "Sơ cấp 2"),
    ("-(으)니까", "vì… nên (lý do, kèm đề nghị)", "Sơ cấp 2"),
    ("-(으)ㄹ 수 있다/없다", "có thể / không thể", "Sơ cấp 2"),
    ("-고 있다", "đang (tiếp diễn)", "Sơ cấp 2"),
    ("-아/어 보다", "thử làm", "Sơ cấp 2"),
    ("-아/어 주다", "làm giúp, làm cho", "Sơ cấp 2"),
    ("-아야/어야 하다", "phải", "Sơ cấp 2"),
    ("-아도/어도 되다", "được phép", "Sơ cấp 2"),
    ("-(으)면 안 되다", "không được làm", "Sơ cấp 2"),
    ("-(으)ㄹ게요", "sẽ (hứa, ý định của người nói)", "Sơ cấp 2"),
    ("-(으)ㄹ까요?", "nhé? (rủ rê, hỏi ý kiến)", "Sơ cấp 2"),
    ("-(으)ㄹ 거예요", "sẽ (dự định / phỏng đoán)", "Sơ cấp 2"),
    ("-기 전에", "trước khi", "Sơ cấp 2"),
    ("-(으)ㄴ 후에", "sau khi", "Sơ cấp 2"),
    ("-(으)면서", "vừa… vừa", "Sơ cấp 2"),
    ("-(으)려고 하다", "định làm", "Sơ cấp 2"),
    ("-(으)러 가다/오다", "đi/đến để làm", "Sơ cấp 2"),
    ("-는 (định ngữ hiện tại)", "định ngữ động từ hiện tại", "Sơ cấp 2"),
    ("-(으)ㄴ (định ngữ)", "định ngữ quá khứ / tính từ", "Sơ cấp 2"),
    ("-(으)ㄹ (định ngữ tương lai)", "định ngữ tương lai", "Sơ cấp 2"),
    ("-(으)ㄴ 적이 있다/없다", "đã từng / chưa từng", "Sơ cấp 2"),
    ("-지 못하다 / 못", "không thể (do năng lực)", "Sơ cấp 2"),
    ("-게 (trạng từ)", "một cách", "Sơ cấp 2"),
    ("-기 때문에", "vì", "Sơ cấp 2"),
    ("-(으)ㄴ/는데", "bối cảnh / nhưng", "Sơ cấp 2"),
    ("-지요?", "nhỉ, phải không", "Sơ cấp 2"),
    ("-네요", "quá, ghê (cảm thán)", "Sơ cấp 2"),
    ("-(으)ㄹ 때", "khi", "Sơ cấp 2"),
    ("-거나", "hoặc", "Sơ cấp 2"),
    ("-아지다/어지다", "trở nên", "Sơ cấp 2"),
    ("-게 되다", "được, trở nên (kết quả)", "Sơ cấp 2"),
    ("-(으)ㄴ 지 (시간이 되다)", "đã… được bao lâu", "Sơ cấp 2"),
    ("ㅂ bất quy tắc", "ㅂ → 우 (덥다 → 더워요)", "Sơ cấp 2"),
    ("ㄷ bất quy tắc", "ㄷ → ㄹ (듣다 → 들어요)", "Sơ cấp 2"),
    ("르 bất quy tắc", "르 → ㄹㄹ (모르다 → 몰라요)", "Sơ cấp 2"),
    ("ㅅ bất quy tắc", "ㅅ rơi (낫다 → 나아요)", "Sơ cấp 2"),
    ("ㅎ bất quy tắc", "ㅎ rơi (빨갛다 → 빨개요)", "Sơ cấp 2"),
    ("-보다 (so sánh)", "hơn", "Sơ cấp 2"),
    ("-처럼/같이", "giống như", "Sơ cấp 2"),
    ("-밖에 + phủ định", "chỉ (ngoài ra không)", "Sơ cấp 2"),
    ("-기로 하다", "quyết định làm", "Sơ cấp 2"),
    # trung cấp
    ("-(으)ㄴ/는 것 같다", "có vẻ, hình như", "Trung cấp"),
    ("-(으)ㄴ/는 편이다", "thuộc loại, khá là", "Trung cấp"),
    ("-도록", "để, sao cho", "Trung cấp"),
    ("-다가", "đang… thì (chuyển hành động)", "Trung cấp"),
    ("-았/었다가", "đã… rồi lại", "Trung cấp"),
    ("-(으)ㄴ/는 대신에", "thay vì, bù lại", "Trung cấp"),
    ("-자마자", "ngay khi", "Trung cấp"),
    ("-는 동안", "trong khi", "Trung cấp"),
    ("-(으)ㄹ 뻔하다", "suýt nữa thì", "Trung cấp"),
    ("-(으)ㄹ 정도로", "đến mức", "Trung cấp"),
    ("-(으)ㄴ/는데도", "mặc dù… vẫn", "Trung cấp"),
    ("-더라도", "dù cho", "Trung cấp"),
    ("-아/어 놓다", "làm sẵn", "Trung cấp"),
    ("-아/어 버리다", "mất, hẳn (tiếc nuối / nhẹ nhõm)", "Trung cấp"),
    ("-아/어 있다", "đang ở trạng thái", "Trung cấp"),
    ("-게 하다", "bắt, khiến ai làm", "Trung cấp"),
    ("Bị động -이/히/리/기-", "bị, được (bị động)", "Trung cấp"),
    ("Sai khiến -이/히/리/기/우/구/추-", "cho, bắt (sai khiến)", "Trung cấp"),
    ("-다고 하다", "nói rằng (gián tiếp trần thuật)", "Trung cấp"),
    ("-냐고 하다", "hỏi rằng (gián tiếp nghi vấn)", "Trung cấp"),
    ("-자고 하다", "rủ rằng (gián tiếp rủ rê)", "Trung cấp"),
    ("-(으)라고 하다", "bảo rằng (gián tiếp mệnh lệnh)", "Trung cấp"),
    ("-(으)ㄹ 테니까", "vì (tôi) sẽ… nên", "Trung cấp"),
    ("-(으)ㄹ걸요", "chắc là… đấy", "Trung cấp"),
    ("-잖아요", "mà, còn gì (nhắc điều đã biết)", "Trung cấp"),
    ("-거든요", "vì… mà (giải thích)", "Trung cấp"),
    ("-던 (hồi tưởng)", "định ngữ hồi tưởng", "Trung cấp"),
    ("-더라고요", "thấy rằng (kể lại điều đã trải qua)", "Trung cấp"),
    ("-(으)ㄹ수록", "càng… càng", "Trung cấp"),
    ("-는 바람에", "do… (kết quả không mong muốn)", "Trung cấp"),
    ("-느라고", "vì mải… nên", "Trung cấp"),
    ("-(으)ㄹ 만하다", "đáng để", "Trung cấp"),
    ("-기는 하지만", "thì có… nhưng", "Trung cấp"),
    ("-(으)ㄹ지도 모르다", "không chừng, biết đâu", "Trung cấp"),
    ("-나 보다 / -(으)ㄴ가 보다", "hình như (suy đoán)", "Trung cấp"),
    ("-는 김에", "nhân tiện", "Trung cấp"),
    ("-(으)ㄴ/는 척하다", "giả vờ", "Trung cấp"),
    ("-기만 하다", "chỉ toàn", "Trung cấp"),
    ("-아/어 가지고", "rồi / vì (khẩu ngữ)", "Trung cấp"),
    ("-(으)ㄹ 겸", "kiêm, tiện thể", "Trung cấp"),
    # cao cấp
    ("-(으)ㄹ 뿐만 아니라", "không những… mà còn", "Cao cấp"),
    ("-기 마련이다", "lẽ đương nhiên", "Cao cấp"),
    ("-는 한", "chừng nào còn", "Cao cấp"),
    ("-(으)ㄹ 리가 없다", "không thể nào", "Cao cấp"),
    ("-는 셈이다", "coi như là", "Cao cấp"),
    ("-(으)ㄴ/는 탓에", "tại vì (đổ lỗi)", "Cao cấp"),
    ("-고 말다", "rốt cuộc thì (lỡ)", "Cao cấp"),
    ("-(으)ㄹ 따름이다", "chỉ… mà thôi", "Cao cấp"),
    ("-기 십상이다", "dễ bị, rất dễ", "Cao cấp"),
    ("-는 법이다", "vốn dĩ là", "Cao cấp"),
    ("-(으)ㄹ망정", "thà… chứ không", "Cao cấp"),
    ("-건만", "vậy mà", "Cao cấp"),
    ("-다시피", "như… (đã biết)", "Cao cấp"),
    ("-는 둥 마는 둥", "làm qua loa, nửa vời", "Cao cấp"),
]
POINTS = [{"no": i + 1, "form": f, "vi": v, "stage": s} for i, (f, v, s) in enumerate(SYLLABUS)]
BY_NO = {p["no"]: p for p in POINTS}

PLAN_SIZE = 60       # câu / buổi (người dùng chọn ~60)
NEW_POINTS = 3       # điểm ngữ pháp mới / buổi
REVIEW_POINTS = 2    # điểm ôn lại / buổi
PER_NEW = 8          # câu cho mỗi điểm mới
PER_REVIEW = 4       # câu cho mỗi điểm ôn
VOCAB_KINDS = ("ko2vi", "vi2ko", "cloze", "trans", "hanviet")

PLAN_PROMPT = """Soạn {n} câu hỏi trắc nghiệm luyện NGỮ PHÁP tiếng Hàn cho người Việt, tất cả xoay quanh đúng điểm ngữ pháp:
{form} — {vi}

Mỗi câu là một câu tiếng Hàn tự nhiên, ngắn (dưới 40 ký tự), dùng đúng điểm ngữ pháp trên, đủ đa dạng về động từ / tính từ / \
ngôi / thì. Nếu hợp thì dùng các từ vựng sau: {vocab}.
Xen kẽ 2 dạng, khoảng một nửa mỗi dạng:
- "gram": khoét phần ngữ pháp {form} trong câu. "target": cụm (eojeol) nguyên văn trong câu có chứa ngữ pháp; "answer": phần \
ngữ pháp đã chia, là chuỗi con nằm ở CUỐI target (vd target "비가 오면" thì không hợp lệ vì có dấu cách — chọn target "오면", \
answer "면"); "distractors": 3 phương án ngữ pháp dễ nhầm với {form}, khi thay vào thì câu SAI NGỮ PHÁP hoặc không còn đúng \
nghĩa câu "vi"; không phương án nào cũng đúng.
- "gfix": "wrong": 3 câu gần giống câu đúng nhưng dùng sai {form} (sai chia, sai kết hợp, nhầm với ngữ pháp gần nghĩa), \
đúng lỗi người học hay mắc; cấm lỗi vô nghĩa như lặp âm tiết; không câu nào lại đúng.
Mỗi câu kèm "vi" (dịch tiếng Việt tự nhiên) và "point" (giải thích ≤ 60 ký tự tiếng Việt, nêu vì sao đúng).
Trả về JSON: {{"items":[{{"type":"gram","ko":"","vi":"","target":"","answer":"","distractors":["","",""],"point":""}},\
{{"type":"gfix","ko":"","vi":"","wrong":["","",""],"point":""}}]}}"""

PLAN_VERIFY = """Kiểm tra kỹ các câu hỏi ngữ pháp tiếng Hàn sau (điểm ngữ pháp: {form}) như biên tập viên đề thi.
- Câu "ko" phải tự nhiên, đúng ngữ pháp, đúng nghĩa "vi"; sửa nếu sai.
- gram: target là chuỗi con nguyên văn của "ko", answer nằm cuối target; mỗi distractor thay vào phải làm câu sai \
(sai ngữ pháp hoặc sai nghĩa "vi"); phương án nào vẫn đúng thì thay.
- gfix: mỗi câu trong wrong phải thật sự sai (đúng 1 lỗi người học hay mắc); câu nào lỡ đúng thì viết lại.
Giữ nguyên số lượng và thứ tự. Trả về JSON cùng schema.
{data}"""


# ---------------------------------------------------------------- dữ liệu
def taught() -> set[int]:
    """Các điểm ngữ pháp đã có trong một buổi nào đó (là điểm mới của buổi đó)."""
    out = set()
    for r in db.q("SELECT data FROM live_plans"):
        for p in json.loads(r["data"]).get("points", []):
            if p.get("new"):
                out.add(p["no"])
    return out


def next_points(k: int = NEW_POINTS) -> list[int]:
    done = taught()
    return [p["no"] for p in POINTS if p["no"] not in done][:k]


def save(plan: dict) -> int:
    with db.tx() as c:
        cur = c.execute("INSERT INTO live_plans(day,title,data) VALUES(?,?,?)",
                        (plan["day"], plan["title"], json.dumps(plan, ensure_ascii=False)))
        return cur.lastrowid


def load(pid: int) -> dict | None:
    r = db.q1("SELECT id, day, title, data, created_at FROM live_plans WHERE id=?", (pid,))
    if not r:
        return None
    p = json.loads(r["data"])
    p.update(id=r["id"], created_at=r["created_at"])
    return p


def update(pid: int, plan: dict):
    with db.tx() as c:
        c.execute("UPDATE live_plans SET data=? WHERE id=?", (json.dumps(plan, ensure_ascii=False), pid))


def delete(pid: int):
    with db.tx() as c:
        c.execute("DELETE FROM live_plans WHERE id=?", (pid,))
    a = active()
    if a and a["id"] == pid:
        stop()


def listing() -> list[dict]:
    out = []
    for r in db.q("SELECT id, day, title, data, created_at FROM live_plans ORDER BY id DESC LIMIT 60"):
        p = json.loads(r["data"])
        qs = p.get("questions", [])
        out.append({"id": r["id"], "day": r["day"], "title": r["title"], "created_at": r["created_at"],
                    "points": p.get("points", []), "total": len(qs),
                    "grammar": sum(1 for q in qs if q["mode"] in ("gram", "gfix"))})
    return out


def active() -> dict | None:
    return db.get_conf("plan_active")


def run(pid: int, pos: int = 0) -> bool:
    p = load(pid)
    if not p or not p.get("questions"):
        return False
    db.set_conf("plan_active", {"id": pid, "pos": max(0, min(pos, len(p["questions"]) - 1))})
    return True


def stop():
    db.set_conf("plan_active", None)


def next_question() -> tuple[dict | None, bool]:
    """(câu tiếp theo của buổi đang chạy, vừa chạy hết?). Không có buổi nào đang chạy -> (None, False)."""
    a = active()
    if not a:
        return None, False
    p = load(a["id"])
    if not p or a["pos"] >= len(p.get("questions", [])):
        stop()
        return None, bool(p)
    q = copy.deepcopy(p["questions"][a["pos"]])
    db.set_conf("plan_active", {"id": a["id"], "pos": a["pos"] + 1})
    return q, False


# ---------------------------------------------------------------- soạn buổi
def _grammar(point: dict, n: int, vocab: list[dict], cfg: dict, key: str, chat) -> list[dict]:
    provider = cfg["provider"]
    model = cfg["model_deepseek"] if provider == "deepseek" else cfg["model_openai"]
    voc = ", ".join(f"{w['korean']} ({w['vietnamese']})" for w in vocab[:20]) or "(tuỳ ý)"
    data = chat(provider, model, key, ai.SYSTEM, PLAN_PROMPT.format(n=n + 2, form=point["form"], vi=point["vi"], vocab=voc))
    items = [i for i in data.get("items", []) if isinstance(i, dict)]
    if cfg.get("verify") and items:
        v = chat(provider, model, key, ai.SYSTEM,
                 PLAN_VERIFY.format(form=point["form"], data=json.dumps({"items": items}, ensure_ascii=False)))
        vi = [i for i in v.get("items", []) if isinstance(i, dict)]
        if len(vi) == len(items):
            items = vi
    out = []
    for it in items:
        ko, vi_ = str(it.get("ko") or "").strip(), str(it.get("vi") or "").strip()
        if not ko or not vi_ or not ai.HANGUL.search(ko):
            continue
        w = {"id": 0, "korean": ko, "vietnamese": vi_, "romanization": "", "hanviet": "", "pos": "",
             "example_ko": ko, "example_vi": vi_}
        if it.get("type") == "gram":
            c = ai.clean_gram(w, it)
            q = live.build_gram(w, c) if c else None
        else:
            c = ai.clean_gfix(w, it)
            q = live.build_gfix(w, c) if c else None
        if q:
            q["point_no"], q["point_form"] = point["no"], point["form"]
            out.append(q)
    return out[:n]


def _vocab(words: list[dict], items: dict, n: int) -> list[dict]:
    used, out = set(), []
    for i in range(n * 3):
        if len(out) >= n:
            break
        q = live.make_question(random.choice(VOCAB_KINDS), words, used, items)
        if q and q["word_id"] not in used:
            used.add(q["word_id"])
            out.append(q)
    return out


def _interleave(gram: list[dict], vocab: list[dict]) -> list[dict]:
    """Đan đều 2 danh sách (giữ thứ tự từng danh sách): câu ngữ pháp và câu từ vựng xen nhau."""
    out, gi, vi = [], 0, 0
    while gi < len(gram) or vi < len(vocab):
        take_g = vi >= len(vocab) or (gi < len(gram) and gi / max(1, len(gram)) <= vi / max(1, len(vocab)))
        if take_g:
            out.append(gram[gi]); gi += 1
        else:
            out.append(vocab[vi]); vi += 1
    return out


def create(words: list[dict], items: dict, cfg: dict, key: str, chat=None, new: list[int] | None = None,
           day: str | None = None, size: int = PLAN_SIZE) -> dict:
    """Soạn 1 buổi: điểm mới (mặc định: 3 điểm kế tiếp trong giáo trình) + 2 điểm ôn + câu từ vựng. Trả về plan đã lưu."""
    chat = chat or ai._chat
    new = [n for n in (new or next_points()) if n in BY_NO]
    if not new:
        raise ai.AIError("Đã học hết giáo trình ngữ pháp")
    done = sorted(taught() - set(new))
    review = random.sample(done, min(REVIEW_POINTS, len(done)))
    pts = [dict(BY_NO[n], new=True) for n in new] + [dict(BY_NO[n], new=False) for n in review]
    jobs = [(BY_NO[n], PER_NEW) for n in new] + [(BY_NO[n], PER_REVIEW) for n in review]
    vocab_hint = random.sample(words, min(len(words), 40))
    gram: list[dict] = []
    errors = []
    with ThreadPoolExecutor(max_workers=min(5, len(jobs))) as ex:
        futs = [ex.submit(_grammar, pt, n, random.sample(vocab_hint, len(vocab_hint)), cfg, key, chat) for pt, n in jobs]
        for f in futs:
            try:
                gram += f.result()
            except ai.AICreditError:
                raise
            except Exception as e:    # 1 điểm ngữ pháp lỗi: các điểm khác vẫn dùng được
                errors.append(e)
    if not gram:
        raise errors[0] if errors else ai.AIError("AI không soạn được câu ngữ pháp nào")
    vocab = _vocab(words, items, max(0, size - len(gram)))
    qs = _interleave(gram, vocab)
    day = day or datetime.date.today().isoformat()
    title = " · ".join(BY_NO[n]["form"] for n in new)
    plan = {"day": day, "title": title, "points": pts, "questions": qs}
    pid = save(plan)
    for i, q in enumerate(qs):          # câu ngữ pháp tự đặt: không có âm thanh HanSong -> đọc bằng TTS riêng của buổi
        if q["mode"] in ("gram", "gfix"):
            q["word_id"] = -(pid * 1000 + i)
            q["audio_reveal"] = "none"
            q["audio_url"] = f"/audio/plan/{pid}/{i}.mp3"
    update(pid, plan)
    plan["id"] = pid
    return plan
