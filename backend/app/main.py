import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import text

from . import agent, agent_service, auth, config, dingtalk, hot, milvus_store, router, storage, validation
from .db import Conversation, SessionLocal, init_db
from .redis_client import get_redis
from .tools import route as route_tool
from .tools import ticket as ticket_tool
from .tools import weather as weather_tool

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="杭州智游助手 API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    messages: list[dict]
    scenic_areas: list[str] | None = None


class ChatStreamRequest(BaseModel):
    session_id: int | None = None
    question: str = ""
    scenic_areas: list[str] | None = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    captcha_id: str
    captcha_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionCreateRequest(BaseModel):
    title: str = "新对话"


class RefreshRequest(BaseModel):
    refresh_token: str


class HandoverRequest(BaseModel):
    session_id: int
    reason: str | None = None


class CloseRequest(BaseModel):
    rating: int | None = None
    comment: str | None = None


class RateRequest(BaseModel):
    score: int
    comment: str | None = None


class AgentMessageRequest(BaseModel):
    ticket_id: int
    content: str


class AdminCreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "customer_service"
    mobile: str | None = None


class AgentStatusRequest(BaseModel):
    status: str


class AdminAssignRequest(BaseModel):
    agent_id: int


def _check_conversation_access(conversation: Conversation | None, user) -> None:
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if conversation.user_id is not None and (user is None or conversation.user_id != user.id):
        raise HTTPException(status_code=403, detail="无权访问该会话")


def _ticket_preview(ticket: dict) -> dict:
    messages = storage.list_messages(ticket["session_id"])
    user_messages = [item for item in messages if item["role"] == "user"]
    ticket["preview"] = user_messages[-1]["content"][:120] if user_messages else ""
    ticket["user_name"] = None
    if ticket.get("user_id"):
        user_row = storage.get_user_by_id(ticket["user_id"])
        ticket["user_name"] = user_row.username if user_row else None
    return ticket


def _check_assigned_ticket(ticket_id: int, agent) -> object:
    ticket = storage.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在")
    if ticket.assignee_id != agent.id:
        raise HTTPException(status_code=403, detail="无权操作该工单")
    return ticket


@app.get("/")
def root():
    return {
        "name": "杭州智游助手 API",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health():
    milvus_ok = False
    mysql_ok = False
    redis_ok = False
    doc_count = 0
    try:
        milvus_ok = milvus_store.get_client().has_collection(config.COLLECTION_NAME)
        doc_count = milvus_store.collection_count() if milvus_ok else 0
    except Exception:
        pass
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        mysql_ok = True
    except Exception:
        pass
    try:
        redis_ok = bool(get_redis().ping())
    except Exception:
        pass
    return {
        "status": "ok",
        "milvus": milvus_ok,
        "mysql": mysql_ok,
        "redis": redis_ok,
        "collection": config.COLLECTION_NAME,
        "doc_count": doc_count,
    }


@app.get("/api/auth/captcha")
def captcha():
    captcha_id, image = auth.generate_captcha()
    return {"captcha_id": captcha_id, "image": image}


@app.post("/api/auth/register")
def register(payload: RegisterRequest):
    if not auth.verify_captcha(payload.captcha_id, payload.captcha_code):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")
    username = payload.username.strip()
    ok, reason = validation.validate_username(username)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    if username[:2] in ("AD", "CS"):
        raise HTTPException(status_code=400, detail="工号前缀 AD/CS 仅供管理员或客服账号使用")
    ok, reason = validation.validate_password(payload.password)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    if storage.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = storage.create_user(username, auth.hash_password(payload.password))
    return {"token": auth.create_access_token(user), "user": storage.user_to_dict(user)}


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = storage.get_user_by_username(payload.username.strip())
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    if user.role == "deleted":
        raise HTTPException(status_code=400, detail="账号已删除")
    return {
        "token": auth.create_access_token(user),
        "refresh_token": auth.create_refresh_token(user),
        "user": storage.user_to_dict(user),
    }


@app.post("/api/auth/refresh")
def refresh(payload: RefreshRequest):
    payload_data = auth.decode_refresh_token(payload.refresh_token)
    if payload_data is None:
        raise HTTPException(status_code=401, detail="刷新凭证无效")
    user = storage.get_user_by_id(int(payload_data["sub"]))
    if user is None or user.role == "deleted":
        raise HTTPException(status_code=401, detail="用户不存在或已删除")
    return {"token": auth.create_access_token(user), "user": storage.user_to_dict(user)}


@app.get("/api/auth/me")
def me(user=Depends(auth.get_current_user)):
    return {"user": storage.user_to_dict(user)}


@app.post("/api/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if credentials is not None:
        auth.logout_token(credentials)
    return {"status": "ok"}


@app.get("/api/sessions")
def sessions(user=Depends(auth.get_current_user)):
    return {"sessions": storage.list_conversations(user.id)}


@app.post("/api/sessions")
def create_session(payload: SessionCreateRequest, user=Depends(auth.get_optional_user)):
    conversation = storage.create_conversation(user.id if user else None, payload.title.strip() or "新对话")
    return {"session_id": conversation.id, "title": conversation.title}


@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: int, user=Depends(auth.get_optional_user)):
    if not storage.delete_conversation(session_id, user.id if user else None):
        raise HTTPException(status_code=404, detail="会话不存在或无权删除")
    return {"status": "ok"}


@app.get("/api/sessions/{session_id}/messages")
def session_messages(session_id: int, user=Depends(auth.get_optional_user)):
    conversation = storage.get_conversation(session_id)
    _check_conversation_access(conversation, user)
    return {"session_id": session_id, "messages": storage.list_messages(session_id)}


@app.delete("/api/messages/{message_id}")
def delete_message(
    message_id: int,
    session_id: int | None = None,
    user=Depends(auth.get_optional_user),
):
    message = storage.get_message(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if session_id is not None and message.session_id != session_id:
        raise HTTPException(status_code=400, detail="消息不属于该会话")
    conversation = storage.get_conversation(message.session_id)
    if conversation is not None and conversation.user_id is not None and (
        user is None or conversation.user_id != user.id
    ):
        raise HTTPException(status_code=403, detail="无权删除该消息")
    storage.soft_delete_message(message_id)
    return {"status": "ok"}


@app.post("/api/chat")
def chat(payload: ChatRequest):
    return agent.handle_chat(payload.messages, scenic_areas_hint=payload.scenic_areas)


@app.post("/api/chat/stream")
def chat_stream(payload: ChatStreamRequest, user=Depends(auth.get_optional_user)):
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    if payload.session_id:
        conversation = storage.get_conversation(payload.session_id)
        _check_conversation_access(conversation, user)
    else:
        conversation = storage.create_conversation(user.id if user else None)
    session_id = conversation.id
    storage.add_message(session_id, "user", question)
    handover_ticket = agent_service.maybe_create_handover(
        session_id,
        user.id if user else None,
        question,
        manual=False,
    )
    history = storage.list_messages(session_id)
    history_for_agent = [
        {"role": item["role"], "content": item["content"]}
        for item in history
        if item.get("sender_type") != "system"
    ]
    cache_key = f"answer:v2:{hot.normalize_question(question)}:{'-'.join(payload.scenic_areas or [])}"

    def sse(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def generate():
        try:
            yield sse("session", {"session_id": session_id, "handover": handover_ticket})
            cached = get_redis().get(cache_key)
            if cached:
                data = json.loads(cached)
                meta = {
                    "intents": data.get("intents", []),
                    "sources": data.get("sources", []),
                    "itinerary": data.get("itinerary"),
                    "weather": None,
                    "ticket_hits": data.get("ticket_hits", []),
                    "scenic_areas": data.get("scenic_areas", []),
                    "scenic_label": data.get("scenic_label", ""),
                }
                done = {
                    "reply": data.get("reply", ""),
                    "suggested_questions": data.get("suggested_questions", []),
                    **meta,
                }
                yield sse("meta", meta)
                yield sse("token", {"text": data.get("reply", "")})
                yield sse("done", done)
                storage.add_message(
                    session_id,
                    "assistant",
                    done["reply"],
                    sources=done["sources"],
                    meta={
                        "intents": done["intents"],
                        "itinerary": done["itinerary"],
                        "weather": None,
                        "ticket_hits": done["ticket_hits"],
                        "suggested_questions": done["suggested_questions"],
                        "scenic_areas": done["scenic_areas"],
                        "scenic_label": done["scenic_label"],
                    },
                )
                hot.record_question(
                    question,
                    hit=bool(done.get("sources")),
                    session_id=session_id,
                    user_id=user.id if user else None,
                )
                return
            final = None
            for item in agent.stream_chat(history_for_agent, scenic_areas_hint=payload.scenic_areas):
                if item["type"] == "meta":
                    yield sse("meta", item)
                elif item["type"] == "token":
                    yield sse("token", {"text": item["text"]})
                elif item["type"] == "done":
                    final = item
                    yield sse("done", item)
            if final is None:
                raise RuntimeError("问答链路未返回结果")
            storage.add_message(
                session_id,
                "assistant",
                final["reply"],
                sources=final["sources"],
                meta={
                    "intents": final.get("intents", []),
                    "itinerary": final.get("itinerary"),
                    "weather": final.get("weather"),
                    "ticket_hits": final.get("ticket_hits", []),
                    "suggested_questions": final.get("suggested_questions", []),
                    "scenic_areas": final.get("scenic_areas", []),
                    "scenic_label": final.get("scenic_label", ""),
                },
            )
            hot.record_question(
                question,
                hit=bool(final.get("sources")),
                session_id=session_id,
                user_id=user.id if user else None,
            )
            if "weather" not in final.get("intents", []):
                get_redis().setex(
                    cache_key,
                    1800,
                    json.dumps(
                        {
                            "reply": final["reply"],
                            "sources": final.get("sources", []),
                            "intents": final.get("intents", []),
                            "itinerary": final.get("itinerary"),
                            "ticket_hits": final.get("ticket_hits", []),
                            "suggested_questions": final.get("suggested_questions", []),
                            "scenic_areas": final.get("scenic_areas", []),
                            "scenic_label": final.get("scenic_label", ""),
                        },
                        ensure_ascii=False,
                    ),
                )
        except Exception as exc:
            yield sse("error", {"message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/hot-questions")
def hot_questions():
    items = hot.get_hot_questions()
    return {"questions": items, "source": "real" if items else "empty"}


@app.get("/api/attractions")
def attractions():
    data = json.loads((DATA_DIR / "attractions.json").read_text(encoding="utf-8"))
    return {"attractions": data}


@app.get("/api/pois")
def pois():
    data = json.loads((DATA_DIR / "pois.json").read_text(encoding="utf-8"))
    return {"pois": data}


@app.get("/api/scenic-areas")
def scenic_areas():
    return {"scenic_areas": router.all_scenic_areas()}


@app.get("/api/tools/weather")
def weather():
    return weather_tool.get_weather()


@app.get("/api/tools/tickets")
def tickets():
    return {"tickets": ticket_tool.all_tickets()}


@app.get("/api/tools/routes")
def routes():
    return {"routes": route_tool.all_routes()}


@app.post("/api/agent/handover")
def handover(payload: HandoverRequest, user=Depends(auth.get_optional_user)):
    conversation = storage.get_conversation(payload.session_id)
    _check_conversation_access(conversation, user)
    ticket = agent_service.maybe_create_handover(
        payload.session_id,
        user.id if user else None,
        payload.reason or "用户主动转人工",
        manual=True,
    )
    if ticket is None:
        raise HTTPException(status_code=400, detail="无法创建转人工工单")
    return {"ticket": ticket}


@app.get("/api/agent/tickets")
def agent_tickets(agent=Depends(auth.get_current_customer_service)):
    tickets = [_ticket_preview(ticket) for ticket in storage.agent_tasks(agent.id)]
    return {"tickets": tickets}


@app.get("/api/agent/tasks")
def agent_tasks(agent=Depends(auth.get_current_customer_service)):
    tickets = [_ticket_preview(ticket) for ticket in storage.agent_tasks(agent.id)]
    return {"tickets": tickets}


@app.post("/api/agent/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, agent=Depends(auth.get_current_agent)):
    if not storage.assign_ticket(ticket_id, agent.id):
        raise HTTPException(status_code=404, detail="工单不存在")
    ticket = storage.get_ticket(ticket_id)
    return {"ticket": storage.ticket_to_dict(ticket)}


@app.post("/api/agent/tickets/{ticket_id}/close")
def close_ticket(
    ticket_id: int,
    payload: CloseRequest,
    agent=Depends(auth.get_current_customer_service),
):
    ticket = _check_assigned_ticket(ticket_id, agent)
    storage.close_ticket(ticket_id, payload.rating, payload.comment)
    storage.audit_log(agent.id, "close_ticket", "handover_ticket", ticket_id)
    storage.add_message(
        ticket.session_id,
        "assistant",
        "客服已结束本次会话，欢迎继续向我咨询杭州相关问题。",
        sender_type="system",
        meta={"system": True},
    )
    return {"status": "ok"}


@app.post("/api/agent/tickets/{ticket_id}/return")
def return_ticket(ticket_id: int, agent=Depends(auth.get_current_customer_service)):
    ticket = _check_assigned_ticket(ticket_id, agent)
    storage.return_ticket(ticket_id)
    storage.audit_log(agent.id, "return_ticket", "handover_ticket", ticket_id)
    storage.add_message(
        ticket.session_id,
        "assistant",
        "已转回智能助手，你可以继续向我提问。",
        sender_type="system",
        meta={"system": True},
    )
    return {"status": "ok"}


@app.post("/api/agent/tickets/{ticket_id}/rate")
def rate_ticket(ticket_id: int, payload: RateRequest, user=Depends(auth.get_current_user)):
    if payload.score < 1 or payload.score > 5:
        raise HTTPException(status_code=400, detail="评分需在 1-5 之间")
    if not storage.rate_ticket(ticket_id, user.id, payload.score, payload.comment):
        raise HTTPException(status_code=403, detail="无权评价该工单")
    return {"status": "ok"}


@app.post("/api/agent/messages")
def agent_send_message(payload: AgentMessageRequest, agent=Depends(auth.get_current_customer_service)):
    ticket = _check_assigned_ticket(payload.ticket_id, agent)
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="回复内容不能为空")
    if ticket.status == "assigned":
        storage.set_ticket_in_progress(ticket.id)
    message = storage.add_message(
        ticket.session_id,
        "assistant",
        content,
        sender_type="agent",
        meta={"agent_id": agent.id, "agent_name": agent.username},
    )
    return {"message_id": message.id, "status": "ok"}


@app.get("/api/agent/tickets/{ticket_id}/context")
def agent_ticket_context(ticket_id: int, agent=Depends(auth.get_current_customer_service)):
    ticket = _check_assigned_ticket(ticket_id, agent)
    return {
        "ticket": storage.ticket_to_dict(ticket),
        "messages": storage.list_messages(ticket.session_id),
    }


@app.get("/api/agent/stats")
def agent_stats(agent=Depends(auth.get_current_customer_service)):
    return {"stats": storage.agent_stats(agent.id)}


@app.post("/api/agent/status")
def agent_status(payload: AgentStatusRequest, agent=Depends(auth.get_current_customer_service)):
    if not storage.set_agent_status(agent.id, payload.status):
        raise HTTPException(status_code=400, detail="状态不合法")
    storage.audit_log(agent.id, "agent_status", "agent", agent.id, payload.status)
    return {"status": payload.status}


@app.get("/api/agent/status")
def get_agent_status(agent=Depends(auth.get_current_customer_service)):
    return {"status": storage.get_agent_status(agent.id)}


@app.post("/api/agent/heartbeat")
def agent_heartbeat(agent=Depends(auth.get_current_customer_service)):
    storage.agent_heartbeat(agent.id)
    return {"status": "ok"}


@app.get("/api/agent/my-rating")
def agent_my_rating(agent=Depends(auth.get_current_customer_service)):
    return {"rating": storage.my_rating(agent.id)}


@app.get("/api/admin/users")
def admin_users(
    role: str | None = None,
    keyword: str | None = None,
    admin=Depends(auth.get_current_admin),
):
    return {"users": storage.list_users(role=role, keyword=keyword)}


@app.post("/api/admin/users")
def admin_create_user(payload: AdminCreateUserRequest, admin=Depends(auth.get_current_admin)):
    if payload.role not in ("user", "customer_service", "admin"):
        raise HTTPException(status_code=400, detail="角色不合法")
    username = payload.username.strip()
    ok, reason = validation.validate_password(payload.password)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)
    if payload.role in ("admin", "customer_service"):
        prefix = "AD" if payload.role == "admin" else "CS"
        if not username:
            username = storage.next_work_no(payload.role)
        if not re.fullmatch(rf"{prefix}\d{{8}}", username):
            raise HTTPException(status_code=400, detail=f"{prefix} 前缀工号格式应为 {prefix} + 8 位数字")
    else:
        ok, reason = validation.validate_username(username)
        if not ok:
            raise HTTPException(status_code=400, detail=reason)
        if username[:2] in ("AD", "CS"):
            raise HTTPException(status_code=400, detail="工号前缀 AD/CS 仅供管理员或客服账号使用")
    if storage.get_user_by_username(username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = storage.create_user(
        username,
        auth.hash_password(payload.password),
        role=payload.role,
        work_no=username if payload.role in ("admin", "customer_service") else None,
    )
    if payload.role in ("admin", "customer_service"):
        storage.get_or_create_agent_profile(user.id)
        if payload.mobile:
            storage.update_agent_profile(user.id, mobile=payload.mobile)
    storage.audit_log(admin.id, "create_user", "user", user.id, username)
    return {"user": storage.user_to_dict(user)}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, admin=Depends(auth.get_current_admin)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    if not storage.delete_user(user_id, deleted_by=admin.id):
        raise HTTPException(status_code=404, detail="用户不存在")
    storage.audit_log(admin.id, "delete_user", "user", user_id)
    return {"status": "ok"}


@app.get("/api/admin/recycle-bin")
def admin_recycle_bin(admin=Depends(auth.get_current_admin)):
    return {"users": storage.list_deleted_users()}


@app.post("/api/admin/users/{user_id}/restore")
def admin_restore_user(user_id: int, admin=Depends(auth.get_current_admin)):
    if not storage.restore_user(user_id):
        raise HTTPException(status_code=404, detail="用户不存在或不在回收站")
    storage.audit_log(admin.id, "restore_user", "user", user_id)
    return {"status": "ok"}


@app.get("/api/admin/next-work-no")
def admin_next_work_no(role: str, admin=Depends(auth.get_current_admin)):
    if role not in ("admin", "customer_service"):
        raise HTTPException(status_code=400, detail="角色不合法")
    return {"work_no": storage.next_work_no(role)}


@app.get("/api/admin/pending-tickets")
def admin_pending_tickets(admin=Depends(auth.get_current_admin)):
    agent_service.escalate_queued_tickets()
    tickets = [_ticket_preview(ticket) for ticket in storage.pending_tickets()]
    return {"count": len(tickets), "tickets": tickets}


@app.post("/api/admin/tickets/{ticket_id}/assign")
def admin_assign_ticket(
    ticket_id: int,
    payload: AdminAssignRequest,
    admin=Depends(auth.get_current_admin),
):
    target = storage.get_user_by_id(payload.agent_id)
    if target is None or target.role != "customer_service":
        raise HTTPException(status_code=400, detail="只能分配给客服账号")
    if not storage.assign_ticket(ticket_id, target.id):
        raise HTTPException(status_code=404, detail="工单不存在")
    storage.audit_log(
        admin.id,
        "manual_assign",
        "handover_ticket",
        ticket_id,
        f"分配给 {target.work_no or target.username}",
    )
    profiles = {item["user_id"]: item for item in storage.list_agent_profiles()}
    info = profiles.get(target.id, {})
    text = (
        f"杭州智游助手-转人工分配\n"
        f"被分配客服：@{target.work_no or target.username}\n"
        f"工单号：{ticket_id}\n"
        f"工作台：http://127.0.0.1:5173/agent"
    )
    mobiles = [info["mobile"]] if info.get("mobile") else []
    dingtalk.send_robot_text(text, at_mobiles=mobiles, ticket_id=ticket_id)
    return {"status": "ok"}


@app.get("/api/admin/agent-performance")
def admin_agent_performance(admin=Depends(auth.get_current_admin)):
    return {"agents": storage.agent_performance()}


@app.get("/api/admin/question-gaps")
def admin_question_gaps(admin=Depends(auth.get_current_admin)):
    return {"gaps": storage.list_question_gaps()}


@app.delete("/api/admin/tickets/{ticket_id}")
def admin_delete_ticket(ticket_id: int, admin=Depends(auth.get_current_admin)):
    if not storage.delete_ticket(ticket_id):
        raise HTTPException(status_code=404, detail="工单不存在")
    storage.audit_log(admin.id, "delete_ticket", "handover_ticket", ticket_id)
    return {"status": "ok"}
