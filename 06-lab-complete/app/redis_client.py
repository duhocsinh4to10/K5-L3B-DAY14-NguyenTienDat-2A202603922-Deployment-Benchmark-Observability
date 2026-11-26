"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

Không ping Redis lúc import để app vẫn khởi động được khi Redis chưa sẵn sàng.
"""
from typing import Optional

import redis

from app.config import settings


def _create_client() -> Optional[redis.Redis]:
    url = (settings.redis_url or "").strip()
    if not url:
        return None
    try:
        return redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1.5,
            socket_timeout=1.5,
        )
    except Exception:
        return None


r: Optional[redis.Redis] = _create_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho endpoint GET /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False


def close_redis() -> None:
    """Đóng Redis connection pool khi shutdown."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
