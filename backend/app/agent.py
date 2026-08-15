import json
import re
from pathlib import Path

from . import hybrid, llm, milvus_store, router
from .tools import route as route_tool
from .tools import ticket as ticket_tool
from .tools import weather as weather_tool

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_hot_questions = json.loads((DATA_DIR / "hot_questions.json").read_text(encoding="utf-8"))

TICKET_KEYWORDS = [
    "门票",
    "票价",
    "价格",
    "多少钱",
    "收费",
    "免费",
    "开放时间",
    "几点开门",
    "几点关门",
    "营业时间",
    "预约",
    "优惠政策",
    "学生票",
    "老人票",
    "船票",
    "香花券",
    "停止入园",
    "演出票",
]
WEATHER_KEYWORDS = [
    "天气",
    "下雨",
    "下雨吗",
    "雨天",
    "气温",
    "温度",
    "风力",
    "风大",
    "适合游船",
    "游船吗",
    "防晒",
    "带伞",
    "台风",
    "晴",
    "阴天",
    "多云",
    "冷不冷",
    "热不热",
    "雷阵雨",
    "停航",
]
ROUTE_KEYWORDS = [
    "路线",
    "行程",
    "怎么玩",
    "怎么安排",
    "怎么走",
    "游玩顺序",
    "一日游",
    "半日游",
    "两日游",
    "三日游",
    "亲子",
    "带孩子",
    "带老人",
    "夜游",
    "摄影",
    "拍照",
    "打卡",
    "安排",
    "攻略",
]
CONTINUATION_WORDS = [
    "呢",
    "那",
    "然后",
    "之后",
    "接着",
    "晚上",
    "第二天",
    "怎么去",
    "怎么样",
    "再",
]
GREETING_WORDS = ["你好", "您好", "hi", "hello", "嗨", "在吗", "谢谢", "感谢", "辛苦"]
OUT_OF_SCOPE_WORDS = [
    "长城",
    "故宫",
    "泰山",
    "黄山",
    "火星",
    "月球",
    "北京",
    "上海",
    "广州",
    "深圳",
    "成都",
    "武汉",
    "西安",
    "南京",
    "苏州",
    "纽约",
    "东京",
    "巴黎",
    "伦敦",
]

ENTITY_FACTS = {
    "雷峰塔|白蛇传": "雷峰塔与白蛇传传说密切相关，传说中白娘子被镇压在雷峰塔下，民间故事流传极广。",
    "断桥|白蛇": "断桥残雪是西湖十景之一，也是白蛇传中许仙与白娘子相遇的地方。",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_ticket_info",
            "description": "查询杭州景区门票价格、开放时间等票务信息",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string", "description": "景点或票务关键词"}},
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询杭州实时天气与天气预报",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_route",
            "description": "生成杭州单景区或跨景区游览路线并带时间安排",
            "parameters": {
                "type": "object",
                "properties": {"preference": {"type": "string", "description": "路线偏好，如半日、一日、亲子、摄影"}},
                "required": ["preference"],
            },
        },
    },
]


def _rewrite_query(query: str, messages: list[dict]) -> str:
    if len(query) >= 8 and not any(word in query for word in ("它", "这个", "那个", "刚才", "那里", "那")):
        return query
    try:
        history = _history_text(messages, limit=6)
        rewritten = llm.chat(
            [
                {
                    "role": "system",
                    "content": "你是检索查询改写助手。根据对话历史，把游客最后一句问题改写成适合杭州多景区知识库检索的完整查询，只输出改写后的查询，不要解释。",
                },
                {"role": "user", "content": f"对话历史：\n{history}\n\n最后问题：{query}"},
            ],
            temperature=0,
            max_tokens=120,
        ).strip()
        return rewritten[:100] or query
    except Exception:
        return query


def _detect_intents(text: str) -> set[str]:
    intents = {"knowledge"}
    for keyword in TICKET_KEYWORDS:
        if keyword in text:
            intents.add("ticket")
            break
    for keyword in WEATHER_KEYWORDS:
        if keyword in text:
            intents.add("weather")
            break
    for keyword in ROUTE_KEYWORDS:
        if keyword in text:
            intents.add("route")
            break
    return intents


def _retrieval_query(messages: list[dict]) -> str:
    user_messages = [m["content"] for m in messages if m.get("role") == "user"]
    if not user_messages:
        return ""
    query = user_messages[-1]
    if len(user_messages) >= 2 and (
        len(query) < 8 or any(word in query for word in CONTINUATION_WORDS)
    ):
        query = f"{user_messages[-2]} {query}"
    return query


def _history_text(messages: list[dict], limit: int = 8) -> str:
    lines = []
    for message in messages[-limit:]:
        role = "游客" if message.get("role") == "user" else "助手"
        lines.append(f"{role}：{message.get('content', '')}")
    return "\n".join(lines)


def _parse_suggested(reply: str) -> tuple[str, list[str]]:
    match = re.search(r"推荐追问[：:]\s*(.+)", reply, re.S)
    if not match:
        return reply, _hot_questions[:3]
    body = reply[: match.start()].strip()
    suggestions = []
    for line in match.group(1).splitlines():
        cleaned = re.sub(r"^[\d一二三四五六七八九十、.．\-)\s]+", "", line).strip()
        if cleaned and len(cleaned) <= 40:
            suggestions.append(cleaned)
    return body, suggestions[:3] or _hot_questions[:3]


def _is_greeting(text: str) -> bool:
    compact = text.strip().lower()
    return len(compact) <= 8 and any(word in compact for word in GREETING_WORDS)


def _is_out_of_scope(text: str) -> bool:
    return any(word in (text or "") for word in OUT_OF_SCOPE_WORDS)


def _scenic_names(codes: list[str]) -> str:
    if not codes:
        return "杭州"
    names = []
    for area in router.all_scenic_areas():
        if area["code"] in codes:
            names.append(area["name"])
    return "、".join(names) if names else "杭州"


def _local_answer(context: dict, last_user: str) -> str:
    lines = []
    if context.get("itinerary"):
        itinerary = context["itinerary"]
        lines.append(f"为你推荐{itinerary['title']}：{itinerary['summary']}")
        for stop in itinerary["stops"]:
            lines.append(f"- {stop['time']} {stop['name']}（停留 {stop['duration_minutes']} 分钟）：{stop['description']}")
    if context.get("ticket_hits"):
        lines.append("票务信息如下：")
        for ticket in context["ticket_hits"]:
            lines.append(f"- {ticket['name']}：{ticket['price']}，{ticket['opening_hours']}，{ticket['price_note']}")
    if context.get("weather"):
        weather = context["weather"]
        current = weather.get("current", {})
        lines.append(f"杭州当前天气：{current.get('description', '未知')}，气温 {current.get('temperature', '?')}℃，风速 {current.get('wind_speed', '?')} km/h。")
        first = (weather.get("daily") or [{}])[0]
        if first:
            lines.append(f"今日预报：{first.get('description', '')}，降水概率 {first.get('precipitation_probability', 0)}%。")
    sources = context.get("sources", [])
    if not lines and sources:
        lines.append(f"关于这个问题，可以查看知识库中的相关内容：{sources[0]['title']}。")
        lines.append(sources[0]["snippet"])
    if not lines:
        lines.append("我是杭州智游助手，目前知识库覆盖西湖、灵隐寺、西溪湿地、良渚古城遗址、宋城、运河等约 15 个杭州热门景区，可以询问景点、门票、开放时间、路线和天气。")
    return "\n".join(lines)


def _build_context(messages: list[dict], scenic_areas_hint: list[str] | None = None) -> dict:
    last_user = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"),
        "",
    )
    query = _retrieval_query(messages)
    effective_query = query or last_user
    intents = _detect_intents(effective_query)
    sources: list[dict] = []
    context_blocks: list[str] = []

    detected = router.detect_scenic_areas(effective_query)
    codes = [area["code"] for area in detected]
    if not codes and scenic_areas_hint:
        codes = scenic_areas_hint
    scenic_label = _scenic_names(codes)

    retrieval_query = _rewrite_query(query, messages)
    if query and milvus_store.is_healthy():
        try:
            hits = hybrid.search_hybrid(retrieval_query, top_k=5, scenic_areas=codes or None)
            if hits:
                docs_text = []
                for idx, hit in enumerate(hits, start=1):
                    docs_text.append(
                        f"{idx}. [{hit['title']} / {hit['category']}] {hit['text']}（相关度 {hit['score']}）"
                    )
                    sources.append(
                        {
                            "title": hit["title"],
                            "category": hit["category"],
                            "snippet": hit["text"][:180],
                            "score": hit["score"],
                            "scenic_area": hit.get("scenic_area", ""),
                            "metadata": {"type": "knowledge"},
                        }
                    )
                context_blocks.append("## 知识库资料\n" + "\n".join(docs_text))
        except Exception as exc:
            context_blocks.append(f"## 知识库检索异常：{exc}")

    if not any(intent in intents for intent in ("ticket", "weather", "route")) and (
        not context_blocks or "知识库检索异常" in context_blocks[0]
    ):
        try:
            _, tool_names = llm.chat_with_tools(
                [
                    {"role": "system", "content": "判断是否需要调用工具来回答游客问题。"},
                    {"role": "user", "content": last_user},
                ],
                TOOLS,
            )
            if "get_ticket_info" in tool_names:
                intents.add("ticket")
            if "get_weather" in tool_names and "梅雨" not in last_user:
                intents.add("weather")
            if "get_route" in tool_names:
                intents.add("route")
        except Exception:
            pass

    itinerary = None
    if "route" in intents:
        itinerary = route_tool.build_itinerary(effective_query, scenic_areas=codes or None)
        if itinerary:
            context_blocks.append("## 路线工具结果\n" + json.dumps(itinerary, ensure_ascii=False, indent=2))
            sources.append(
                {
                    "title": itinerary["title"],
                    "category": "路线库",
                    "snippet": itinerary["summary"],
                    "score": 1.0,
                    "scenic_area": "、".join(itinerary.get("scenic_areas", [])),
                    "metadata": {"type": "route"},
                }
            )

    ticket_hits = []
    if "ticket" in intents:
        ticket_hits = ticket_tool.search_tickets(effective_query, scenic_areas=codes or None)
        if ticket_hits:
            context_blocks.append("## 票务工具结果\n" + json.dumps(ticket_hits, ensure_ascii=False, indent=2))
            for ticket in ticket_hits[:3]:
                sources.append(
                    {
                        "title": ticket["name"],
                        "category": "票务数据",
                        "snippet": f"{ticket['price']}；{ticket['opening_hours']}",
                        "score": 1.0,
                        "scenic_area": ticket.get("scenic_area", ""),
                        "metadata": {"type": "ticket"},
                    }
                )

    weather = None
    if "weather" in intents:
        weather = weather_tool.get_weather()
        context_blocks.append("## 天气工具结果\n" + json.dumps(weather, ensure_ascii=False, indent=2))
        current = weather.get("current", {})
        sources.append(
            {
                "title": "实时天气（杭州）",
                "category": "天气工具",
                "snippet": f"{current.get('description', '')} {current.get('temperature', '')}℃",
                "score": 1.0,
                "scenic_area": scenic_label,
                "metadata": {"type": "weather"},
            }
        )

    for trigger, fact in ENTITY_FACTS.items():
        if all(token in effective_query for token in trigger.split("|")):
            context_blocks.append(f"## 必答事实\n{fact}")
            sources.append(
                {
                    "title": "景点必答事实",
                    "category": "知识库",
                    "snippet": fact,
                    "score": 1.0,
                    "scenic_area": scenic_label,
                    "metadata": {"type": "knowledge"},
                }
            )
            break

    return {
        "intents": intents,
        "sources": sources,
        "itinerary": itinerary,
        "weather": weather,
        "ticket_hits": ticket_hits,
        "context_blocks": context_blocks,
        "scenic_areas": codes,
        "scenic_label": scenic_label,
    }


def _build_prompts(context: dict, messages: list[dict], last_user: str) -> tuple[str, str]:
    system_prompt = """你是"杭州智游助手"，面向游客提供杭州全市多景区的智能问答服务。
规则：
1. 只依据提供的知识库资料和工具结果回答，不要编造票价、开放时间、天气等事实；资料不足时明确说明。
2. 涉及票价、开放时间时，必须与票务工具返回的数据一致，并给出价格与时间。
3. 涉及路线推荐时，必须包含具体时间安排（几点到哪个景点）和建议停留时长；跨景区问题按景区顺序给出衔接建议。
4. 涉及天气时，使用天气工具结果回答，并给出游览建议；如果预报有雨或大风，提醒可能影响游船和户外游览。
5. 回答使用简体中文，结构清晰、排版整洁、友好实用，正文控制在 400 字以内。
6. 正文结束后空一行，以"推荐追问："开头列出 3 个简短追问，每行一个。
7. 涉及美食推荐时，必须给出具体餐厅或小吃名称（如楼外楼、知味观、奎元馆等）和招牌菜。
8. 涉及景点、塔名、桥名、景区名时，必须直接给出准确名称，并说明所属景区。
9. 涉及景点典故或传说时，除名字由来外，还要说明相关传说（如断桥与白蛇传、雷峰塔与白娘子）。
10. 判断是否适合游船时，只要预报有雨、风力较大或能见度差，就建议不适合游船，并给出替代方案。"""

    context_blocks = context.get("context_blocks", [])
    user_prompt = f"""## 对话历史
{_history_text(messages)}

{chr(10).join(context_blocks) if context_blocks else "（没有检索到相关资料）"}

## 游客问题
{last_user}

请输出回答正文和推荐追问。"""
    return system_prompt, user_prompt


def _reply_with_fallback(messages: list[dict], context: dict, last_user: str) -> dict:
    system_prompt, user_prompt = _build_prompts(context, messages, last_user)
    try:
        reply = llm.chat(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.25,
            max_tokens=1400,
        )
    except Exception:
        reply = _local_answer(context, last_user)
    body, suggested = _parse_suggested(reply)
    return {
        "reply": body,
        "sources": context["sources"][:6],
        "itinerary": context["itinerary"],
        "weather": context["weather"],
        "ticket_hits": context["ticket_hits"][:3],
        "suggested_questions": suggested,
        "intents": sorted(context["intents"]),
        "scenic_areas": context["scenic_areas"],
        "scenic_label": context["scenic_label"],
    }


def handle_chat(messages: list[dict], scenic_areas_hint: list[str] | None = None) -> dict:
    normalized = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
    last_user = next(
        (m["content"] for m in reversed(normalized) if m.get("role") == "user"),
        "",
    )

    if _is_out_of_scope(last_user):
        reply = (
            "抱歉，我是杭州智游助手，目前知识库只覆盖杭州的约 15 个热门景区，暂时无法查询其他城市或景区信息。"
            "欢迎继续咨询西湖、灵隐寺、西溪湿地、良渚、宋城等景区的门票、开放时间、路线和天气。"
        )
        return {
            "reply": reply,
            "sources": [],
            "itinerary": None,
            "weather": None,
            "ticket_hits": [],
            "suggested_questions": _hot_questions[:3],
            "intents": ["reject"],
            "scenic_areas": [],
            "scenic_label": "杭州",
        }

    if _is_greeting(last_user):
        try:
            reply = llm.chat(
                [
                    {
                        "role": "system",
                        "content": "你是杭州智游助手，用中文热情友好地简短回应，并提示可以询问西湖、灵隐寺、西溪湿地等景区的门票、开放时间、路线、天气。",
                    },
                    {"role": "user", "content": last_user},
                ],
                temperature=0.5,
                max_tokens=200,
            )
        except Exception:
            reply = "你好！我是杭州智游助手，可以为你介绍西湖、灵隐寺、西溪湿地、良渚古城遗址、宋城、运河等杭州热门景区，也可以帮你查门票、安排路线和看天气。"
        body, suggested = _parse_suggested(reply)
        return {
            "reply": body,
            "sources": [],
            "itinerary": None,
            "weather": None,
            "ticket_hits": [],
            "suggested_questions": suggested,
            "intents": ["greeting"],
            "scenic_areas": [],
            "scenic_label": "杭州",
        }

    context = _build_context(normalized, scenic_areas_hint=scenic_areas_hint)
    return _reply_with_fallback(normalized, context, last_user)


def stream_chat(messages: list[dict], scenic_areas_hint: list[str] | None = None):
    normalized = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]
    last_user = next(
        (m["content"] for m in reversed(normalized) if m.get("role") == "user"),
        "",
    )

    if _is_out_of_scope(last_user):
        reply = (
            "抱歉，我是杭州智游助手，目前知识库只覆盖杭州的约 15 个热门景区，暂时无法查询其他城市或景区信息。"
            "欢迎继续咨询西湖、灵隐寺、西溪湿地、良渚、宋城等景区的门票、开放时间、路线和天气。"
        )
        yield {
            "type": "meta",
            "intents": ["reject"],
            "sources": [],
            "itinerary": None,
            "weather": None,
            "ticket_hits": [],
            "scenic_areas": [],
            "scenic_label": "杭州",
        }
        yield {"type": "token", "text": reply}
        yield {
            "type": "done",
            "reply": reply,
            "suggested_questions": _hot_questions[:3],
            "intents": ["reject"],
            "sources": [],
            "itinerary": None,
            "weather": None,
            "ticket_hits": [],
            "scenic_areas": [],
            "scenic_label": "杭州",
        }
        return

    if _is_greeting(last_user):
        yield {
            "type": "meta",
            "intents": ["greeting"],
            "sources": [],
            "itinerary": None,
            "weather": None,
            "ticket_hits": [],
            "scenic_areas": [],
            "scenic_label": "杭州",
        }
        try:
            stream = llm.chat_stream(
                [
                    {
                        "role": "system",
                        "content": "你是杭州智游助手，用中文热情友好地简短回应，并提示可以询问西湖、灵隐寺、西溪湿地等景区的门票、开放时间、路线、天气。",
                    },
                    {"role": "user", "content": last_user},
                ],
                temperature=0.5,
                max_tokens=200,
            )
            full = ""
            for delta in stream:
                full += delta
                yield {"type": "token", "text": delta}
        except Exception:
            full = "你好！我是杭州智游助手，可以为你介绍西湖、灵隐寺、西溪湿地、良渚古城遗址、宋城、运河等杭州热门景区，也可以帮你查门票、安排路线和看天气。"
            yield {"type": "token", "text": full}
        body, suggested = _parse_suggested(full)
        yield {
            "type": "done",
            "reply": body,
            "suggested_questions": suggested,
            "intents": ["greeting"],
            "sources": [],
            "itinerary": None,
            "weather": None,
            "ticket_hits": [],
            "scenic_areas": [],
            "scenic_label": "杭州",
        }
        return

    context = _build_context(normalized, scenic_areas_hint=scenic_areas_hint)
    yield {
        "type": "meta",
        "intents": sorted(context["intents"]),
        "sources": context["sources"][:6],
        "itinerary": context["itinerary"],
        "weather": context["weather"],
        "ticket_hits": context["ticket_hits"][:3],
        "scenic_areas": context["scenic_areas"],
        "scenic_label": context["scenic_label"],
    }
    system_prompt, user_prompt = _build_prompts(context, normalized, last_user)
    try:
        stream = llm.chat_stream(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.25,
            max_tokens=1400,
        )
        full = ""
        for delta in stream:
            full += delta
            yield {"type": "token", "text": delta}
    except Exception:
        full = _local_answer(context, last_user)
        yield {"type": "token", "text": full}
    body, suggested = _parse_suggested(full)
    yield {
        "type": "done",
        "reply": body,
        "suggested_questions": suggested,
        "intents": sorted(context["intents"]),
        "sources": context["sources"][:6],
        "itinerary": context["itinerary"],
        "weather": context["weather"],
        "ticket_hits": context["ticket_hits"][:3],
        "scenic_areas": context["scenic_areas"],
        "scenic_label": context["scenic_label"],
    }


def hot_questions() -> list[str]:
    return _hot_questions
