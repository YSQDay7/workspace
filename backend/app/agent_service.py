from . import dingtalk, storage
from .redis_client import get_redis

NEGATIVE_WORDS = [
    "投诉",
    "举报",
    "人工",
    "客服",
    "转人工",
    "差评",
    "垃圾",
    "骗人",
    "骗子",
    "失望",
    "生气",
    "愤怒",
    "很差",
    "太差",
    "不满意",
    "没用",
    "什么破",
    "讨厌",
    "解决不了",
    "没人管",
]


def detect_negative(text: str) -> bool:
    return any(word in (text or "") for word in NEGATIVE_WORDS)


def maybe_create_handover(
    session_id: int,
    user_id: int | None,
    question: str,
    manual: bool = False,
) -> dict | None:
    question = (question or "").strip()
    if not question:
        return None
    active = storage.get_active_ticket(session_id)
    if active is not None:
        return storage.ticket_to_dict(active)
    triggered = manual or detect_negative(question)
    if not triggered:
        return None
    priority = 2 if manual or detect_negative(question) else 1
    ticket = storage.create_handover_ticket(session_id, user_id, question[:200], priority=priority)
    assigned = _auto_assign(ticket, question)
    storage.add_message(
        session_id,
        "assistant",
        "已为你转接人工客服，请稍候，客服接入后会在此会话回复。",
        sender_type="system",
        meta={"system": True, "ticket_id": ticket.id},
    )
    return storage.ticket_to_dict(storage.get_ticket(ticket.id))


def _auto_assign(ticket, question: str) -> dict | None:
    profiles = [item for item in storage.list_agent_profiles() if item["role"] == "customer_service"]
    online = [item for item in profiles if item["status"] == "online"]
    if not online:
        text = (
            f"杭州智游助手-转人工提醒\n"
            f"工单号：{ticket.id}\n"
            f"用户问题：{question[:100]}\n"
            f"当前无在线客服，任务已进入排队，请管理员及时处理。\n"
            f"工作台：http://127.0.0.1:5173/agent"
        )
        dingtalk.send_robot_text(text, ticket_id=ticket.id)
        return None
    online.sort(key=lambda item: storage.agent_stats(item["user_id"]).get("active", 0))
    target = online[0]
    storage.assign_ticket(ticket.id, target["user_id"])
    storage.audit_log(
        actor_id=None,
        action="auto_assign",
        target_type="handover_ticket",
        target_id=ticket.id,
        detail=f"自动分配给 {target['work_no']}",
    )
    text = (
        f"杭州智游助手-转人工提醒\n"
        f"被分配客服：@{target['work_no']}\n"
        f"工单号：{ticket.id}\n"
        f"用户问题：{question[:100]}\n"
        f"工作台：http://127.0.0.1:5173/agent"
    )
    mobiles = [target["mobile"]] if target.get("mobile") else []
    dingtalk.send_robot_text(text, at_mobiles=mobiles, ticket_id=ticket.id)
    return target


def escalate_queued_tickets() -> int:
    redis = get_redis()
    escalated = 0
    for ticket in storage.pending_tickets():
        if ticket["status"] != "queued" or ticket["wait_seconds"] < 300:
            continue
        flag = f"escalated:{ticket['id']}"
        if redis.set(flag, "1", nx=True, ex=1800):
            text = (
                f"杭州智游助手-排队超时提醒\n"
                f"工单号：{ticket['id']}\n"
                f"已排队 {ticket['wait_seconds'] // 60} 分钟，请管理员尽快分配。\n"
                f"工作台：http://127.0.0.1:5173/agent"
            )
            dingtalk.send_robot_text(text, ticket_id=ticket['id'])
            escalated += 1
    return escalated
