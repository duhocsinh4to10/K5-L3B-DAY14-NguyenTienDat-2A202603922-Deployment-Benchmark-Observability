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

## AI Log

- **CP1 (Part 1):**
  - *Hỏi gì:* Nhờ AI đọc code `01-localhost-vs-production/develop/app.py`, `production/app.py`, `production/config.py`, chạy kiểm thử thực tế cả hai server để thu output HTTP/stdout và tổng hợp câu trả lời Part 1 theo yêu cầu đề bài.
  - *Nhận gì:* Danh sách 7 anti-patterns có trích dẫn dòng code cụ thể, bảng so sánh Develop vs Production, cùng kết quả chạy thực tế.
  - *Tự sửa và tự kiểm tra:* Đã chạy trực tiếp cả `develop/app.py` và `production/app.py` trên máy để xác nhận thực tế endpoint `POST /ask?question=Hello` của bản develop in lộ key `sk-hardcoded-fake-key-never-do-this`, còn bản production trả `200 OK` cho `/health`, `/ready` và `POST /ask` dạng JSON.
