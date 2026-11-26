# Deployment Information — Day 14 Final Project

> Deploy trực tiếp thư mục `06-lab-complete/` (Production AI Agent) kèm dịch vụ Redis trên cloud.

## Public URL
`https://<your-agent-domain>.up.railway.app` *(cập nhật URL thật sau khi chạy `railway domain` hoặc deploy trên Render)*

## Platform
Railway (hoặc Render) — build từ `06-lab-complete/Dockerfile` theo `06-lab-complete/railway.toml` / `render.yaml`

## Environment Variables Set (trên Cloud Dashboard — KHÔNG commit secret vào Git)
- `PORT` (nền tảng tự inject)
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`
- `AGENT_API_KEY` *(đặt trên Dashboard, không ghi vào code)*
- `REDIS_URL` *(trỏ tới Redis add-on trên nền tảng)*
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Test Commands (4 lệnh tự kiểm CP6)

Đặt `BASE` là Public URL và `AGENT_API_KEY` là key đã cấu hình trên nền tảng:

```bash
export BASE="https://<your-agent-domain>.up.railway.app"
export AGENT_API_KEY="<your-secret-key>"

# 1. Liveness check → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check (kiểm tra kết nối Redis) → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Gọi /ask không có API key → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Gọi /ask có API key hợp lệ → 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
