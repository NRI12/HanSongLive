# HanSongLive: đoán từ tiếng Hàn trên TikTok LIVE

Project chạy độc lập, tách khỏi HanSong. Từ vựng và âm thanh được lấy qua HTTP API của một máy chủ HanSong
(chỉ cần địa chỉ + mật khẩu). Không đọc DB và không import code của HanSong.

Cách làm giống tu-tien-online: kết nối TikTok → chuẩn hoá sự kiện → engine trò chơi → màn hình overlay.

## Cách chơi (hiện trên live)
- Mỗi câu hiện 1 từ (tiếng Hàn → chọn nghĩa Việt, hoặc ngược lại) và đọc to từ đó. Người xem **comment A/B/C/D**
  (hoặc 1–4, hoặc gõ thẳng đáp án). Mỗi người chỉ được tính câu trả lời đầu tiên.
- Điểm: đúng +10, trả lời càng nhanh thưởng thêm tối đa +10, người đúng đầu tiên +5, đúng liên tiếp từ 3 câu trở lên được cộng thêm điểm chuỗi (tối đa +10).
- Hết giờ thì hiện đáp án, kèm âm Hán Việt, câu ví dụ và bản đọc 2 luồng (Việt tai trái, Hàn tai phải). Có top 3 người đúng nhanh nhất.
- Trong lúc hỏi, mỗi đáp án hiện tỉ lệ % người đang chọn (tắt được trong admin).
- Cứ mỗi N câu lại hiện bảng xếp hạng: top của phiên, kỷ lục mọi thời đại, **Vua tuần**, danh sách cảm ơn người tặng quà và **Fan cứng tuần**.
  Trong lúc hiện bảng, người xem comment `1/2/3` để chọn kiểu câu cho lượt tiếp theo (Hàn → Việt, Việt → Hàn, Nghe).
- 👹 **Câu boss** (mặc định cứ 10 câu có 1 câu): x3 điểm, thời gian còn 60%.
- 🎧 **Câu nghe** (mặc định cứ 5 câu có 1 câu): chỉ phát tiếng Hàn, không hiện chữ, người xem chọn nghĩa.
- 🔴🔵 **Đội**: comment `đội đỏ` hoặc `đội xanh` để vào đội (không được đổi đội). Điểm của mỗi người cộng cho đội của mình.
- 🔥 Thông báo lớn khi có người đúng liên tiếp 5, 10, 15… câu, và báo khi chuỗi đó bị phá.
- 🎁 **Quà** (chỉ tạo hiệu ứng cố định cho cả phòng, **không bao giờ** đổi ra điểm, theo quy định của TikTok):
  - Mọi món quà đều loại 1 đáp án sai của câu đang hỏi.
  - Quà từ `gift_big` kim cương (mặc định 30): câu đang hỏi được thêm 10 giây (tối đa +30 giây mỗi câu) và đọc lại đề.
  - Quà từ `gift_huge` kim cương (mặc định 100): tên người tặng hiện là "nhà tài trợ" của câu kế tiếp.
  - Cả phòng tặng đủ `gift_goal` kim cương (mặc định 300) thì mở một câu boss.
  - Mỗi lần tặng quà từ mức lớn trở lên đều hiện thông báo cảm ơn to giữa màn hình.
- ❤️ **Tim**: đủ mốc (mặc định 300 tim) thì câu sau được x2 điểm. 🔁 **Chia sẻ**: đủ mốc (mặc định 10 lượt) cũng được x2.
- Banner cuối màn hình thay đổi mỗi 6 giây để hướng dẫn người mới vào phòng.
- Trong admin có nút để đặt trước câu boss, câu nghe hoặc x2 cho câu kế tiếp, và bảng **Thống kê theo câu**
  (số người trả lời, số comment, người xem, tỉ lệ đúng theo từng kiểu câu).
- **Các dạng câu** (chọn trong admin, mặc định trộn tất cả):
  - Hàn → Việt, Việt → Hàn (dạng cũ).
  - 🧩 **Điền chỗ trống**: câu ví dụ bị khoét đúng từ đang hỏi (đã chia đuôi), có kèm bản dịch làm gợi ý, chọn 1 trong 4 cụm tiếng Hàn.
  - 📝 **Dịch câu**: đọc câu ví dụ tiếng Hàn, chọn bản dịch đúng trong 4 câu.
  - 🈶 **Âm Hán Việt**: chọn âm Hán Việt của từ (chỉ dùng từ Hán Hàn).
  - Đáp án nhiễu của 2 dạng 🧩 và 📝 do AI (DeepSeek hoặc OpenAI) tạo sẵn ở mục **🤖 AI tạo câu hỏi** trong admin. Âm thanh dùng luôn bản đọc câu ví dụ bên HanSong.
- 🐰 **Bot Hami**: linh vật hoạt hình ở góc phải dưới, phản ứng với mọi diễn biến (đọc đề thì nhép miệng, cảm ơn quà, nhảy khi có quà lớn, giục khi còn 5 giây, buồn khi cả phòng sai, ngủ khi tạm dừng). Người xem gõ `bot ơi …` để hỏi về tiếng Hàn, AI trả lời ngắn trong bong bóng thoại. Bot không bao giờ để lộ đáp án câu đang hỏi.
- 📐 **Vùng an toàn**: mặc định toàn bộ nội dung nằm trong khoảng 12–62% chiều cao, không bị comment, ô nhập hay tên host của TikTok đè lên. Dùng nút **📐 Mở kèm khung TikTok** trong admin để căn lại `safe_top`/`safe_bottom` cho khớp điện thoại của bạn.
- Gõ `điểm` hoặc `top` để xem điểm và hạng của mình.

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
2. Bấm **Chế độ thử** rồi **Bắt đầu**. Gửi vài comment giả để xem màn hình chạy đúng chưa.
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
static/         admin.* (bảng điều khiển), overlay.* (màn hình live)
```
