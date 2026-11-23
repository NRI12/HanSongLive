"""Chuẩn hoá chữ để so đáp án (giữ giống HanSong srs.norm_ko)."""
import re
import unicodedata


def norm_ko(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "")
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[\s\.\,\!\?\~\-·…'\"]", "", s)


def norm_vi(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower()
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"[^\w]+", " ", s).strip()
