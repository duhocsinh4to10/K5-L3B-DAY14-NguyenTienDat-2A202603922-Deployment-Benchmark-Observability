# Day 14 Lab — Mission Answers

> **Học viên:** Nguyen Tien Dat (`2A202603922`) — Lớp `K5-L3B`

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

Đọc `01-localhost-vs-production/develop/app.py` và đối chiếu với `01-localhost-vs-production/production/app.py` & `config.py`, phát hiện **7 anti-patterns** nghiêm trọng:

1. **Hardcode secret trong mã nguồn** (`develop/app.py` dòng 17–18):
   - Khai báo cứng `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên Git, toàn bộ secret bị lộ vĩnh viễn trong lịch sử commit.
   - *Cách `production` khắc phục:* `production/config.py` (dòng 27, 32) đọc toàn bộ cấu hình nhạy cảm từ biến môi trường (`os.getenv("OPENAI_API_KEY", "")`, `os.getenv("AGENT_API_KEY", "")`) và gọi `validate()` (dòng 37–46) để fail-fast nếu thiếu key ở môi trường `production`.
2. **Dùng `print()` thay cho structured logging và in trực tiếp secret ra log** (`develop/app.py` dòng 33–38):
   - Dòng 34 chạy `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm rò rỉ API key thẳng ra stdout/log hệ thống; dạng text tự do cũng rất khó lọc, tìm kiếm trên các log aggregator (Loki, Datadog, Cloud Logging).
   - *Cách `production` khắc phục:* `production/app.py` (dòng 28–32, 111–122) cấu hình `logging` xuất định dạng JSON có trường `time`, `level`, `msg`, `event`, `question_length`, `client_ip` và tuyệt đối không log secret.
3. **Hardcode cấu hình ứng dụng và bật `DEBUG = True`, `reload=True`** (`develop/app.py` dòng 21–22, 53):
   - `DEBUG = True` và `uvicorn.run(..., reload=True)` tiêu tốn CPU/RAM theo dõi file, có nguy cơ lộ stack trace và tự restart bất ngờ trên production.
   - *Cách `production` khắc phục:* `production/config.py` (dòng 19) đọc `DEBUG` mặc định `"false"`, và `production/app.py` (dòng 198) chỉ bật `reload=settings.debug`.
4. **Không có Health Check / Readiness endpoints** (`develop/app.py` dòng 42–43):
   - Không có `/health` và `/ready`, nên cloud platform hoặc orchestrator không biết container còn sống hay bị treo để tự restart, còn load balancer không biết khi nào app sẵn sàng nhận traffic.
   - *Cách `production` khắc phục:* `production/app.py` cung cấp `GET /health` (liveness probe, dòng 135–149) và `GET /ready` (readiness probe trả `503` khi chưa sẵn sàng, dòng 152–161).
5. **Bind cố định `host="localhost"` và `port=8000`** (`develop/app.py` dòng 51–52):
   - `host="localhost"` chỉ nhận kết nối nội bộ loopback; khi đóng gói vào Docker hoặc deploy lên cloud, traffic từ bên ngoài container sẽ không truy cập được. `port=8000` cố định cũng khiến app lỗi trên Railway/Render vì nền tảng cấp port động qua biến `PORT`.
   - *Cách `production` khắc phục:* `production/config.py` (dòng 17–18) mặc định `HOST="0.0.0.0"` và đọc `PORT` từ biến môi trường.
6. **Không có Graceful Shutdown / Lifecycle management** (`develop/app.py`):
   - Khi platform gửi tín hiệu `SIGTERM` để dừng/deploy phiên bản mới, process tắt đột ngột và cắt ngang các request đang xử lý (`in-flight`), không đóng sạch kết nối.
   - *Cách `production` khắc phục:* `production/app.py` dùng `lifespan` (dòng 39–67) để đặt `is_ready = False` khi shutdown và chờ hoàn thành request, kết hợp bắt `signal.SIGTERM` (dòng 180–189).
7. **Nhận input qua query string và thiếu cấu hình CORS/validation chặt chẽ** (`develop/app.py` dòng 30–31):
   - `POST /ask` nhận `question` qua query parameter (`?question=...`) dễ bị lưu vào access log URL, giới hạn độ dài URL và không chuẩn REST cho payload văn bản dài; đồng thời không có middleware CORS.
   - *Cách `production` khắc phục:* `production/app.py` (dòng 77–82, 102–108) đọc JSON body, kiểm tra thiếu trường `question` trả `422` và cấu hình `CORSMiddleware` dựa trên `ALLOWED_ORIGINS`.

---

### Exercise 1.2: Kết quả chạy thực tế bản Develop và Production

**1. Chạy `01-localhost-vs-production/develop/app.py`:**

- Gọi `GET http://localhost:8000/`:
```http
HTTP/1.1 200 OK
content-type: application/json

{"message":"Hello! Agent is running on my machine :)"}
```

- Gọi `POST "http://localhost:8000/ask?question=Hello"`:
```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

- Log in ra terminal của server develop (cho thấy lỗi rò rỉ secret trực tiếp qua `print()`):
```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.
```

**2. Chạy `01-localhost-vs-production/production/app.py`:**

- Gọi `GET http://localhost:8000/health`:
```http
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","uptime_seconds":2.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T09:07:48.176036+00:00"}
```

- Gọi `GET http://localhost:8000/ready`:
```http
HTTP/1.1 200 OK
content-type: application/json

{"ready":true}
```

- Gọi `POST http://localhost:8000/ask` với JSON body `{"question":"Hello"}`:
```json
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

---

### Exercise 1.3: Bảng so sánh Develop vs Production

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Config & Secrets** | Hardcode trực tiếp `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `PORT=8000` trong code | Đọc toàn bộ từ biến môi trường (`os.getenv`), tập trung trong class `Settings` kèm `validate()` | Tuân thủ 12-Factor App: cùng một bản build chạy được trên dev/staging/production, không làm lộ secret trong Git và dễ xoay vòng key (rotate). |
| **Network Binding** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, đọc `PORT` động, `reload=settings.debug` (mặc định `False`) | Container/cloud yêu cầu bind `0.0.0.0` mới nhận được traffic từ bên ngoài; nền tảng PaaS cấp `PORT` động; tắt `reload` tránh tốn tài nguyên và crash bất ngờ. |
| **Health & Readiness** | Không có `/health` và `/ready` | Có `GET /health` (liveness + uptime) và `GET /ready` (readiness trả `503` khi chưa sẵn sàng) | Platform dựa vào `/health` để tự restart container bị treo; Load Balancer dựa vào `/ready` để chỉ đẩy traffic vào instance đã khởi tạo xong và không gửi request khi đang tắt. |
| **Logging** | Dùng `print()` dạng text tự do, in cả API key ra màn hình | Dùng `logging` định dạng JSON có cấu trúc (`time`, `level`, `event`, metadata), không log secret | Log JSON giúp các hệ thống giám sát (Loki, Datadog, Cloud Logging) parse, lọc, đếm lỗi và cảnh báo tự động mà không làm lộ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột khi nhận tín hiệu dừng | Dùng FastAPI `lifespan` + bắt `SIGTERM`, hạ cờ `is_ready = False` trước khi thoát | Đảm bảo Zero-downtime deployment: hoàn thành nốt các request đang xử lý (`in-flight`) và đóng kết nối DB/Redis an toàn, không trả lỗi 502/504 cho người dùng. |
| **API Input & CORS** | `POST /ask` dùng query parameter `?question=...`, không có CORS | `POST /ask` đọc JSON body có kiểm tra `422`, có `CORSMiddleware` giới hạn `ALLOWED_ORIGINS` | Tránh lộ nội dung câu hỏi trên access log URL, hỗ trợ payload dài và ngăn truy cập trái phép từ domain lạ trên trình duyệt. |

---

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy Agent Part 6 lên Cloud (Railway / Render)

- **Nền tảng:** Railway / Render *(cập nhật sau khi deploy service `06-lab-complete/` kèm Redis trên cloud)*
- **Public URL:** *(điền URL thật sau khi deploy, xem [DEPLOYMENT.md](DEPLOYMENT.md))*
- **Screenshots:**
  - [Dashboard](screenshots/dashboard.png)
  - [Service Running](screenshots/running.png)
  - [Self-Test Results (200 / 200 / 401 / 200)](screenshots/test.png)

---

### Exercise 3.2: So sánh `railway.toml` với `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Tại sao khác nhau? |
| :--- | :--- | :--- | :--- |
| **Định dạng & Phạm vi** | Định dạng TOML, cấu hình **một service** duy nhất (`[build]`, `[deploy]`). | Định dạng YAML theo chuẩn Infrastructure as Code (Blueprint), khai báo được **cả stack nhiều service** trong cùng 1 file (`services:` gồm web + Redis). | Railway quản lý từng service và add-on (Redis, Postgres) theo project trên Dashboard/CLI rồi nối biến môi trường; Render dùng Blueprint để đồng bộ toàn bộ hạ tầng từ Git. |
| **Cách build & chạy** | Khai báo `builder = "DOCKERFILE"` (hoặc `"NIXPACKS"`), `dockerfilePath`, `startCommand`. | Khai báo `type: web`, `runtime: docker` (hoặc `python`), `dockerfilePath` / `buildCommand` & `startCommand`, kèm `region`, `plan`, `autoDeploy`. | Render yêu cầu mô tả tường minh loại service, gói tài nguyên (`plan: free`) và vùng triển khai (`region: singapore`) ngay trong file IaC. |
| **Health check & Restart** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30`, `restartPolicyType = "ON_FAILURE"`, `restartPolicyMaxRetries = 3`. | `healthCheckPath: /health` (nền tảng tự quản lý chính sách restart và zero-downtime deploy). | Cả hai đều cần `/health` để kiểm tra container sống; Railway cho tinh chỉnh chi tiết timeout và số lần retry ngay trong file TOML. |
| **Quản lý biến môi trường & Secret** | **Không** khai báo biến môi trường trong `railway.toml`; đặt qua Dashboard hoặc `railway variables set ...`. | Cho phép khai báo `envVars:` trực tiếp trong `render.yaml`, dùng `generateValue: true` (tự sinh key ngẫu nhiên) hoặc `sync: false` (nhập tay trên Dashboard) để **không lộ secret trong Git**. | Render Blueprint thiết kế để tái tạo nhanh cả cấu hình biến môi trường khi clone repo mới mà vẫn giữ an toàn cho secret. |

---

### Exercise 3.3: Phân tích CI/CD Pipeline của GCP Cloud Run (`cloudbuild.yaml` & `service.yaml`)

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động chạy khi push lên nhánh `main` đi qua **4 bước tuần tự** (`waitFor`):
1. **`test` (`python:3.11-slim`):** Cài dependencies và chạy `pytest tests/ -v --tb=short` — nếu test lỗi thì dừng pipeline ngay, không build/deploy.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image gắn 2 tag (`$COMMIT_SHA` để truy vết/rollback và `latest`), tận dụng `--cache-from=...:latest` để tăng tốc build.
3. **`push` (`gcr.io/cloud-builders/docker`):** Đẩy toàn bộ tags lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcr.io/cloud-builders/gcloud`):** Deploy image theo `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình tài nguyên (`512Mi` RAM, `1 CPU`, `timeout=60s`), auto-scaling (`min-instances=1` tránh cold start, `max-instances=10`, `containerConcurrency=80`), gắn secret an toàn từ **Secret Manager** (`--set-secrets` / `secretKeyRef`) và kiểm tra `livenessProbe` (`/health`) cùng `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

**Phân tích mã nguồn:**
- **API key được kiểm tra ở đâu?** Tại hàm dependency `verify_api_key` (`04-api-gateway/develop/app.py` dòng 39–54) đọc header `X-API-Key` qua `APIKeyHeader(name="X-API-Key", auto_error=False)`, được gắn vào endpoint `POST /ask` bằng `Depends(verify_api_key)` (dòng 70). Các endpoint public như `/` và `/health` không yêu cầu key.
- **Điều gì xảy ra nếu thiếu hoặc sai key?** Thiếu header `X-API-Key` trả `HTTP 401 Unauthorized`; sai key trả `HTTP 403 Forbidden` (ở Part 6 production sẽ chuẩn hóa trả `401` cho cả thiếu và sai key theo hợp đồng).
- **Làm sao xoay vòng (rotate) API key không gây downtime?** Hỗ trợ danh sách nhiều key hợp lệ cùng lúc (ví dụ biến môi trường `AGENT_API_KEYS=old-key,new-key`): (1) thêm key mới song song key cũ, (2) cập nhật client sang key mới, (3) xác nhận không còn traffic dùng key cũ rồi gỡ key cũ và thu hồi (revoke).

**Kết quả chạy thực tế (`AGENT_API_KEY=secret-key-123 python app.py`):**

1. Không có API key (`401`):
```http
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. Sai API key (`403`):
```http
HTTP/1.1 403 Forbidden
content-type: application/json

{"detail":"Invalid API key."}
```

3. Có API key hợp lệ (`200`):
```http
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

**Phân tích JWT (`auth.py`) & Rate Limiter (`rate_limiter.py`):**
- **Luồng JWT:** Client gửi `username`/`password` lên `POST /auth/token` → server xác thực và ký JWT bằng thuật toán `HS256` chứa `sub`, `role`, `iat`, `exp` (hết hạn sau 60 phút). Khi gọi `POST /ask` với `Authorization: Bearer <token>`, `verify_token()` xác minh chữ ký và hạn dùng stateless (không cần query DB mỗi request).
- **Thuật toán Rate Limiting:** `Sliding Window Counter` (dùng `deque` lưu timestamp các request trong cửa sổ `window_seconds = 60` giây; mỗi request mới sẽ `popleft()` các timestamp cũ hơn `now - 60`).
- **Giới hạn & Phân quyền (bypass/nâng hạn mức cho admin):** Trong `rate_limiter.py` (dòng 86–87) và `app.py` (dòng 141), user thường (`student`, role `user`) giới hạn **10 requests/phút** (`rate_limiter_user`), còn admin (`teacher`, role `admin`) có hạn mức **100 requests/phút** (`rate_limiter_admin`) — hoặc có thể bỏ qua bước `limiter.check()` nếu `role == "admin"`.

**Kết quả chạy thực tế (`POST /auth/token` với `student` / `demo123` → token đã che `eyJhbGciOiJIUzI...<REDACTED>`):**

1. Request đầu tiên với JWT hợp lệ (`200 OK`):
```http
HTTP/1.1 200 OK
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

2. Vòng lặp gửi liên tiếp 12 request (Request 1–10 trả `200 OK`, từ Request 11 vượt 10 req/phút trả `429 Too Many Requests`):
```text
Req 2  -> HTTP/1.1 200 OK
Req 3  -> HTTP/1.1 200 OK
Req 4  -> HTTP/1.1 200 OK
Req 5  -> HTTP/1.1 200 OK
Req 6  -> HTTP/1.1 200 OK
Req 7  -> HTTP/1.1 200 OK
Req 8  -> HTTP/1.1 200 OK
Req 9  -> HTTP/1.1 200 OK
Req 10 -> HTTP/1.1 200 OK
Req 11 -> HTTP/1.1 429 Too Many Requests
Req 12 -> HTTP/1.1 429 Too Many Requests
```

3. Response chi tiết khi chạm ngưỡng Rate Limit (`429`):
```http
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795684671
retry-after: 59
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

4. Kiểm tra usage tại `GET /me/usage`:
```json
{"user_id":"student","date":"2026-11-26","requests":10,"input_tokens":40,"output_tokens":288,"cost_usd":0.000179,"budget_usd":1.0,"budget_remaining_usd":0.999821,"budget_used_pct":0.0}
```

---

### Exercise 4.4: Thiết kế Cost Guard & Vì sao cần cả Rate Limit lẫn Cost Guard

- **Cách triển khai Cost Guard trong production (dùng Redis):**
  - Tạo key theo chu kỳ ngày/tháng trên Redis, ví dụ `cost:daily:<YYYY-MM-DD>` hoặc `budget:<user_id>:<YYYY-MM>`.
  - **Trước khi gọi LLM (`check_budget`):** đọc tổng chi phí hiện tại từ Redis (`GET`). Nếu `current_cost >= budget_limit` (hoặc `current_cost + estimated_cost > budget_limit`), chặn ngay bằng `HTTP 402 Payment Required` (và ghi log cảnh báo khi vượt 80% ngân sách).
  - **Sau khi gọi LLM (`record_cost`):** tính chi phí thực tế theo bảng giá token: `(input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K`, cộng dồn atomic bằng `INCRBYFLOAT` và đặt `EXPIRE` (ví dụ 2 ngày cho daily budget hoặc 32 ngày cho monthly budget) để tự động reset.
- **Vì sao cần đồng thời cả Rate Limit và Cost Guard?**
  - **Rate Limit bảo vệ tốc độ (traffic / chống spam / chống DDoS):** giới hạn số request trên mỗi đơn vị thời gian (req/phút), nhưng không phân biệt request ngắn (10 tokens) với request cực dài (50.000 tokens). Kẻ tấn công vẫn có thể gửi đều đặn dưới ngưỡng rate limit với prompt rất dài để đốt sạch tiền API.
  - **Cost Guard bảo vệ ngân sách (tiền):** chặn tổng chi phí cộng dồn theo ngày/tháng, nhưng không ngăn được đột biến lưu lượng (burst) làm quá tải CPU/worker tức thời. Vì vậy production cần cả hai lớp bảo vệ song song.

---

## AI Log

- **CP1 (Part 1):**
  - *Hỏi gì:* Nhờ AI đọc code `01-localhost-vs-production/develop/app.py`, `production/app.py`, `production/config.py`, chạy kiểm thử thực tế cả hai server để thu output HTTP/stdout và tổng hợp câu trả lời Part 1 theo yêu cầu đề bài.
  - *Nhận gì:* Danh sách 7 anti-patterns có trích dẫn dòng code cụ thể, bảng so sánh Develop vs Production, cùng kết quả chạy thực tế.
  - *Tự sửa và tự kiểm tra:* Đã chạy trực tiếp cả `develop/app.py` và `production/app.py` trên máy để xác nhận thực tế endpoint `POST /ask?question=Hello` của bản develop in lộ key `sk-hardcoded-fake-key-never-do-this`, còn bản production trả `200 OK` cho `/health`, `/ready` và `POST /ask` dạng JSON.
- **CP3 (Part 4):**
  - *Hỏi gì:* Nhờ AI đọc code `04-api-gateway/develop/app.py`, `production/app.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, chạy kiểm thử API Key, JWT và vòng lặp kích hoạt HTTP 429, sau đó tổng hợp câu trả lời Part 4 vào `MISSION_ANSWERS.md`.
  - *Nhận gì:* Kết quả chạy thực tế `401`, `403`, `200`, `429`, `/me/usage` (đã che JWT token) cùng phần giải thích cơ chế Sliding Window và thiết kế Cost Guard với Redis.
  - *Tự sửa và tự kiểm tra:* Đã chạy trực tiếp server develop với `AGENT_API_KEY=secret-key-123` và server production với tài khoản `student`/`demo123`, xác nhận request thứ 11 bị chặn với `HTTP 429` và header `retry-after: 59`.
- **CP7 (Part 7 Bước 1 — Benchmark Local & Eval):**
  - *Hỏi gì:* Nhờ AI thêm Histogram `agent_question_length_chars`, chạy đủ 7 kịch bản load test + 3 lần eval (`v1`, `v2`, `v2_fixed`), bổ sung 2 mục thiếu vào `KNOWLEDGE_BASE`, viết `.github/workflows/eval.yml` và tổng hợp số liệu thật vào `BENCHMARK_REPORT.md`.
  - *Nhận gì:* 10 file JSON đo thật trong `reports/`, workflow CI quality gate và bảng phân tích SLO/tail latency/cost-per-correct trong `BENCHMARK_REPORT.md`.
  - *Tự sửa và tự kiểm tra:* Đã đối chiếu từng con số trong `BENCHMARK_REPORT.md` khớp chính xác với 10 file JSON; chạy `eval/run_eval.py --min-accuracy 1.0 --baseline reports/eval_v2.json` xác nhận đạt `100.0% (23/23)`, `0 regression`, `Quality gate ✅ PASS`.
- **CP5 (Part 6 — Final Project `06-lab-complete/`):**
  - *Hỏi gì:* Nhờ AI hoàn thiện toàn bộ 12 file TODO trong `06-lab-complete/` (`config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) theo đúng bảng hợp đồng trong `06-lab-complete/README.md`.
  - *Nhận gì:* Code FastAPI production-ready với Redis sliding-window rate limit, Redis daily/monthly cost guard, API key auth (401), JSON logging, lifespan + SIGTERM graceful shutdown và multi-stage Dockerfile non-root.
  - *Tự sửa và tự kiểm tra:* Đã chạy `python check_production_ready.py --static-only` đạt **28/28 static checks** và `--skip-docker` đạt **36/37 checks** (chỉ còn 1 mục `/ready` 200 + các mục Docker/SIGTERM cần chạy lại trong WSL2 khi bật Docker Desktop để lấy `PASS 12/12`).
- **CP6 (Part 3 — Cloud Deployment):**
  - *Hỏi gì:* Nhờ AI đọc `03-cloud-deployment/railway/railway.toml`, `render/render.yaml`, `production-cloud-run/cloudbuild.yaml`, `service.yaml` để viết phần so sánh Railway vs Render, phân tích CI/CD Cloud Run (Exercise 3.3) và tạo khung `DEPLOYMENT.md`.
  - *Nhận gì:* Bảng so sánh chi tiết `railway.toml` vs `render.yaml`, tóm tắt 4 bước pipeline Cloud Build/Cloud Run và file `DEPLOYMENT.md` kèm 4 lệnh tự kiểm CP6.
  - *Tự sửa và tự kiểm tra:* Đã đối chiếu đúng tên trường cấu hình trong từng file (`builder`, `healthcheckPath`, `sync: false`, `generateValue: true`, `minScale`, `secretKeyRef`). Phần Public URL và 3 screenshot sẽ cập nhật sau khi deploy lên Railway/Render.
