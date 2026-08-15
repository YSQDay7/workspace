import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USERNAME_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9_]{3,32}$")
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)\S{8,32}$")

_sensitive_cache: list[str] | None = None


def _sensitive_words() -> list[str]:
    global _sensitive_cache
    if _sensitive_cache is None:
        path = DATA_DIR / "sensitive_words.txt"
        if path.exists():
            _sensitive_cache = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            _sensitive_cache = []
    return _sensitive_cache


def validate_username(username: str) -> tuple[bool, str]:
    username = (username or "").strip()
    if not USERNAME_RE.fullmatch(username):
        return False, "用户名需为 3-32 位，仅支持中文、字母、数字和下划线"
    lowered = username.lower()
    for word in _sensitive_words():
        if word.lower() in lowered:
            return False, "用户名包含敏感词，请更换"
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    if not password or not PASSWORD_RE.fullmatch(password):
        return False, "密码需为 8-32 位，必须包含字母和数字，且不能包含空格"
    return True, ""
