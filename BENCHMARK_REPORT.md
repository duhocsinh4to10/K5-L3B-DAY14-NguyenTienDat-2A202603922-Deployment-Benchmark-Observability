# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được đo trực tiếp từ `load_test.py`, `eval/run_eval.py` và đối chiếu 100% với các file JSON trong thư mục `reports/` và CSV trong `benchmark-results/`.

**Họ tên:** Nguyễn Tiến Đạt (`2A202603922`) — Lớp `L3B`  
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

## 4. Observability stack (`production/`)

### 4.1 Screenshot & Câu hỏi Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ 4 Golden Signals, bước scale 1 → 3 instance): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (1.7s, thấy span `chat mock-llm-small` chiếm 98.4%): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (`HTTP 503`, `error=true` ở span LLM): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với **3 alert cùng đang `firing`** (`AgentHighErrorRate`, `AgentHighLatencyP95`, `AgentInstanceDown`) + `LLMCostBurnRateHigh` đang `pending`: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (số liệu đo từ Prometheus/Grafana khi chạy tải):**
1. **p95 và avg là bao nhiêu? Khoảng cách nói lên điều gì?**
   - Tại cửa sổ đo trên Grafana/Prometheus: `avg ≈ 233.3 ms`, `p95 ≈ 294.4 ms` (`298.65 ms` trên stat panel), trong khi `p99 ≈ 1.7s–1.8s` (biểu đồ Latency `/ask`). Khoảng cách lớn giữa `avg`/`p50` (~200ms) và `p99` (~1.7s) phản ánh rõ hiện tượng **tail latency** (~3% request bị chậm bất thường ở tầng LLM).
2. **Panel "Requests/s theo instance": Nginx có chia đều traffic cho các instance không?**
   - Có. Khi scale lên 3 instance (`172.19.0.4:8000`, `172.19.0.8:8000`, `172.19.0.9:8000`), lượng request được Nginx phân bổ gần như bằng nhau tuyệt đối: lần lượt `7.79`, `7.89`, và `7.87 req/s` (~33.3% mỗi instance, trên biểu đồ 3 đường trùng khít nhau ở ~20 req/s khi chạy tải cao điểm).
3. **Vì sao input tokens/s lớn hơn output tokens/s?**
   - Đo thực tế: `input ≈ 1802.6 tokens/s` so với `output ≈ 939.3 tokens/s` (gần gấp đôi). Nguyên nhân là Agent `v2` (RAG) ghép thêm `SYSTEM_PROMPT` + đoạn ngữ cảnh tài liệu retrieve được từ `KNOWLEDGE_BASE` + câu hỏi của người dùng làm prompt đầu vào, nên lượng input tokens luôn dài hơn câu trả lời output.
4. **`curl -i http://localhost:8080/metrics` trả về gì? Vì sao?**
   - Trả về **`HTTP/1.1 404 Not Found`** từ Nginx (`nginx/nginx.conf` chủ động chặn route `/metrics` ra ngoài Internet). Trong production, `/metrics` chỉ mở trong mạng nội bộ (`obs_net`) cho Prometheus scrape, tránh làm lộ thông tin hạ tầng, lưu lượng và chi phí ra bên ngoài.

### 4.2 Thí nghiệm "phá hệ thống" & Alert rules

Đã chạy unit test alert rules: `promtool test rules /p/alert_rules_test.yml` → **`SUCCESS`**.

Thực hiện fault injection trên stack 3 instance với tải Locust 30 users (`MOCK_ERROR_RATE=0.25`, `MOCK_SLOW_RATE=0.3`, `LLM_MODEL=mock-llm-large`, kết hợp `docker pause k5-day14-observability-agent-1`):

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.25` (> 5%, `for: 1m`) | **`AgentHighErrorRate`** (`critical`) | **75.6 giây** | Golden Signals → **Error rate** (chuyển đỏ), **Requests/s theo status code** (`503` tăng vọt) |
| B | `MOCK_SLOW_RATE=0.3` (p95 > 1s, `for: 2m`) | **`AgentHighLatencyP95`** (`warning`) | **135.8 giây** | Golden Signals → **Latency p95** (> 1s), biểu đồ **Latency /ask — p50/p95/p99** |
| C | `LLM_MODEL=mock-llm-large` (> $2/h, `for: 2m`) | **`LLMCostBurnRateHigh`** (`pending` → `firing` sau 2m) | Chuyển `pending` ở giây ~50 (sẽ `firing` sau `for: 2m`) | **Cost burn rate (USD/giờ)** vượt đường đỏ `$2/h`, **LLM cost (1h)** |
| D | `docker pause k5-day14-observability-agent-1` (`up == 0`, `for: 30s`) | **`AgentInstanceDown`** (`critical`) | **45.5 giây** | **Instances up** giảm từ 3 xuống 2; lỗi 504 ở tầng Nginx không hiện trong metric error của agent |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | N/A | **Retrieval hit ratio (agent v2)** giảm về 0%, **Tokens/s** giảm một nửa, bảng version đổi sang `v1` |

**Thí nghiệm E không làm alert nào firing (và giải thích hiện tượng lỗi 504 ở thí nghiệm D):**
- **Tại sao đổi sang `AGENT_VERSION=v1` không có alert hạ tầng nào báo động?** Các alert hiện tại giám sát *sức khỏe hạ tầng* (error rate 5xx, latency p95, instance up, cost). Bản `v1` thậm chí chạy nhanh hơn, rẻ hơn và vẫn trả HTTP `200 OK`, nhưng câu trả lời sai gần hết (`accuracy` tụt từ 100% xuống 4.3%). Trong production, để phát hiện suy giảm chất lượng cần: (1) chạy **eval quality gate** trên golden dataset trong CI/CD trước khi deploy (như `.github/workflows/eval.yml`), (2) theo dõi metric nghiệp vụ/RAG như `retrieval_hit_ratio` (đặt alert khi tụt ngưỡng), (3) đánh giá mẫu traffic thật bằng **LLM-as-a-Judge** và thu thập phản hồi thumbs-up/down từ người dùng.
- **Tại sao ở thí nghiệm D lỗi 504 không hiện trên panel Error rate của agent?** Khi một container bị `pause`, Nginx chờ quá `proxy_read_timeout` rồi tự trả `504 Gateway Timeout` cho client; request chưa bao giờ được agent xử lý xong nên counter `http_requests_total` bên trong agent không đếm nó. Do đó production cần thêm giám sát ở tầng Load Balancer/Nginx và synthetic monitoring từ bên ngoài.

### 4.3 Debug bằng trace

**Trace chậm nhất đã chọn (`jaeger-slow-trace.png`):**
- **`trace_id`:** `165e566334fff7d7e9e52972332b94ba`
- **Tổng thời gian (`POST /ask`):** `1725.9 ms`
- **Phân rã các span:**
  - `POST /ask`: `1725.9 ms` (100.0%)
  - `agent.run`: `1721.4 ms` (99.7%)
  - `agent.retrieve_context`: `22.2 ms` (1.3%)
  - **Span chiếm nhiều thời gian nhất:** `chat mock-llm-small` — **`1698.9 ms` (`98.4%`)** → chứng minh nút thắt nằm ở lời gọi LLM upstream, không phải bước retrieval hay code FastAPI.
- **Dòng log JSON tương ứng (grep từ `docker compose -p k5-day14-observability logs agent` theo đúng `trace_id`):**

```json
{"ts": "2026-11-26T10:07:19.804176+00:00", "level": "INFO", "service": "observable-agent", "instance": "d3a158c25a2d", "event": "llm_call", "trace_id": "165e566334fff7d7e9e52972332b94ba", "span_id": "187ae49ab8fb4720", "request_id": "5d005a7b0aa2", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.9}
```

**Trace lỗi đã đối chiếu (`jaeger-error-trace.png`):**
- **`trace_id`:** `41412a783b8e0a2e77ca1221602b770a` (HTTP `503`, tổng thời gian `90.7 ms`, span `chat mock-llm-small` ghi nhận `error=true` ở `70.3 ms`)
- **Dòng log JSON tương ứng:**

```json
{"ts": "2026-11-26T10:08:56.775258+00:00", "level": "INFO", "service": "observable-agent", "instance": "d8355c57653c", "event": "llm_error", "trace_id": "41412a783b8e0a2e77ca1221602b770a", "span_id": "ce31d1e97dc8a258", "request_id": "cff6ec9efae3", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (`production/`, Locust headless, 100 users, 2 phút)

*(Nguồn dữ liệu khớp 100% với `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`)*

**Kết quả cho endpoint chính `POST /ask`:**

| Số instance | Total Reqs | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 6988 | 58.66 | 200 | 540 | 1700 | 61 (0.87%) |
| 3 | 7156 | 60.11 | 200 | 250 | 1700 | 69 (0.96%) |

**Kết quả tổng hợp (`Aggregated`: `POST /ask` + `GET /health`):**

| Số instance | Total Reqs | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 7691 | 64.56 | 200 | 500 | 1700 | 61 (0.79%) |
| 3 | 7846 | 65.90 | 190 | 240 | 1700 | 69 (0.88%) |

**Giải thích kết quả:**
- **p95 cải thiện rõ rệt (giảm hơn một nửa: `540 ms → 250 ms` ở `/ask`, và `/health` p95 giảm từ `110 ms → 16 ms`)**: ở cấu hình 1 container bị giới hạn `0.5 CPU`, khi có 100 user đồng thời tạo tải thì event loop và hàng đợi CPU bắt đầu nghẽn nhẹ ở nhóm 5% request cao nhất. Khi scale lên 3 instance, tải được Nginx chia đều (mỗi container chỉ gánh ~1/3 lưu lượng), loại bỏ hoàn toàn hàng đợi CPU ở tầng ứng dụng.
- **Tuy nhiên `p50` (`200 ms`), `p99` (`1700 ms`) và `RPS` (`58.66 → 60.11 req/s`) gần như không đổi nhiều:** vì nút thắt chính của AI Agent nằm ở **độ trễ I/O của LLM upstream** (~150–200ms cho request thường và ~1700ms cho 3% tail latency) cùng `wait_time` của 100 Locust users. Scale ngang thêm instance giải quyết được nút thắt CPU/bộ nhớ cục bộ nhưng không thể tự làm LLM provider trả lời nhanh hơn — muốn giảm `p99` phải tối ưu ở tầng gọi LLM (streaming, timeout + retry có hedge, semantic caching, hoặc chọn model nhỏ/nhanh hơn).

---

## 6. Kết luận

- **3 điều quan trọng nhất học được về benchmark & observability:**
  1. **Không bao giờ đặt SLO theo latency trung bình (average):** Average che giấu tail latency (`p95`/`p99`). Chỉ cần 3–10% request chậm ~1.7s, trải nghiệm người dùng đã tệ đi rất rõ trong khi `avg` chỉ nhích nhẹ.
  2. **Observability hạ tầng xanh không có nghĩa là AI Agent đang trả lời đúng:** Cần kết hợp cả 3 lớp — giám sát hạ tầng (Metrics/Traces/Logs), benchmark hiệu năng (load test + SLO) và benchmark chất lượng định kỳ trên golden dataset (eval + CI quality gate) dùng chỉ số `cost / câu đúng` để đánh giá trade-off.
  3. **Liên kết 3 trụ cột Metrics → Traces → Logs bằng `trace_id` giúp tìm root cause trong vài giây:** Dashboard báo p95/error tăng → mở Jaeger xem flamegraph xác định span `chat mock-llm-small` chiếm 98.4% → grep `trace_id` trong JSON logs để lấy đầy đủ ngữ cảnh sự cố.
- **Nếu đưa agent này lên production thật, cần bổ sung thêm các metric / alert sau:**
  - **TTFT (Time To First Token)** và **Tokens per second** cho streaming response.
  - **Alert cho `retrieval_hit_ratio` thấp** (ví dụ `< 70%` trong 5 phút) để phát hiện sớm lỗi RAG/vector DB hoặc suy giảm chất lượng như thí nghiệm E.
  - **Nginx/Ingress 5xx & 504 rate alert** + **synthetic probe từ bên ngoài** để bắt các lỗi timeout ở tầng Load Balancer mà metric nội bộ của agent không nhìn thấy.
  - **Alertmanager** định tuyến cảnh báo theo mức độ (`critical` → PagerDuty/Slack on-call, `warning` → kênh Slack team) kèm **trace tail-based sampling** (giữ 100% trace lỗi/chậm, sample 5–10% trace thường) để tối ưu chi phí lưu trữ khi traffic lớn.
