import json
from datetime import datetime

from sqlalchemy import func

from .db import (
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


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "work_no": user.work_no or user.username,
        "original_role": user.original_role,
        "deleted_at": user.deleted_at.isoformat() if user.deleted_at else None,
        "created_at": user.created_at.isoformat(),
    }


def create_user(
    username: str,
    password_hash: str,
    role: str = "user",
    work_no: str | None = None,
) -> User:
    db = SessionLocal()
    try:
        user = User(
            username=username,
            password_hash=password_hash,
            role=role,
            work_no=work_no or (username if role in ("admin", "customer_service") else None),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def get_user_by_username(username: str) -> User | None:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


def get_user_by_id(user_id: int) -> User | None:
    db = SessionLocal()
    try:
        return db.get(User, user_id)
    finally:
        db.close()


def update_user_role(user_id: int, role: str) -> User | None:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return None
        user.role = role
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def delete_user(user_id: int, deleted_by: int | None = None) -> bool:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None:
            return False
        work_no = user.work_no or user.username
        original_role = (
            "admin"
            if work_no.startswith("AD")
            else "customer_service"
            if work_no.startswith("CS")
            else "user"
        )
        user.original_role = original_role
        user.role = "deleted"
        user.deleted_at = datetime.utcnow()
        user.deleted_by = deleted_by
        db.commit()
        return True
    finally:
        db.close()


def restore_user(user_id: int) -> bool:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or user.role != "deleted":
            return False
        user.role = user.original_role or "user"
        user.original_role = None
        user.deleted_at = None
        user.deleted_by = None
        db.commit()
        return True
    finally:
        db.close()


def list_deleted_users() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(User).filter(User.role == "deleted").order_by(User.deleted_at.desc()).all()
        return [user_to_dict(user) for user in rows]
    finally:
        db.close()


def list_users(role: str | None = None, keyword: str | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        query = db.query(User).filter(User.role != "deleted")
        if role:
            query = query.filter(User.role == role)
        if keyword:
            query = query.filter(User.username == keyword)
        rows = query.order_by(User.id.asc()).all()
        return [user_to_dict(user) for user in rows]
    finally:
        db.close()


def create_conversation(user_id: int | None, title: str = "新对话") -> Conversation:
    db = SessionLocal()
    try:
        conversation = Conversation(user_id=user_id, title=title)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    finally:
        db.close()


def get_conversation(conversation_id: int) -> Conversation | None:
    db = SessionLocal()
    try:
        return db.get(Conversation, conversation_id)
    finally:
        db.close()


def get_message(message_id: int) -> Message | None:
    db = SessionLocal()
    try:
        return db.get(Message, message_id)
    finally:
        db.close()


def list_conversations(user_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
            .all()
        )
        result = []
        for row in rows:
            message_count = db.query(Message).filter(Message.session_id == row.id, Message.deleted.is_(False)).count()
            result.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                    "message_count": message_count,
                }
            )
        return result
    finally:
        db.close()




def delete_conversation(conversation_id: int, user_id: int | None) -> bool:
    db = SessionLocal()
    try:
        row = db.get(Conversation, conversation_id)
        if row is None or (row.user_id is not None and row.user_id != user_id):
            return False
        db.query(Message).filter(Message.session_id == conversation_id).delete()
        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()


def add_message(
    session_id: int,
    role: str,
    content: str,
    sources: list | None = None,
    meta: dict | None = None,
    sender_type: str | None = None,
) -> Message:
    db = SessionLocal()
    try:
        resolved_sender = sender_type or ("assistant" if role == "assistant" else "user")
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            sender_type=resolved_sender,
            sources=json.dumps(sources or [], ensure_ascii=False),
            meta=json.dumps(meta or {}, ensure_ascii=False),
        )
        db.add(message)
        conversation = db.get(Conversation, session_id)
        if conversation is not None:
            conversation.updated_at = datetime.utcnow()
            if role == "user" and len(content) > 3:
                conversation.title = content[:20]
        db.commit()
        db.refresh(message)
        return message
    finally:
        db.close()


def list_messages(session_id: int, include_deleted: bool = False) -> list[dict]:
    db = SessionLocal()
    try:
        query = db.query(Message).filter(Message.session_id == session_id)
        if not include_deleted:
            query = query.filter(Message.deleted.is_(False))
        rows = query.order_by(Message.id.asc()).all()
        return [
            {
                "id": row.id,
                "session_id": row.session_id,
                "role": row.role,
                "sender_type": row.sender_type,
                "content": row.content,
                "sources": json.loads(row.sources or "[]"),
                "meta": json.loads(row.meta or "{}"),
                "created_at": row.created_at.isoformat(),
                "deleted": row.deleted,
            }
            for row in rows
        ]
    finally:
        db.close()


def soft_delete_message(message_id: int, session_id: int | None = None) -> bool:
    db = SessionLocal()
    try:
        message = db.get(Message, message_id)
        if message is None:
            return False
        if session_id is not None and message.session_id != session_id:
            return False
        message.deleted = True
        db.commit()
        return True
    finally:
        db.close()


def log_question(
    question: str,
    normalized: str,
    hit: bool,
    session_id: int | None = None,
    user_id: int | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            QuestionLog(
                question=question,
                normalized=normalized,
                hit=hit,
                session_id=session_id,
                user_id=user_id,
            )
        )
        db.commit()
    finally:
        db.close()


def get_active_ticket(session_id: int) -> HandoverTicket | None:
    db = SessionLocal()
    try:
        return (
            db.query(HandoverTicket)
            .filter(
                HandoverTicket.session_id == session_id,
                HandoverTicket.status.in_(["queued", "assigned", "in_progress"]),
                HandoverTicket.deleted.is_(False),
            )
            .order_by(HandoverTicket.id.desc())
            .first()
        )
    finally:
        db.close()


def create_handover_ticket(
    session_id: int,
    user_id: int | None,
    reason: str | None,
    priority: int = 1,
) -> HandoverTicket:
    db = SessionLocal()
    try:
        ticket = HandoverTicket(session_id=session_id, user_id=user_id, reason=reason, priority=priority)
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket
    finally:
        db.close()


def get_ticket(ticket_id: int) -> HandoverTicket | None:
    db = SessionLocal()
    try:
        return (
            db.query(HandoverTicket)
            .filter(HandoverTicket.id == ticket_id, HandoverTicket.deleted.is_(False))
            .first()
        )
    finally:
        db.close()


def list_tickets(status: str | None = None, assignee_id: int | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        query = db.query(HandoverTicket).filter(HandoverTicket.deleted.is_(False))
        if status:
            query = query.filter(HandoverTicket.status == status)
        if assignee_id is not None:
            query = query.filter(HandoverTicket.assignee_id == assignee_id)
        rows = query.order_by(HandoverTicket.priority.desc(), HandoverTicket.created_at.asc()).all()
        return [ticket_to_dict(row) for row in rows]
    finally:
        db.close()


def delete_ticket(ticket_id: int) -> bool:
    db = SessionLocal()
    try:
        ticket = db.query(HandoverTicket).filter(HandoverTicket.id == ticket_id).first()
        if ticket is None:
            return False
        ticket.deleted = True
        db.commit()
        return True
    finally:
        db.close()


def ticket_to_dict(ticket: HandoverTicket) -> dict:
    now = datetime.utcnow()
    created = ticket.created_at or now
    wait_seconds = max(0, int((now - created).total_seconds()))
    return {
        "id": ticket.id,
        "session_id": ticket.session_id,
        "user_id": ticket.user_id,
        "status": ticket.status,
        "priority": ticket.priority,
        "assignee_id": ticket.assignee_id,
        "reason": ticket.reason,
        "rating": ticket.rating,
        "rating_comment": ticket.rating_comment,
        "created_at": ticket.created_at.isoformat(),
        "assigned_at": ticket.assigned_at.isoformat() if ticket.assigned_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        "wait_seconds": wait_seconds,
    }


def assign_ticket(ticket_id: int, agent_id: int) -> bool:
    db = SessionLocal()
    try:
        ticket = db.get(HandoverTicket, ticket_id)
        if ticket is None:
            return False
        ticket.assignee_id = agent_id
        if ticket.status in ("queued", "assigned"):
            ticket.status = "assigned"
        ticket.assigned_at = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()


def set_ticket_in_progress(ticket_id: int) -> bool:
    db = SessionLocal()
    try:
        ticket = db.get(HandoverTicket, ticket_id)
        if ticket is None:
            return False
        ticket.status = "in_progress"
        db.commit()
        return True
    finally:
        db.close()


def return_ticket(ticket_id: int) -> bool:
    db = SessionLocal()
    try:
        ticket = db.get(HandoverTicket, ticket_id)
        if ticket is None:
            return False
        ticket.status = "returned"
        db.commit()
        return True
    finally:
        db.close()


def close_ticket(ticket_id: int, rating: int | None = None, comment: str | None = None) -> bool:
    db = SessionLocal()
    try:
        ticket = db.get(HandoverTicket, ticket_id)
        if ticket is None:
            return False
        ticket.status = "closed"
        ticket.closed_at = datetime.utcnow()
        if rating is not None:
            ticket.rating = rating
            ticket.rating_comment = comment
            db.add(
                SatisfactionRating(
                    ticket_id=ticket.id,
                    user_id=ticket.user_id,
                    score=rating,
                    comment=comment,
                )
            )
        db.commit()
        return True
    finally:
        db.close()


def rate_ticket(ticket_id: int, user_id: int | None, score: int, comment: str | None) -> bool:
    db = SessionLocal()
    try:
        ticket = db.get(HandoverTicket, ticket_id)
        if ticket is None or ticket.user_id != user_id:
            return False
        ticket.rating = score
        ticket.rating_comment = comment
        db.add(
            SatisfactionRating(
                ticket_id=ticket.id,
                user_id=user_id,
                score=score,
                comment=comment,
            )
        )
        db.commit()
        return True
    finally:
        db.close()


def log_dingtalk_notify(ticket_id: int | None, target: str | None, status: str, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(DingtalkNotifyLog(ticket_id=ticket_id, target=target, status=status, error=error))
        db.commit()
    finally:
        db.close()


def agent_stats(agent_id: int) -> dict:
    db = SessionLocal()
    try:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        total = db.query(HandoverTicket).filter(HandoverTicket.assignee_id == agent_id).count()
        today_count = (
            db.query(HandoverTicket)
            .filter(HandoverTicket.assignee_id == agent_id, HandoverTicket.assigned_at >= today)
            .count()
        )
        active = (
            db.query(HandoverTicket)
            .filter(HandoverTicket.assignee_id == agent_id, HandoverTicket.status == "in_progress")
            .count()
        )
        avg_rating = (
            db.query(SatisfactionRating)
            .join(HandoverTicket, SatisfactionRating.ticket_id == HandoverTicket.id)
            .filter(HandoverTicket.assignee_id == agent_id)
            .with_entities(SatisfactionRating.score)
            .all()
        )
        average_rating = round(sum(item[0] for item in avg_rating) / len(avg_rating), 2) if avg_rating else None
        return {
            "total": total,
            "today": today_count,
            "active": active,
            "average_rating": average_rating,
        }
    finally:
        db.close()


def audit_log(
    actor_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: str | None = None,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=detail,
            )
        )
        db.commit()
    finally:
        db.close()


def get_or_create_agent_profile(user_id: int) -> AgentProfile:
    db = SessionLocal()
    try:
        profile = db.query(AgentProfile).filter(AgentProfile.user_id == user_id).first()
        if profile is None:
            profile = AgentProfile(user_id=user_id, status="offline")
            db.add(profile)
            db.commit()
            db.refresh(profile)
        return profile
    finally:
        db.close()


def update_agent_profile(
    user_id: int,
    mobile: str | None = None,
    dingtalk_user_id: str | None = None,
) -> AgentProfile:
    db = SessionLocal()
    try:
        profile = db.query(AgentProfile).filter(AgentProfile.user_id == user_id).first()
        if profile is None:
            profile = AgentProfile(user_id=user_id, status="offline")
            db.add(profile)
        if mobile is not None:
            profile.mobile = mobile.strip() or None
        if dingtalk_user_id is not None:
            profile.dingtalk_user_id = dingtalk_user_id.strip() or None
        profile.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(profile)
        return profile
    finally:
        db.close()


def set_agent_status(user_id: int, status: str) -> bool:
    if status not in ("online", "away", "offline"):
        return False
    db = SessionLocal()
    try:
        profile = db.query(AgentProfile).filter(AgentProfile.user_id == user_id).first()
        if profile is None:
            profile = AgentProfile(user_id=user_id)
            db.add(profile)
        profile.status = status
        profile.last_heartbeat = datetime.utcnow()
        profile.away_since = datetime.utcnow() if status == "away" else None
        db.commit()
        return True
    finally:
        db.close()


def get_agent_status(user_id: int) -> str:
    db = SessionLocal()
    try:
        profile = db.query(AgentProfile).filter(AgentProfile.user_id == user_id).first()
        return profile.status if profile and profile.status else "offline"
    finally:
        db.close()


def agent_heartbeat(user_id: int) -> None:
    db = SessionLocal()
    try:
        profile = db.query(AgentProfile).filter(AgentProfile.user_id == user_id).first()
        if profile is None:
            profile = AgentProfile(user_id=user_id, status="online")
            db.add(profile)
        if profile.status != "away":
            profile.status = "online"
        profile.last_heartbeat = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def list_agent_profiles() -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(AgentProfile, User)
            .join(User, AgentProfile.user_id == User.id)
            .filter(User.role.in_(["customer_service", "admin"]))
            .all()
        )
        now = datetime.utcnow()
        result = []
        for profile, user in rows:
            away_minutes = (
                int((now - profile.away_since).total_seconds() // 60)
                if profile.away_since
                else 0
            )
            result.append(
                {
                    "user_id": user.id,
                    "work_no": user.work_no or user.username,
                    "username": user.username,
                    "role": user.role,
                    "mobile": profile.mobile,
                    "status": profile.status,
                    "last_heartbeat": profile.last_heartbeat.isoformat() if profile.last_heartbeat else None,
                    "away_since": profile.away_since.isoformat() if profile.away_since else None,
                    "away_minutes": away_minutes if profile.status == "away" else 0,
                }
            )
        return result
    finally:
        db.close()


def agent_tasks(agent_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(HandoverTicket)
            .filter(
                HandoverTicket.assignee_id == agent_id,
                HandoverTicket.status.in_(["assigned", "in_progress"]),
                HandoverTicket.deleted.is_(False),
            )
            .order_by(HandoverTicket.created_at.asc())
            .all()
        )
        return [ticket_to_dict(row) for row in rows]
    finally:
        db.close()


def my_rating(user_id: int) -> dict:
    db = SessionLocal()
    try:
        rows = (
            db.query(SatisfactionRating)
            .join(HandoverTicket, SatisfactionRating.ticket_id == HandoverTicket.id)
            .filter(HandoverTicket.assignee_id == user_id)
            .order_by(SatisfactionRating.created_at.desc())
            .all()
        )
        scores = [row.score for row in rows]
        average = round(sum(scores) / len(scores), 2) if scores else None
        return {
            "average": average,
            "count": len(scores),
            "recent": [{"score": row.score, "comment": row.comment, "created_at": row.created_at.isoformat()} for row in rows[:5]],
        }
    finally:
        db.close()


def agent_performance() -> list[dict]:
    profiles = {item["user_id"]: item for item in list_agent_profiles()}
    db = SessionLocal()
    try:
        agents = db.query(User).filter(User.role == "customer_service").all()
        result = []
        for agent in agents:
            rating = my_rating(agent.id)
            stats = agent_stats(agent.id)
            profile = profiles.get(agent.id, {})
            result.append(
                {
                    "user_id": agent.id,
                    "work_no": agent.work_no or agent.username,
                    "username": agent.username,
                    "mobile": profile.get("mobile"),
                    "status": profile.get("status", "offline"),
                    "away_minutes": profile.get("away_minutes", 0),
                    "away_since": profile.get("away_since"),
                    "last_heartbeat": profile.get("last_heartbeat"),
                    "total": stats.get("total", 0),
                    "today": stats.get("today", 0),
                    "active": stats.get("active", 0),
                    "average_rating": rating["average"],
                    "rating_count": rating["count"],
                }
            )
        return result
    finally:
        db.close()


def pending_tickets() -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(HandoverTicket)
            .filter(
                HandoverTicket.status.in_(["queued", "assigned"]),
                HandoverTicket.deleted.is_(False),
            )
            .order_by(HandoverTicket.created_at.asc())
            .all()
        )
        return [ticket_to_dict(row) for row in rows]
    finally:
        db.close()


def list_question_gaps(limit: int = 20) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(QuestionLog.normalized, func.count(QuestionLog.id))
            .filter(QuestionLog.hit.is_(False))
            .group_by(QuestionLog.normalized)
            .order_by(func.count(QuestionLog.id).desc())
            .limit(limit)
            .all()
        )
        result = []
        for norm, count in rows:
            sample = (
                db.query(QuestionLog.question)
                .filter(QuestionLog.normalized == norm, QuestionLog.hit.is_(False))
                .first()
            )
            result.append(
                {
                    "normalized": norm,
                    "count": count,
                    "question": sample[0] if sample else norm,
                }
            )
        return result
    finally:
        db.close()


def next_work_no(role: str) -> str:
    prefix = "AD" if role == "admin" else "CS"
    db = SessionLocal()
    try:
        rows = (
            db.query(User)
            .filter(User.work_no.like(f"{prefix}%"))
            .order_by(User.work_no.desc())
            .limit(1)
            .all()
        )
        if not rows:
            return f"{prefix}20260001"
        latest = rows[0].work_no
        number = int(latest[len(prefix):]) + 1 if latest[len(prefix):].isdigit() else 1
        return f"{prefix}{number:08d}"
    finally:
        db.close()
