# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được đo trực tiếp từ `load_test.py`, `eval/run_eval.py` và đối chiếu 100% với các file JSON trong thư mục `reports/` và CSV trong `benchmark-results/`.

**Họ tên:** Nguyen Tien Dat (`2A202603922`) — Lớp `K5-L3B`  
**Ngày chạy:** 2026-11-26  
**Môi trường:** Windows 11, Python 3.14 (`.venv`), WSL2 Ubuntu + Docker Desktop

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | 95% người dùng nhận phản hồi trong nửa giây cho trải nghiệm hội thoại mượt mà, phù hợp với baseline mock LLM (~150–250ms) cộng thêm bước retrieval (~20ms) và một chút dư địa cho jitter. |
| Error rate `/ask` | ≤ 2.0 % | Cho phép error budget 2% để hấp thu lỗi upstream ngẫu nhiên (~1% ở `MOCK_ERROR_RATE=0.01`) mà không gây cảnh báo giả, đồng thời phát hiện sớm khi lỗi tăng bất thường. |
| Accuracy trên golden dataset | ≥ 85 % (mục tiêu sau sửa KB: 100%) | Đảm bảo agent RAG trả lời đúng tối thiểu 85% bộ câu hỏi chuẩn trước khi merge PR và không có bất kỳ câu nào bị regression so với baseline. |

---

## 2. Benchmark hiệu năng (`develop/`, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, `--requests 300`, `MOCK_SLOW_RATE=0.03`)

*(Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`)*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO (p95 ≤ 500ms, err ≤ 2%) |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 3.68 | 206.4 | 247.4 | 1715.7 | 1.00% | ✅ PASS |
| 10 | 39.00 | 203.2 | 467.2 | 1719.4 | 1.00% | ✅ PASS |
| 50 | 49.86 | 499.6 | 2545.8 | 3679.8 | 0.67% | ❌ FAIL (p95 > 500ms) |
| 100 | 36.44 | 1237.7 | 5430.8 | 5889.6 | 2.00% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ concurrency 1 lên 10, RPS tăng gần tuyến tính (~10.6× từ `3.68` lên `39.00 req/s`) vì tiến trình async của FastAPI/Uvicorn tận dụng tốt thời gian chờ I/O (`asyncio.sleep`). Tuy nhiên khi lên 50 và 100, single-worker process và hàng đợi kết nối của OS bắt đầu bão hòa (saturation): RPS đạt đỉnh `49.86 req/s` ở `c=50` rồi **giảm** xuống `36.44 req/s` ở `c=100`, trong khi `p95` tăng vọt từ `247.4 ms` lên `5430.8 ms` do request phải xếp hàng chờ xử lý.

### 2.2 Tail latency (agent v2, `--requests 300 --concurrency 20`)

*(Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`)*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| `0` | 229.6 | 505.8 | 555.7 |
| `0.03` (mặc định) | 253.8 | 519.5 | 1711.8 |
| `0.1` | 411.2 | 1713.3 | 1751.4 |

**Nhận xét:** **p99** (và sau đó là **p95** khi tỷ lệ chậm vượt 5%) là chỉ số nhạy nhất với các request chậm bất thường:
- Ở `MOCK_SLOW_RATE=0.03` (3% request chậm thêm ~1.5s), `avg` chỉ tăng nhẹ `+24.2 ms` (`229.6 → 253.8 ms`), nhưng `p99` nhảy vọt gấp hơn 3 lần (`555.7 → 1711.8 ms`).
- Ở `MOCK_SLOW_RATE=0.1` (10% request chậm, vượt ngưỡng 5% đuôi của p95), `p95` lập tức tăng vọt lên `1713.3 ms` trong khi `avg` mới ở mức `411.2 ms`.
- **Vì sao SLO không đặt theo average?** Giá trị trung bình làm mượt và che giấu nhóm người dùng gặp tail latency. Nếu chỉ nhìn `avg = 411.2 ms`, đội vận hành sẽ tưởng hệ thống đạt mục tiêu `< 500 ms` trong khi thực tế cứ 10 người dùng lại có 1 người phải chờ gần 2 giây.

---

## 3. Benchmark chất lượng (`develop/`, `eval/run_eval.py`)

*(Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`)*

| Chỉ số | Agent v1 | Agent v2 (ban đầu) | Agent v2 (sau khi sửa KB) |
|---|---:|---:|---:|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100.0% (23/23)** |
| Avg tokens / câu | 56.8 | 108.8 | 113.7 |
| Tổng cost (USD) | $0.000400 | $0.000758 | $0.000790 |
| Cost / câu đúng (USD) | $0.00040035 | $0.00003607 | **$0.00003436** |
| Quality gate | ❌ FAIL | ✅ PASS (≥ 80%) | **✅ PASS (≥ 100%, 0 regression)** |

**Những câu v2 trả lời sai ban đầu và cách sửa (`06-lab-complete/benchmark-observability/develop/utils/mock_llm.py` và đồng bộ sang `production/utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `["jwt"]` vào `KNOWLEDGE_BASE` giải thích sự khác biệt giữa API key (cố định, không tự hết hạn) và JWT (token có chữ ký số, chứa thông tin user và thời điểm hết hạn). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` giải thích Kubernetes HPA tự động scale pod dựa trên CPU, memory hoặc custom metrics (RPS, độ dài hàng đợi). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- Agent `v2` thêm bước retrieval (~20ms) và chèn ngữ cảnh tài liệu vào prompt, khiến số token trung bình tăng gần gấp đôi (`56.8 → 113.7 tokens/câu`) và tổng chi phí tăng ~2 lần (`$0.000400 → $0.000790`).
- Tuy nhiên, độ chính xác tăng vượt bậc từ `4.3%` lên `100.0%`, nên **chi phí trên mỗi câu trả lời đúng** (`cost_per_correct_usd`) của `v2` (`$0.00003436`) thực tế **rẻ hơn ~11.7 lần** so với `v1` (`$0.00040035`). Đánh đổi thêm ~20–40ms latency và một lượng nhỏ token là hoàn toàn xứng đáng.

**Quality Gate trong CI (Exercise 7.3):**
- Đã tạo workflow GitHub Actions tại `.github/workflows/eval.yml` chạy tự động trên mỗi `pull_request` vào `main`.
- Khi chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 0.85` (có thể kèm `--baseline`), script sẽ thoát với **exit code `1`** nếu `accuracy < 0.85` hoặc có bất kỳ câu nào bị regression (baseline đúng → bản mới sai), làm bước CI fail và tự động chặn merge PR.

**Bài tập Metrics (Exercise 7.1):**
- Đã thêm metric Histogram `agent_question_length_chars` (buckets: `20, 50, 100, 200, 500, 1000, 2000`) trong `develop/app.py` để đo phân bố độ dài câu hỏi mà không làm bùng nổ cardinality.
- 3 loại metric trên `/metrics`: Counter (`http_requests_total`, `llm_tokens_total`, `llm_cost_usd_total`), Gauge (`agent_in_flight_requests`, `agent_info`), Histogram (`http_request_duration_seconds`, `llm_request_duration_seconds`, `agent_question_length_chars`).
- Nếu dùng `request.url.path` thay vì `route.path` làm label, bot quét hàng nghìn URL lạ (`/wp-admin`, `/.env`, `/a1b2c3`...) sẽ tạo ra vô số tổ hợp time series (high cardinality) làm Prometheus cạn RAM và chậm truy vấn.

---

## 4. Observability stack (`production/`) — *Cập nhật ở CP8 khi chạy Docker stack*

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [ ] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [ ] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [ ] Trang Alerts của Prometheus với ≥ 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | *(cập nhật CP8)* | | |
| B | `MOCK_SLOW_RATE=0.3` | *(cập nhật CP8)* | | |
| C | `LLM_MODEL=mock-llm-large` | *(cập nhật CP8)* | | |
| D | `docker pause` 1 instance | *(cập nhật CP8)* | | |
| E | `AGENT_VERSION=v1` | Không có | N/A | Retrieval hit ratio / Tokens/s / Version table |

### 4.3 Debug bằng trace

*(Sẽ điền `trace_id`, span chậm nhất và dòng log JSON thực tế ở CP8)*

---

## 5. Benchmark scaling (`production/`, Locust headless, 100 users, 2 phút)

*(Sẽ điền số liệu thật từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` ở CP8)*

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---:|---:|---:|---:|---:|
| 1 | | | | | |
| 3 | | | | | |

---

## 6. Kết luận

*(Sẽ hoàn thiện tổng kết sau khi hoàn tất CP8)*
