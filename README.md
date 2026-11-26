# HanSongLive: game "Săn Quái Chữ" tiếng Hàn trên TikTok LIVE

Project chạy độc lập, tách khỏi HanSong. Từ vựng và âm thanh được lấy qua HTTP API của một máy chủ HanSong
(chỉ cần địa chỉ + mật khẩu). Không đọc DB và không import code của HanSong.

Cách làm giống tu-tien-online: kết nối TikTok → chuẩn hoá sự kiện → engine trò chơi → màn hình overlay.

## Cách chơi (hiện trên live)
Cả phòng cùng đánh quái bằng cách trả lời câu hỏi tiếng Hàn, leo ải càng cao càng tốt.
- Mỗi ải có 1 con quái (ghép ngẫu nhiên nên con nào cũng khác). Mỗi câu là 1 lượt đánh: người xem **comment A/B/C/D**
  (hoặc 1–4, hoặc gõ thẳng đáp án). Mỗi người chỉ được tính câu trả lời đầu tiên.
- Trả lời đúng gây **sát thương** = điểm: +10, nhanh thêm tối đa +10, người đúng đầu tiên +5 (**CHÍ MẠNG**), đúng liên tiếp từ 3 câu cộng thêm điểm chuỗi (tối đa +10).
  Máu quái chỉ tụt lúc hiện đáp án (từng đòn bay lên kèm tên người đánh), để trong lúc hỏi không lộ ai đúng.
- Cả phòng có **tim chung** (mặc định 5). Có người trả lời mà dưới 50% đúng thì quái **phản đòn**, mất tim. Hết tim: cả phòng bị hạ,
  quay về ải đầu vùng và hồi đầy tim. Không ai trả lời thì quái không đánh.
- 👹 Cứ 5 ải có 1 **BOSS** (nhiều máu, 🔥 cuồng nộ: phản đòn mất 2 tim). Hạ boss xong sang **vùng mới** (đổi cảnh nền) và đó là điểm hồi sinh mới.
- **Đặc tính quái**: ⚡ Nhanh nhẹn (ít thời gian), 👻 Tàng hình (câu nghe: chỉ phát tiếng Hàn, không hiện chữ), 🛡 Giáp dày (máu x1.5),
  🪞 Đảo ngược (hỏi Việt → Hàn), 💚 Tự hồi máu (hồi máu khi cả phòng đánh trượt).
- **Hạ quái**: hiện MVP (top 3 sát thương), người ra đòn kết liễu, kỷ lục ải mới. MVP đội 👑 tới khi hạ con quái sau.
  Rồi cả phòng comment `1/2/3` để **chọn cửa** = đặc tính của quái kế tiếp.
- **Cấp độ + danh hiệu** tính từ tổng sát thương mọi thời đại: 🌱 Tân binh → 🗡 Kiếm sĩ → 🛡 Hiệp sĩ → 🔮 Pháp sư → ⭐ Anh hùng → 👑 Huyền thoại.
  Gõ `điểm` để xem sát thương, hạng và cấp của mình.
- ❤️ **Tim**: đủ mốc (mặc định 300 tim) thì câu sau x2 sát thương. 🔁 **Chia sẻ**: đủ mốc (mặc định 10 lượt) thì hồi 1 tim cho cả phòng.
- 🎁 **Quà tặng không có tác dụng gì trong game** (chỉ được ghi nhận vào DB). Game thu hút người xem bằng lối chơi, không bằng quà.
- 🔥 Thông báo lớn khi có người đúng liên tiếp 5, 10, 15… câu, khi lên danh hiệu mới, khi lập kỷ lục.
- Banner cuối màn hình thay đổi mỗi 6 giây để hướng dẫn người mới vào phòng.
- Trong admin có nút gọi boss cho quái sau, câu sau x2, +1 tim, chọn đặc tính quái sau, và bảng **Thống kê theo câu**.
- **Các dạng câu** (chọn trong admin, mặc định trộn tất cả):
  - Hàn → Việt, Việt → Hàn.
  - 🧩 **Điền chỗ trống**: câu ví dụ bị khoét đúng từ đang hỏi (đã chia đuôi), có kèm bản dịch làm gợi ý, chọn 1 trong 4 cụm tiếng Hàn.
  - 📝 **Dịch câu**: đọc câu ví dụ tiếng Hàn, chọn bản dịch đúng trong 4 câu.
  - 🈶 **Âm Hán Việt**: chọn âm Hán Việt của từ (chỉ dùng từ Hán Hàn).
  - Đáp án nhiễu của 2 dạng 🧩 và 📝 do AI (DeepSeek hoặc OpenAI) tạo sẵn ở mục **🤖 AI tạo câu hỏi** trong admin. Âm thanh dùng luôn bản đọc câu ví dụ bên HanSong.
- 🐰 **Bot Hami**: linh vật hoạt hình ở góc phải dưới, bình luận trận đánh (quái xuất hiện, chí mạng, phản đòn, hạ quái, lên cấp, giục khi còn 5 giây).
  Người xem gõ `bot ơi …` để hỏi về tiếng Hàn, AI trả lời ngắn trong bong bóng thoại. Bot không bao giờ để lộ đáp án câu đang hỏi.
- 📐 **Vùng an toàn**: mặc định toàn bộ nội dung nằm trong khoảng 12–62% chiều cao, không bị comment, ô nhập hay tên host của TikTok đè lên.
  Dùng nút **📐 Mở kèm khung TikTok** trong admin để căn lại `safe_top`/`safe_bottom` cho khớp điện thoại của bạn.
- Hình, hiệu ứng, âm thanh: Kenney.nl (CC0) + font Baloo 2 (OFL), xem `static/game/CREDITS.md`.

## Chạy
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements-dev.txt
cp .env.example .env     # điền LIVE_PASSWORD, HANSONG_URL, HANSONG_PASSWORD
set -a; . ./.env; set +a
.venv/bin/uvicorn app.main:app --port 8100
.venv/bin/python -m pytest -q tests   # test, không cần mạng
```
Hoặc dùng Docker: `docker compose up -d --build` (cổng 8100, dữ liệu nằm ở `./data`).

## Dùng khi phát live
1. Mở `http://localhost:8100/admin`. Ở mục **Nguồn dữ liệu HanSong**, nhập địa chỉ HanSong và mật khẩu, rồi bấm **Kiểm tra kết nối**.
2. Bấm **Chế độ thử** rồi **Bắt đầu**. Gửi vài comment giả (trả lời ngẫu nhiên, chọn cửa, tim, chia sẻ) để xem màn hình chạy đúng chưa.
3. Chép link **Màn hình LIVE**, rồi đưa vào phần mềm phát:
   - TikTok LIVE Studio: Thêm nguồn › Liên kết/Trình duyệt, kích thước 1080 × 1920.
   - OBS: Browser Source 1080 × 1920, tích "Control audio via OBS" để âm thanh đi vào luồng live.
   - Thêm `&bg=0` vào cuối link nếu muốn nền trong suốt để chồng lên camera.
4. Bắt đầu phát LIVE trên TikTok. Nhập tên tài khoản, bấm **Kết nối TikTok**, rồi bấm **Bắt đầu**.
   Nếu TikTok chặn kết nối, đăng ký khoá ký miễn phí tại eulerstream.com và dán vào ô "Khoá ký".

## Ghi chú
- Âm thanh được tải từ HanSong một lần rồi cache vào `data/audio`. Vì vậy dù mạng tới HanSong chập chờn trong lúc live,
  âm thanh vẫn phát được. Nếu đổi kiểu phát hoặc giọng đọc bên HanSong, bấm **Xoá cache âm thanh**.
- Danh sách từ được làm mới 5 phút một lần. Nếu HanSong tạm lỗi, app dùng danh sách cũ để game không bị dừng.
- Điểm của phiên live chỉ nằm trong bộ nhớ. Điểm mọi thời đại lưu ở `data/live.db`. Người xem trả lời trên live
  **không** ảnh hưởng tới lịch ôn (SRS) của bạn bên HanSong.
- Khi có đặt `LIVE_PASSWORD`: trang /admin cần đăng nhập, còn link overlay dùng token `?k=` nên dán thẳng vào OBS được.
  Không đặt mật khẩu thì mọi thứ đều mở, nên chỉ để trống khi chạy trên máy cá nhân.

## Cấu trúc
```
app/main.py     API, trang, vòng lặp game
app/live.py     engine trò chơi (thuần, test được bằng đồng hồ giả)
app/tiktok.py   kết nối TikTok (TikTokLive), chuẩn hoá sự kiện, tự kết nối lại tối đa 6 lần
app/source.py   client gọi HTTP API của HanSong, cache từ và âm thanh
static/         admin.* (bảng điều khiển), overlay.* + monster.js (màn hình live), bot.* (Hami), sfx.js
static/game/    tài nguyên CC0/OFL: quái, nền, hiệu ứng, âm thanh, font
tools/          screenshots.js: chụp mọi màn overlay để kiểm tra bố cục
```
