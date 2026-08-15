import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth  # noqa: E402
from app.db import (  # noqa: E402
    AgentConversation,
    AgentProfile,
    AuditLog,
    Conversation,
    DingtalkNotifyLog,
    HandoverTicket,
    Message,
    QuestionLog,
    SatisfactionRating,
    SessionLocal,
    User,
)
from app.redis_client import get_redis  # noqa: E402

ADMIN_USERNAME = "root"
NEW_PASSWORD = "123456"


def clear_redis() -> None:
    redis = get_redis()
    for pattern in ("hot:*", "answer:*", "captcha:*", "jwt:blacklist:*", "escalated:*"):
        for key in redis.scan_iter(pattern, count=500):
            redis.delete(key)
    print("redis cleared")


def run() -> None:
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        if admin is None:
            admin = User(
                username=ADMIN_USERNAME,
                password_hash=auth.hash_password(NEW_PASSWORD),
                role="admin",
                work_no=ADMIN_USERNAME,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"已创建管理员账号：{ADMIN_USERNAME} / {NEW_PASSWORD}")

        deleted_users = (
            db.query(User).filter(User.username != ADMIN_USERNAME).all()
        )
        deleted_user_ids = [user.id for user in deleted_users]
        print(f"删除账号：{len(deleted_users)} 个")

        db.query(Message).delete(synchronize_session=False)
        db.query(SatisfactionRating).delete(synchronize_session=False)
        db.query(AgentConversation).delete(synchronize_session=False)
        db.query(DingtalkNotifyLog).delete(synchronize_session=False)
        db.query(HandoverTicket).delete(synchronize_session=False)
        db.query(Conversation).delete(synchronize_session=False)
        db.query(QuestionLog).delete(synchronize_session=False)
        db.query(AuditLog).delete(synchronize_session=False)
        db.query(AgentProfile).filter(AgentProfile.user_id != admin.id).delete(
            synchronize_session=False
        )
        if deleted_user_ids:
            db.query(User).filter(User.id.in_(deleted_user_ids)).delete(
                synchronize_session=False
            )

        admin.password_hash = auth.hash_password(NEW_PASSWORD)
        admin.role = "admin"
        db.commit()
        print(f"管理员密码已更新：{ADMIN_USERNAME} / {NEW_PASSWORD}")

        remaining = db.query(User).all()
        print("剩余账号：", [user.username for user in remaining])
        print(
            "剩余数据：",
            {
                "conversations": db.query(Conversation).count(),
                "messages": db.query(Message).count(),
                "tickets": db.query(HandoverTicket).count(),
                "question_logs": db.query(QuestionLog).count(),
            },
        )
    finally:
        db.close()
    clear_redis()


if __name__ == "__main__":
    run()
