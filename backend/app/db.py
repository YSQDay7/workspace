from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

engine = create_engine(
    config.MYSQL_URL,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(32), default="user", nullable=False)
    work_no = Column(String(64), nullable=True, index=True)
    original_role = Column(String(32), nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    mobile = Column(String(32), nullable=True)
    dingtalk_user_id = Column(String(128), nullable=True)
    status = Column(String(16), default="offline", nullable=False)
    last_heartbeat = Column(DateTime, nullable=True)
    away_since = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_id = Column(Integer, nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)
    target_type = Column(String(64), nullable=True)
    target_id = Column(Integer, nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(128), default="新对话", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)
    sender_type = Column(String(16), default="user", nullable=False)
    content = Column(Text, nullable=False)
    sources = Column(Text, nullable=True)
    meta = Column(Text, nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class QuestionLog(Base):
    __tablename__ = "question_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    question = Column(Text, nullable=False)
    normalized = Column(String(256), nullable=False, index=True)
    hit = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class HandoverTicket(Base):
    __tablename__ = "handover_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    status = Column(String(32), default="queued", nullable=False, index=True)
    priority = Column(Integer, default=1, nullable=False)
    assignee_id = Column(Integer, nullable=True, index=True)
    reason = Column(String(512), nullable=True)
    rating = Column(Integer, nullable=True)
    rating_comment = Column(String(512), nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    assigned_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("handover_tickets.id"), nullable=False, index=True)
    agent_id = Column(Integer, nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)


class SatisfactionRating(Base):
    __tablename__ = "satisfaction_ratings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("handover_tickets.id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=True)
    score = Column(Integer, nullable=False)
    comment = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class DingtalkNotifyLog(Base):
    __tablename__ = "dingtalk_notify_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, nullable=True, index=True)
    target = Column(String(256), nullable=True)
    status = Column(String(32), nullable=False)
    error = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for statement in (
            "ALTER TABLE users ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'user'",
            "ALTER TABLE messages ADD COLUMN sender_type VARCHAR(16) NOT NULL DEFAULT 'user'",
            "ALTER TABLE users ADD COLUMN work_no VARCHAR(64) NULL",
            "ALTER TABLE users ADD COLUMN original_role VARCHAR(32) NULL",
            "ALTER TABLE users ADD COLUMN deleted_at DATETIME NULL",
            "ALTER TABLE users ADD COLUMN deleted_by INT NULL",
            "ALTER TABLE handover_tickets ADD COLUMN deleted TINYINT(1) NOT NULL DEFAULT 0",
        ):
            try:
                conn.execute(text(statement))
            except Exception:
                pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
