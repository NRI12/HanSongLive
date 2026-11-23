# HanSongLive

Trò chơi đoán từ tiếng Hàn trên TikTok LIVE. Người xem comment A/B/C/D, overlay dọc 1080×1920 đưa vào TikTok LIVE Studio hoặc OBS.

## Ranh giới
- Project độc lập. **Không sửa** `/home/nri12/demo/HanSong`, không import code và không đọc DB của nó. Muốn dùng logic của HanSong thì **chép** sang (như `norm.py`, `ai.py`), không import.
- Dữ liệu (từ vựng, âm thanh) chỉ lấy qua HTTP API của HanSong: `POST /api/login`, `GET /api/words?source=`, `GET /api/audio/{id}/{ko_word|vi_word|mix}.mp3`. Chi tiết trong `app/source.py`.
- Hàm chuẩn hoá chữ trong `app/norm.py` là bản chép từ `srs.norm_ko` của HanSong. `_chat`, `tts` và cách chia lô chạy song song trong `app/ai.py` là bản chép từ `server/app/ai.py` của HanSong (đã đổi để nhận key qua tham số). Nếu bên HanSong đổi thì chép lại.
- Audio lấy qua proxy gồm `ko_word`, `vi_word`, `mix`, `ko_ex`, `vi_ex` (`AUDIO_PARTS` trong `source.py`). HanSong thật có đủ câu ví dụ và audio câu ví dụ cho mọi từ.

## Stack, lệnh
- Python 3.12, FastAPI, SQLite (`data/live.db`), thư viện `TikTokLive==7.0.1`. Frontend dùng JS thuần, không có bước build.
- Cài: `uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements-dev.txt`
- Test: `.venv/bin/python -m pytest -q tests` (không cần mạng, HanSong và TikTok đều được giả lập)
- Chạy: `.venv/bin/uvicorn app.main:app --port 8100`. Trang: `/admin` và `/overlay?k=<token>`.

## Kiến trúc
- `app/tiktok.py`: payload của SDK chỉ nằm trong file này. `normalize()` đổi sang dict chuẩn `{type, user:{id,name}, ...}`. Tự kết nối lại tối đa 6 lần.
- `app/live.py`: `LiveGame` là engine thuần, nhận đồng hồ qua tham số. Các phase: idle → question → reveal → (board) → question. Mọi thay đổi trạng thái đều phải giữ `self.lock`.
  - Vòng đặc biệt `self.special`: `boss` (x3 điểm, thời gian còn 60%) hoặc `listen` (ép `ko2vi`, ẩn đề và phiên âm trong `state()`). Thứ tự ưu tiên trong `_next_question`: `self.queued` (admin hoặc đủ mốc quà) → `boss_every` → bình chọn "nghe" hoặc `listen_every`.
  - Bình chọn mở khi vào phase board (`self.vote`), đóng ở đầu `_next_question`. Kết quả nằm trong `vote_mode` và giữ đến lần hiện bảng kế tiếp.
  - Đội: lệnh `đội đỏ`/`đội xanh` được so qua `plain()` (bỏ dấu) và không cho đổi đội. Lệnh đội phải có tiền tố để không trùng với đáp án như "đỏ".
  - Mốc tim, chia sẻ, kim cương đều dùng chung `_goal()`. Dòng feed có `alert=True` (kèm `tier` 1–3) thì overlay hiện thông báo lớn.
  - `config` mới đều phải có trong `DEFAULT_CONFIG` và `LIMITS`. `clean_config` luôn trộn với `DEFAULT_CONFIG` nên cấu hình cũ trong DB vẫn đọc được.
- Dạng câu (`mode` trong config): `ko2vi`, `vi2ko`, `mix`, `cloze` (khoét chỗ trống trong câu ví dụ), `trans` (chọn bản dịch đúng của câu ví dụ), `hanviet` (chọn âm Hán Việt), `all` (trộn). Hàm thuần `live.make_question(mode, words, recent, items)` chọn từ rồi gọi `build_*`. Kiểu nào thiếu dữ liệu thì thử kiểu khác, cuối cùng quay về `ko2vi`. Câu hỏi có thể kèm `hint`, `audio_q` (None thì không đọc đề) và `audio_reveal`. Thêm dạng mới thì làm 4 việc: viết `build_x`, thêm vào `KINDS`/`MODES`, thêm `ASK`/`OPT_LANG` trong `overlay.js`, thêm option trong `admin.html`.
- `app/ai.py`: sinh nội dung cho `cloze` và `trans` (đáp án nhiễu, bản dịch sai) từ câu ví dụ, có thể kiểm duyệt lần 2. `clean_cloze`/`clean_trans` loại những mục AI làm sai (answer không nằm trong câu, trùng đáp án đúng, thiếu 3 nhiễu). Kết quả lưu ở `live_items` kèm chữ Hàn của từ: nếu bên HanSong đổi từ ở id đó thì mục cũ tự bị bỏ qua. Job chạy nền trong `main.run_ai_job`, trạng thái nằm ở `AI_JOB`. Test giả lập `chat`, không gọi AI thật.
- `app/db.py`: các bảng `live_players` (tổng mọi thời đại, có cột `diamonds` thêm bằng `_migrate`), `live_weekly` (theo tuần ISO), `live_rounds` (thống kê từng câu, dùng cho `/api/stats`), `live_items` (nội dung AI, khoá `(word_id, kind)`). Thêm cột mới thì phải viết migration trong `_migrate`.
- `app/main.py`: API, xác thực và vòng `ticker()` gọi `GAME.tick()` mỗi 0,25 giây. Chế độ thử dùng `/api/mock` (có trường `diamonds`). `/api/game` nhận thêm các action `boss|listen|double`.
- Overlay hỏi `/api/overlay/state` mỗi 400ms. Âm thanh: câu mới thì đọc đề, khi `question.replay` tăng (có quà lớn) thì đọc lại, hiện đáp án thì phát bản `mix` 2 luồng. Thông báo lớn chỉ hiện cho dòng feed mới, không hiện lại dòng cũ khi vừa mở overlay. Banner hướng dẫn được tạo từ `config` và đổi mỗi 6 giây.

## Quy tắc
- Quà chỉ tạo hiệu ứng cố định có lợi cho cả phòng hoặc để trang trí, **không bao giờ quy ra điểm** (cả điểm cá nhân lẫn điểm đội). Đây là quy định của TikTok. Các hiệu ứng hiện có: loại 1 đáp án sai, +10 giây kèm đọc lại đề (`gift_big`), nhà tài trợ câu kế tiếp (`gift_huge`), đủ mốc kim cương chung (`gift_goal`) thì mở câu boss. Có test kiểm tra quà không làm tăng điểm.
- Khoá ký TikTok, mật khẩu HanSong và API key AI (`ai.openai_key`, `ai.deepseek_key` trong DB, hoặc `OPENAI_API_KEY`/`DEEPSEEK_API_KEY` trong env) chỉ được ghi vào, không bao giờ trả về qua API, không log, không commit. Admin chỉ thấy `has_*_key`.
- Chữ trên giao diện viết bằng tiếng Việt.
- Đổi bố cục overlay thì phải chụp lại khung 540×960 ở các màn: câu hỏi, đáp án, bảng xếp hạng (cả khi có và không có bình chọn), câu boss, câu nghe, thông báo quà, và 3 dạng điền chỗ trống, dịch câu (4 đáp án dài, 1 cột), Hán Việt. Kiểm tra không bị tràn khi có 12 người chơi trở lên và khi tên dài (feed, top, thông báo đều cắt bằng dấu …).

## Chạy thật (phát live)
- HanSong thật chạy trên Vultr (instance `hansong`) ở https://45-76-191-34.sslip.io (Docker `/opt/hansong`, `ssh root@45.76.191.34`), có khoảng 300 từ. File `.env` ở local đã được điền đủ: URL, mật khẩu HanSong, key DeepSeek/OpenAI (chép từ `/opt/hansong/.env`), `LIVE_PASSWORD`, `LIVE_SECRET`.
- Cấu hình (máy mới): `cp .env.example .env`, điền `LIVE_PASSWORD`, `LIVE_SECRET` (`openssl rand -hex 32`), `HANSONG_URL`, `HANSONG_PASSWORD`, `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`. Sau đó chạy `set -a; . ./.env; set +a` rồi khởi động uvicorn, hoặc dùng `docker compose up -d --build`. Nếu chạy trên VPS sau HTTPS thì thêm `COOKIE_SECURE=1`.
- Trước khi lên sóng: vào `/admin`, bấm **Kiểm tra kết nối** HanSong (số từ phải lớn hơn 0). Ở mục **🤖 AI tạo câu hỏi**, bấm **✨ Tạo câu hỏi** (mặc định dùng DeepSeek, 30 từ mất khoảng 1 phút) để có dữ liệu cho dạng điền chỗ trống và dịch câu. Sau đó bật **Chế độ thử**, bấm **Bắt đầu** và thử các nút giả lập.
- Overlay: chép link trong admin vào TikTok LIVE Studio (Liên kết/Trình duyệt) hoặc OBS Browser Source, kích thước 1080×1920. Với OBS thì tích "Control audio via OBS". Thêm `&bg=0` nếu muốn nền trong suốt.
- Thứ tự lên sóng: phát LIVE trên TikTok trước (app chỉ kết nối được khi tài khoản đang live). Sau đó trong admin nhập tài khoản, bấm **Kết nối TikTok**, chờ trạng thái "đã kết nối" rồi mới bấm **Bắt đầu**. Nếu bị chặn thì dán khoá ký Euler (eulerstream.com).
- Buổi live đầu tiên: dùng tài khoản phụ, nhờ người tặng một món quà từ 5💎 trở lên, rồi kiểm tra bằng `sqlite3 data/live.db "select name,gifts,diamonds from live_players order by updated_at desc limit 5"`. Nếu `diamonds` bằng `gifts` thì SDK không gửi `diamond_count`, cần sửa `normalize()` trong `app/tiktok.py`.

## Chạy thử end-to-end ở local
- Không có dữ liệu HanSong thật ở local. Muốn thử thì tạo một HanSong tạm có `DATA_DIR` trỏ vào thư mục tạm, chèn từ vào DB và dùng âm `ffmpeg sine` làm âm thanh giả, rồi chạy HanSong ở cổng 8000 với `APP_PASSWORD`.
- Muốn chụp màn hình bằng dữ liệu thật mà không làm bẩn bảng điểm: sao lưu `data/live.db` sang thư mục tạm (`sqlite3.backup`) rồi chạy một server thứ hai với `DATA_DIR=<tạm>` ở cổng 8101. Máy không có lệnh `sqlite3`, dùng Python để đọc DB.
- Có thể dùng một HanSong giả nhỏ (FastAPI phục vụ `/api/login`, `/api/words`, `/api/audio/...`) đặt trong scratchpad thay cho HanSong thật.
- Chụp màn hình bằng `google-chrome --headless=new --virtual-time-budget=2000 --window-size=540,960 --screenshot=...`. Playwright có sẵn ở `/home/nri12/betaka/tu-tien-online/node_modules/playwright` nhưng không có trình duyệt riêng, nên phải truyền `chromium.launch({executablePath: "/usr/bin/google-chrome"})`. Muốn chụp thông báo lớn thì dùng Playwright: mở overlay trước rồi mới gửi sự kiện.
- Tắt server bằng `fuser -k 8100/tcp`, **không dùng** `pkill -f "port 8100"` vì lệnh này khớp với chính shell đang chạy và tắt luôn nó.

## Trạng thái
- Đã xong: engine, admin, overlay, chế độ thử, proxy và cache âm thanh, xác thực, Docker. Đợt nâng cấp tương tác đã xong: tỉ lệ đáp án trực tiếp, quà chia mức, mốc quà và chia sẻ, câu boss, câu nghe, đội, bình chọn, chuỗi đúng, Vua tuần và Fan cứng, banner hướng dẫn, nút đặt trước vòng đặc biệt, thống kê theo câu. Đã chép AI từ HanSong, thêm 3 dạng câu (điền chỗ trống, dịch câu, Hán Việt). Đã chạy thử AI thật (DeepSeek, có kiểm duyệt) với 12 từ: tạo được 24/24 câu và chất lượng tốt. Có 19 test, tất cả đều qua.
- Mã nguồn: git, remote `git@github.com:NRI12/HanSongLive.git` (private). Máy không có `gh`, SSH push được với tài khoản NRI12.
- Chưa kiểm chứng: nhận comment và quà từ một phiên TikTok LIVE thật. Mới chỉ thử trường hợp tài khoản chưa live (app báo lỗi đúng và tự thử lại). Đặc biệt cần xác nhận `gift.diamond_count` có giá trị thật. Nếu không có thì mọi quà bị tính 1 kim cương/món và các mức `gift_big`/`gift_huge` sẽ không bao giờ đạt.
