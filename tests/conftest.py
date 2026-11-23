import os, sys, tempfile
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="hansonglive-test-")
# Test không bao giờ dùng cấu hình thật, kể cả khi shell đã `. ./.env` (key AI thật sẽ gọi API tốn tiền).
for _k in ("LIVE_PASSWORD", "LIVE_SECRET", "HANSONG_URL", "HANSONG_PASSWORD", "TIKTOK_USERNAME", "TIKTOK_SIGN_API_KEY",
           "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "COOKIE_SECURE"):
    os.environ.pop(_k, None)
os.environ["HANSONGLIVE_OFFLINE"] = "1"     # chặn mọi lời gọi AI/TTS thật (app/ai.py::_offline)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
