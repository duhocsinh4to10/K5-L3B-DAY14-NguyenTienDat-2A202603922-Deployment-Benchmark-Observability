# Deployment Information — Day 14 Final Project

> Deploy trực tiếp thư mục `06-lab-complete/` (Production AI Agent) kèm dịch vụ Managed Key Value (Redis) trên **Render** bằng Blueprint (`render.yaml`).

## Public URL
https://day14-production-agent-yqmv.onrender.com

## Platform
**Render** (Free tier — Singapore region)
- Web Service: `day14-production-agent` (`runtime: docker`, `rootDir: 06-lab-complete`, `healthCheckPath: /health`)
- Redis / Key Value: `day14-redis` (`plan: free`, `maxmemoryPolicy: allkeys-lru`, internal private network)

## Environment Variables Set (trên Render Dashboard — KHÔNG commit secret vào Git)
- `PORT` (Render tự inject)
- `ENVIRONMENT=production`
- `LOG_LEVEL=INFO`
- `AGENT_API_KEY` *(tự sinh bằng `generateValue: true` trên Render, không ghi vào code)*
- `REDIS_URL` *(tự động nối từ service `day14-redis` qua `fromService.property: connectionString`)*
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Test Commands & Real Results (4 lệnh tự kiểm CP6)

Đặt `BASE` là Public URL và `AGENT_API_KEY` là key trong tab Environment của Render:

```bash
export BASE="https://day14-production-agent-yqmv.onrender.com"
export AGENT_API_KEY="<your-secret-key>"

# 1. Liveness check → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Output: 200  ({"status":"ok","environment":"production","uptime_seconds":148.4})

# 2. Readiness check (kiểm tra kết nối Redis) → 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Output: 200  ({"ready":true,"redis":"connected"})

# 3. Gọi /ask không có API key → 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Output: 401

# 4. Gọi /ask có API key hợp lệ → 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Output: 200  ({"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","environment":"production","usage":{"input_tokens":1,"output_tokens":16,"cost_usd":9.75e-06}})
```

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
