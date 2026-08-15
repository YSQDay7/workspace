import redis

from . import config

_pool = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(config.REDIS_URL, decode_responses=True)
    return redis.Redis(connection_pool=_pool)

