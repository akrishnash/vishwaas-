"""
Prometheus metrics definitions.

Imported once at startup. Counters / histograms / gauges are module-level
singletons so they accumulate correctly across requests.
"""
from prometheus_client import Counter, Gauge, Histogram

# ---- HTTP layer ----

http_requests_total = Counter(
    "vishwaas_http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "vishwaas_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# ---- Agent call layer ----

agent_calls_total = Counter(
    "vishwaas_agent_calls_total",
    "Outbound calls from controller to node agents",
    ["operation", "success"],
)

# ---- Business metrics (updated by heartbeat loop) ----

nodes_active = Gauge(
    "vishwaas_nodes_active_total",
    "Number of currently ACTIVE nodes",
)

nodes_offline = Gauge(
    "vishwaas_nodes_offline_total",
    "Number of currently OFFLINE nodes",
)

join_requests_pending = Gauge(
    "vishwaas_join_requests_pending_total",
    "Number of pending join requests awaiting admin approval",
)
