"""
Production AI Agent — Part 6 Final Project.

Đáp ứng đủ 12 tiêu chí Production Readiness:
  - /health (liveness) & /ready (readiness kiểm tra Redis)
  - API Key auth (X-API-Key → 401)
  - Rate limiting sliding window trên Redis (→ 429 + Retry-After)
  - Cost guard trên Redis (→ 402)
  - Config 12-Factor từ biến môi trường
  - Structured JSON logging
  - Graceful shutdown khi nhận SIGTERM
"""
import json
import logging
import signal
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import close_redis, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Mỗi dòng log của app là một JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "env": settings.environment,
        }
        if isinstance(record.msg, dict):
            payload.update(record.msg)
        else:
            payload["msg"] = record.getMessage()
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        return json.dumps(payload, ensure_ascii=False)


def _setup_logger() -> logging.Logger:
    app_logger = logging.getLogger("production_agent")
    app_logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        app_logger.addHandler(handler)
    return app_logger


logger = _setup_logger()
START_TIME = time.time()


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, {"event": event, **fields})


def _register_sigterm_handler() -> None:
    """Ghi log JSON khi nhận SIGTERM và gọi lại handler gốc của uvicorn."""
    if threading.current_thread() is not threading.main_thread():
        return
    previous = signal.getsignal(signal.SIGTERM)

    def _on_sigterm(signum, frame):
        log_event("sigterm_received", signal=signum)
        if callable(previous):
            previous(signum, frame)

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    _register_sigterm_handler()
    log_event(
        "startup",
        port=settings.port,
        environment=settings.environment,
        rate_limit_per_minute=settings.rate_limit_per_minute,
        redis_connected=redis_healthy(),
    )
    yield
    log_event("shutdown_start")
    close_redis()
    log_event("shutdown_complete")


app = FastAPI(
    title="Production AI Agent",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        log_event(
            "unhandled_exception",
            level=logging.ERROR,
            method=request.method,
            path=request.url.path,
        )
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
    finally:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        log_event(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=status_code,
            ms=elapsed_ms,
        )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default=None, max_length=128)


@app.get("/health")
def health():
    """Liveness probe — luôn trả 200 khi process còn sống, không phụ thuộc Redis."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/ready")
def ready():
    """Readiness probe — 200 khi Redis kết nối được, 503 khi mất kết nối Redis."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis is not ready")
    return {"ready": True, "redis": "connected"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question) // 4)
    output_tokens = max(1, len(answer) // 4)
    cost_usd = record_cost(input_tokens, output_tokens)

    log_event(
        "ask_completed",
        user_id=body.user_id or "anonymous",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 8),
    )

    return {
        "question": body.question,
        "answer": answer,
        "environment": settings.environment,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost_usd, 8),
        },
    }
