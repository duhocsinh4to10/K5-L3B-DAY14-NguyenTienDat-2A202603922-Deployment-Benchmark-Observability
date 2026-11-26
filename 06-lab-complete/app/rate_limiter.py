"""
Rate limiting (tiêu chí 7) — Sliding window 60 giây lưu trong Redis Sorted Set.

State lưu trong Redis để mọi worker / instance dùng chung và tồn tại qua restart.
"""
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60
_fallback_windows: dict[str, deque] = defaultdict(deque)


def check_rate_limit(key: str) -> None:
    """Kiểm tra giới hạn RATE_LIMIT_PER_MINUTE trong cửa sổ 60 giây."""
    limit = settings.rate_limit_per_minute
    now = time.time()
    window_start = now - WINDOW_SECONDS

    if r is not None:
        redis_key = f"ratelimit:{key}"
        try:
            pipe = r.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            _, current_count = pipe.execute()

            if current_count >= limit:
                oldest = r.zrange(redis_key, 0, 0, withscores=True)
                retry_after = (
                    max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
                    if oldest
                    else WINDOW_SECONDS
                )
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )

            member = f"{now}:{uuid.uuid4().hex}"
            pipe = r.pipeline()
            pipe.zadd(redis_key, {member: now})
            pipe.expire(redis_key, WINDOW_SECONDS + 5)
            pipe.execute()
            return
        except HTTPException:
            raise
        except RedisError:
            pass

    # Fallback in-memory chỉ khi chạy local không có Redis
    window = _fallback_windows[key]
    while window and window[0] < window_start:
        window.popleft()
    if len(window) >= limit:
        retry_after = max(1, int(window[0] + WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    window.append(now)
