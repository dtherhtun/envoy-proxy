# Envoy Observability (v1.38.0)

Complete reference for metrics, tracing, access logging, and admin API endpoints.

---

## Prometheus Stats

Prometheus metrics are exposed through the admin endpoint — no extra stats_sink needed.

```bash
curl http://127.0.0.1:9901/stats/prometheus
```

To push metrics to an external collector (optional), use `stats_sinks` at the **bootstrap
top level** (not under `admin:`):

```yaml
# Bootstrap top-level field:
stats_sinks:
- name: envoy.stat_sinks.metrics_service
  typed_config:
    "@type": type.googleapis.com/envoy.config.metrics.v3.MetricsServiceConfig
    grpc_service:
      envoy_grpc:
        cluster_name: metrics_collector
    transport_api_version: V3
```

### Key Metrics

**Cluster:**
- `envoy_cluster_upstream_cx_active` — Active connections
- `envoy_cluster_upstream_rq_total` — Total upstream requests
- `envoy_cluster_upstream_rq_time` — Request duration histogram
- `envoy_cluster_upstream_rq_retry` — Retry count
- `envoy_cluster_outlier_detection_ejections_active` — Ejected hosts

**Listener:**
- `envoy_listener_downstream_cx_active` — Active downstream connections
- `envoy_listener_downstream_cx_total` — Total connections

**HTTP:**
- `envoy_http_downstream_rq_total` — Total HTTP requests
- `envoy_http_downstream_rq_time` — Request duration
- `envoy_http_downstream_rq_response_code_2xx/5xx` — Response code counters
- `envoy_http_downstream_cx_ssl_fail` — TLS handshake failures

---

## Zipkin Tracing

Tracing config has two parts:
1. **Provider** — defined at bootstrap level under `tracing.http:`
2. **Sampling rate** — set per-HCM under the `tracing:` block inside HttpConnectionManager

```yaml
# Bootstrap level — tracer provider
tracing:
  http:
    name: envoy.tracers.zipkin
    typed_config:
      "@type": type.googleapis.com/envoy.config.trace.v3.ZipkinConfig
      collector_cluster: zipkin_collector
      collector_endpoint: "/api/v2/spans"
      collector_endpoint_version: HTTP_JSON
      shared_span_context: false
      trace_id_128bit: true
```

```yaml
# Inside HttpConnectionManager — sampling rate and operation name
- name: envoy.filters.network.http_connection_manager
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
    stat_prefix: ingress_http
    generate_request_id: true
    tracing:
      random_sampling:
        value: 10.0    # 10% — range 0.0–100.0
      overall_sampling:
        value: 100.0
      verbose: false
    # ... route_config, http_filters, etc.
```

### Zipkin Cluster

```yaml
- name: zipkin_collector
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: zipkin_collector
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: zipkin.example.com
              port_value: 9411
```

---

## OpenTelemetry Tracing

```yaml
# Bootstrap level — OTel provider
tracing:
  http:
    name: envoy.tracers.opentelemetry
    typed_config:
      "@type": type.googleapis.com/envoy.config.trace.v3.OpenTelemetryConfig
      grpc_service:
        envoy_grpc:
          cluster_name: otel_collector
        timeout: 5s
      service_name: "envoy-proxy"
```

```yaml
# HCM level — sampling
tracing:
  random_sampling:
    value: 10.0
```

### OTel Cluster

```yaml
- name: otel_collector
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  typed_extension_protocol_options:
    envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
      "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
      explicit_http_config:
        http2_protocol_options: {}
  load_assignment:
    cluster_name: otel_collector
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: otel-collector.example.com
              port_value: 4317   # gRPC port
```

---

## Access Logging

### JSON Access Log (Production Standard)

```yaml
# Inside HttpConnectionManager:
access_log:
- name: envoy.access_loggers.file
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
    path: /dev/stdout
    log_format:
      typed_json_format:
        timestamp:            "%START_TIME(%Y-%m-%dT%H:%M:%S.%3fZ)%"
        method:               "%REQ(:METHOD)%"
        path:                 "%REQ(:PATH)%"
        protocol:             "%PROTOCOL%"
        response_code:        "%RESPONSE_CODE%"
        response_flags:       "%RESPONSE_FLAGS%"
        duration_ms:          "%DURATION%"
        upstream_cluster:     "%UPSTREAM_CLUSTER%"
        upstream_address:     "%UPSTREAM_ADDRESS%"
        upstream_svc_time:    "%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME,-)%"
        downstream_client_ip: "%DOWNSTREAM_REMOTE_ADDRESS_WITHOUT_PORT%"
        bytes_received:       "%BYTES_RECEIVED%"
        bytes_sent:           "%BYTES_SENT%"
        request_id:           "%REQ(X-REQUEST-ID,-)%"
        user_agent:           "%REQ(USER-AGENT,-)%"
        x_forwarded_for:      "%REQ(X-FORWARDED-FOR,-)%"
        tls_version:          "%DOWNSTREAM_TLS_VERSION%"
        upstream_failure:     "%UPSTREAM_TRANSPORT_FAILURE_REASON%"
```

### Common Command Operators

| Operator | Description |
|----------|-------------|
| `%START_TIME%` | Request start time (customizable format) |
| `%REQ(:METHOD)%` | HTTP method |
| `%REQ(:PATH)%` | Request path |
| `%PROTOCOL%` | Protocol (HTTP/1.1, HTTP/2, HTTP/3) |
| `%RESPONSE_CODE%` | HTTP response status code |
| `%RESPONSE_FLAGS%` | Envoy response flags (see table below) |
| `%DURATION%` | Total request duration in milliseconds |
| `%UPSTREAM_CLUSTER%` | Name of the upstream cluster used |
| `%UPSTREAM_ADDRESS%` | Upstream host:port |
| `%UPSTREAM_TRANSPORT_FAILURE_REASON%` | TLS/transport failure reason |
| `%DOWNSTREAM_REMOTE_ADDRESS_WITHOUT_PORT%` | Client IP |
| `%DOWNSTREAM_TLS_VERSION%` | TLS version on downstream connection |
| `%DOWNSTREAM_PEER_SUBJECT%` | Client cert subject (mTLS) |
| `%BYTES_RECEIVED%` / `%BYTES_SENT%` | Transfer sizes |
| `%REQ(X-REQUEST-ID,-)%` | Header value with default `-` |
| `%RESP(X-ENVOY-UPSTREAM-SERVICE-TIME,-)%` | Response header value |

### Response Flags

| Flag | Meaning |
|------|---------|
| `NR` | No route found |
| `UC` | Upstream connection failure |
| `UT` | Upstream request timeout |
| `UO` | Upstream overflow (circuit breaker) |
| `UF` | Upstream connection failure (framing) |
| `DC` | Downstream connection termination |
| `LR` | Local reset |
| `RL` | Rate limited |
| `UAEX` | Unauthorized by ext_authz |
| `RLSE` | Rate limit service error |

---

## Admin API Endpoints

### Read-Only (GET)

| Endpoint | Description |
|----------|-------------|
| `/server_info` | Version, state, uptime, PID |
| `/clusters` | Cluster health, LB stats, outlier status |
| `/listeners` | Listener addresses and filter chain summary |
| `/config_dump` | Full config snapshot (all subsystems) |
| `/config_dump?mask=listeners` | Only listener configs |
| `/config_dump?mask=clusters` | Only cluster configs |
| `/config_dump?mask=secrets` | Only SDS secret metadata |
| `/config_dump?mask=route_configs` | Only route configs |
| `/stats` | All stats in text format |
| `/stats?format=prometheus` | Prometheus exposition format |
| `/stats?filter=upstream_cx` | Filtered stats by name substring |
| `/certs` | TLS certificate details and expiry |
| `/runtime` | Current runtime feature flags |
| `/memory` | Memory usage summary |
| `/ready` | Readiness probe (200 = ready) |
| `/hot_restart_version` | Hot restart protocol version |

### Write (POST)

| Endpoint | Description |
|----------|-------------|
| `/quitquitquit` | Graceful shutdown |
| `/drain_listeners?inboundonly` | Drain inbound listeners |
| `/healthcheck/fail` | Mark this Envoy unhealthy |
| `/healthcheck/ok` | Mark this Envoy healthy again |
| `/reset_counters` | Reset all stats counters |
| `/logging?level=debug` | Change log level at runtime |

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| `stats_sinks` nested under `admin:` | Field silently ignored | Move `stats_sinks` to bootstrap top level |
| `random_sampling` inside tracer provider config | Rejected — wrong proto | Set `random_sampling` on HCM `tracing:` block, not in ZipkinConfig/OTelConfig |
| OTel cluster without HTTP/2 | gRPC transport fails | Add `typed_extension_protocol_options` with `http2_protocol_options: {}` |
| `typed_filter_config` on route | Field ignored | Correct key is `typed_per_filter_config` |
| Access log missing `%RESPONSE_FLAGS%` | Cannot distinguish error types | Always include `response_flags` |
| Using `format` (string) instead of `typed_json_format` | Unstructured logs, hard to parse | Use `typed_json_format` map for structured JSON |
| Admin on `0.0.0.0` | Config, stats, secrets exposed | Bind admin to `127.0.0.1` |
| Zipkin endpoint path wrong | No traces collected | Use `/api/v2/spans` for Zipkin v2 API |
| Tracing `random_sampling: 0.0` | Zero traces collected | Set a non-zero value (e.g., `10.0` for 10%) |