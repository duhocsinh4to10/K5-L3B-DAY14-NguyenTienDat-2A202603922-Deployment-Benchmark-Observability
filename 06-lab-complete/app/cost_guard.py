"""
Cost guard (tiêu chí 8) — theo dõi và chặn chi phí LLM vượt ngân sách bằng Redis.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_fallback_daily_cost: dict[str, float] = {}
_fallback_monthly_cost: dict[str, float] = {}


def _period_keys() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    return f"cost:daily:{now.strftime('%Y-%m-%d')}", f"cost:monthly:{now.strftime('%Y-%m')}"


def _get_current_costs() -> tuple[float, float]:
    daily_key, monthly_key = _period_keys()
    if r is not None:
        try:
            vals = r.mget(daily_key, monthly_key)
            return float(vals[0] or 0.0), float(vals[1] or 0.0)
        except (RedisError, ValueError, TypeError):
            pass
    return (
        _fallback_daily_cost.get(daily_key, 0.0),
        _fallback_monthly_cost.get(monthly_key, 0.0),
    )


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_spent, monthly_spent = _get_current_costs()
    if daily_spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily LLM budget exceeded.",
        )
    if monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Monthly LLM budget exceeded.",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào Redis, trả về chi phí request (USD)."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    daily_key, monthly_key = _period_keys()
    if r is not None:
        try:
            pipe = r.pipeline()
            pipe.incrbyfloat(daily_key, cost)
            pipe.expire(daily_key, 2 * 24 * 3600)
            pipe.incrbyfloat(monthly_key, cost)
            pipe.expire(monthly_key, 32 * 24 * 3600)
            pipe.execute()
            return cost
        except RedisError:
            pass

    _fallback_daily_cost[daily_key] = _fallback_daily_cost.get(daily_key, 0.0) + cost
    _fallback_monthly_cost[monthly_key] = _fallback_monthly_cost.get(monthly_key, 0.0) + cost
    return cost
