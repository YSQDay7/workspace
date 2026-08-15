import json
import re

from . import config
from .redis_client import get_redis

PUNCT_RE = re.compile(r"[\s，。！？、,.!?;；:：\"'“”‘’（）()\[\]【】\-—_—]+")


def normalize_question(question: str) -> str:
    return PUNCT_RE.sub("", (question or "").strip()).lower()[:120]


def record_question(
    question: str,
    hit: bool = True,
    session_id: int | None = None,
    user_id: int | None = None,
) -> None:
    norm = normalize_question(question)
    if not norm:
        return
    redis = get_redis()
    redis.zincrby("hot:questions", 1, norm)
    if not redis.hexists("hot:question_text", norm):
        redis.hset("hot:question_text", norm, (question or "").strip()[:200])
    from .storage import log_question

    log_question(question, norm, hit, session_id, user_id)


def _get_hot_answer(question: str, norm: str) -> dict:
    redis = get_redis()
    cached = redis.get(f"hot:answer:{norm}")
    if cached:
        return json.loads(cached)
    from . import agent

    result = agent.handle_chat([{"role": "user", "content": question}])
    answer = {
        "reply": result["reply"],
        "sources": result["sources"][:3],
        "suggested_questions": result["suggested_questions"][:2],
    }
    redis.setex(
        f"hot:answer:{norm}",
        config.HOT_ANSWER_TTL_SECONDS,
        json.dumps(answer, ensure_ascii=False),
    )
    return answer


def get_hot_questions(limit: int | None = None) -> list[dict]:
    limit = limit or config.HOT_QUESTION_TOP_N
    redis = get_redis()
    items = redis.zrevrange("hot:questions", 0, limit - 1, withscores=True)
    hot = []
    for norm, score in items:
        question = redis.hget("hot:question_text", norm) or norm
        answer = _get_hot_answer(question, norm)
        hot.append(
            {
                "question": question,
                "count": int(score),
                "reply": answer.get("reply", ""),
                "sources": answer.get("sources", []),
                "suggested_questions": answer.get("suggested_questions", []),
            }
        )
    return hot
