import io
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, ImageDraw, ImageFont

from . import config
from .db import SessionLocal, User
from .redis_client import get_redis

_bearer = HTTPBearer(auto_error=False)
CAPTCHA_CHARS = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_ACCESS_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def create_refresh_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=config.JWT_REFRESH_EXPIRE_DAYS),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def decode_refresh_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
        return payload if payload.get("type") == "refresh" else None
    except jwt.PyJWTError:
        return None


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效")
    redis = get_redis()
    if redis.get(f"jwt:blacklist:{payload.get('jti', '')}"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效")
    db = SessionLocal()
    try:
        user = db.get(User, int(payload["sub"]))
    finally:
        db.close()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if user.role == "deleted":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已删除")
    return user


def get_optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User | None:
    if credentials is None:
        return None
    payload = decode_token(credentials.credentials)
    if payload is None:
        return None
    db = SessionLocal()
    try:
        user = db.get(User, int(payload["sub"]))
    except Exception:
        user = None
    finally:
        db.close()
    return user


def get_current_agent(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("customer_service", "admin"):
        raise HTTPException(status_code=403, detail="无客服权限")
    return user


def get_current_customer_service(user: User = Depends(get_current_user)) -> User:
    if user.role != "customer_service":
        raise HTTPException(status_code=403, detail="需要客服权限")
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def logout_token(credentials: HTTPAuthorizationCredentials) -> None:
    payload = decode_token(credentials.credentials)
    if payload is None:
        return
    exp = payload.get("exp")
    ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp())) if exp else 3600
    get_redis().setex(f"jwt:blacklist:{payload.get('jti', '')}", ttl, "1")


def generate_captcha() -> tuple[str, str]:
    code = "".join(random.choices(CAPTCHA_CHARS, k=4))
    width, height = 132, 46
    image = Image.new("RGB", (width, height), (247, 251, 250))
    draw = ImageDraw.Draw(image)
    for _ in range(6):
        draw.line(
            [
                (random.randint(0, width), random.randint(0, height)),
                (random.randint(0, width), random.randint(0, height)),
            ],
            fill=(random.randint(140, 210), random.randint(160, 220), random.randint(160, 220)),
            width=1,
        )
    for _ in range(40):
        draw.point(
            (random.randint(0, width), random.randint(0, height)),
            fill=(random.randint(120, 200), random.randint(120, 200), random.randint(120, 200)),
        )
    try:
        font = ImageFont.load_default(size=30)
    except TypeError:
        font = ImageFont.load_default()
    x = 14
    for char in code:
        draw.text(
            (x, random.randint(4, 12)),
            char,
            font=font,
            fill=(random.randint(30, 90), random.randint(60, 120), random.randint(90, 140)),
        )
        x += 27
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    captcha_id = uuid.uuid4().hex
    get_redis().setex(f"captcha:{captcha_id}", config.CAPTCHA_TTL_SECONDS, code.lower())
    import base64

    image_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return captcha_id, f"data:image/png;base64,{image_base64}"


def verify_captcha(captcha_id: str, captcha_code: str) -> bool:
    if not captcha_id or not captcha_code:
        return False
    redis = get_redis()
    key = f"captcha:{captcha_id}"
    stored = redis.get(key)
    if stored is None:
        return False
    redis.delete(key)
    return stored == captcha_code.strip().lower()
