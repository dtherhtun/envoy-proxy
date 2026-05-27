# Envoy Cluster Patterns (v1.38.0)

Complete reference for upstream cluster types, load balancing, health checks, circuit breakers, and outlier detection.

## Cluster Types

| Type | Resolution | Use Case |
|------|-----------|----------|
| `STATIC` | Config-time | Fixed IPs, local sidecars |
| `STRICT_DNS` | Per-new-connection | Hostname-based upstreams (most common) |
| `LOGICAL_DNS` | Per-LB-decision | Small pools where one resolved IP is used |
| `EDS` | xDS push/pull | Kubernetes, service mesh, dynamic pools |
| `ORIGINAL_DST` | OS connection metadata | Transparent proxy / passthrough |

### STATIC Cluster

```yaml
- name: static_backend
  type: STATIC
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: static_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: 10.0.0.1
              port_value: 8080
      - endpoint:
          address:
            socket_address:
              address: 10.0.0.2
              port_value: 8080
```

### STRICT_DNS Cluster

```yaml
- name: dns_backend
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  dns_refresh_rate: 30s
  load_assignment:
    cluster_name: dns_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: backend.example.com
              port_value: 443
```

### EDS Cluster

```yaml
- name: eds_backend
  type: EDS
  connect_timeout: 5s
  eds_cluster_config:
    eds_config:
      api_config_source:
        api_type: DELTA_GRPC
        grpc_services:
        - envoy_grpc:
            cluster_name: xds_cluster
        transport_api_version: V3
```

---

## Load Balancing Policies

| Policy | Description | Best For |
|--------|-------------|----------|
| `ROUND_ROBIN` | Cycles through healthy hosts | Default, uniform workloads |
| `LEAST_REQUEST` | Host with fewest active requests | Variable-latency services |
| `RANDOM` | Random host selection | Simple distribution |
| `RING_HASH` | Consistent hashing | Sticky sessions, cache affinity |
| `MAGLEV` | Maglev consistent hashing | Better distribution than RING_HASH |
| `WEIGHTED_ROUND_ROBIN` | Weighted cyclic | Canary, zone-aware routing |

### LEAST_REQUEST

```yaml
lb_policy: LEAST_REQUEST
least_request_lb_config:
  choice_count: 2           # Sample 2 hosts, pick the one with fewer requests
  active_request_bias:
    default_value: 1.0
    runtime_key: lb.least_request.active_request_bias
```

### RING_HASH

Hash policy lives in the **route config**, NOT in the cluster.

```yaml
# Cluster side — only ring sizing goes here:
lb_policy: RING_HASH
ring_hash_lb_config:
  minimum_ring_size: 1024
  hash_function: XX_HASH    # XX_HASH (default) or MURMUR_HASH_2

# Route side — hash_policy is required here:
route:
  cluster: my_cluster
  hash_policy:
  - header:
      header_name: x-user-id
  - connection_properties:
      source_ip: true       # fallback to IP if header missing
```

### MAGLEV

```yaml
lb_policy: MAGLEV
maglev_lb_config:
  table_size: 65536   # Must be a prime number; default 65537
```

---

## Health Check Configuration

Only one health check type per entry: `http_health_check`, `tcp_health_check`, or `grpc_health_check`.

### HTTP Health Check

```yaml
health_checks:
- timeout: 5s
  interval: 10s
  interval_jitter: 1s
  unhealthy_threshold: 3
  healthy_threshold: 2
  http_health_check:
    path: /healthz
    expected_statuses:
    - status_range:
        start: 200
        end: 299
    request_headers_to_add:
    - header:
        key: X-Envoy-Healthcheck
        value: "true"
```

### TCP Health Check

```yaml
health_checks:
- timeout: 3s
  interval: 10s
  unhealthy_threshold: 2
  healthy_threshold: 1
  tcp_health_check:
    send:
      text: "PING"    # hex or text payload; empty = just connect check
    receive:
    - text: "PONG"
```

### gRPC Health Check

```yaml
health_checks:
- timeout: 5s
  interval: 10s
  unhealthy_threshold: 3
  healthy_threshold: 2
  grpc_health_check:
    service_name: "my.service.Health"  # maps to grpc.health.v1.Health/Check
```

### Multi Health Check (HTTP + TCP as separate entries)

```yaml
health_checks:
- timeout: 5s
  interval: 10s
  unhealthy_threshold: 3
  healthy_threshold: 2
  http_health_check:
    path: /healthz
- timeout: 3s
  interval: 15s
  unhealthy_threshold: 2
  healthy_threshold: 1
  tcp_health_check: {}    # connection-only check
```

---

## Outlier Detection

```yaml
outlier_detection:
  consecutive_5xx: 5                   # Consecutive 5xx responses to eject
  consecutive_gateway_failure: 3       # Consecutive 502/503/504 to eject
  consecutive_local_origin_failure: 5  # Connection-level failures (reset, timeout)
  interval: 15s                        # Ejection sweep interval
  base_ejection_time: 30s              # Minimum ejection duration
  max_ejection_percent: 50             # Never eject more than this % of hosts
  min_health_percent: 10               # Don't eject if healthy pool drops below 10%
  success_rate_minimum_hosts: 5        # Min hosts needed for success-rate ejection
  success_rate_request_volume: 100     # Min requests per host for success-rate check
  success_rate_stdev_factor: 1900      # Stdev multiplier (1900 = 1.9 sigma)
```

---

## Circuit Breaker

`circuit_breakers` is a **direct cluster-level field** — not nested under any other block.

```yaml
- name: my_cluster
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  circuit_breakers:
    thresholds:
    - priority: DEFAULT
      max_connections: 1024
      max_pending_requests: 1024
      max_requests: 1024
      max_retries: 3
    - priority: HIGH
      max_connections: 2048
      max_pending_requests: 2048
      max_requests: 2048
      max_retries: 3
  load_assignment:
    cluster_name: my_cluster
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: backend.example.com
              port_value: 8080
```

---

## HTTP/2 Upstream

```yaml
- name: h2_backend
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  typed_extension_protocol_options:
    envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
      "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
      explicit_http_config:
        http2_protocol_options: {}
  load_assignment:
    cluster_name: h2_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: backend.example.com
              port_value: 443
```

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| `circuit_breakers` nested under `common_lb_config` | Field ignored, no protection | `circuit_breakers` is a direct cluster field |
| Missing `typed_extension_protocol_options` on H2 upstream | HTTP/2 connections fail silently | Add `HttpProtocolOptions` with `http2_protocol_options: {}` |
| `hash_policy` in cluster instead of route config | Config rejected or ignored | Hash policy belongs in `route.hash_policy`, not in `ring_hash_lb_config` |
| `hash_function: MURMER_HASH` (typo) | Config rejected | Valid values: `XX_HASH` (default) or `MURMUR_HASH_2` |
| `outlier_detection` with `min_health_percent: 0` | All hosts ejected, total 503s | Set `min_health_percent: 10` |
| Health check `timeout` ≥ `interval` | Checks overlap, false positives | Keep `timeout < interval` |
| Missing `interval_jitter` | All hosts probed simultaneously | Add `interval_jitter: 1s` |
| Using `http2_health_check` type | Not a valid type | Use `http_health_check` with an H2 cluster |
| `max_ejection_percent` not set | Single bad host can eject entire cluster | Set `max_ejection_percent: 50` |
| Static cluster missing `load_assignment` | No endpoints, 503 on all requests | Always include `load_assignment` with at least one endpoint |
| EDS cluster missing `eds_cluster_config` | No endpoint updates received | Configure `eds_cluster_config.eds_config` |