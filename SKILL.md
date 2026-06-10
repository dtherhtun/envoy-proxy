---
name: envoy-proxy
description: >
  Envoy proxy v1.38.0 — configuration validation, production-readiness auditing, xDS
  semantics, filter/trap catalog, and troubleshooting. Covers static/dynamic config,
  listeners, HCM, clusters, TLS/mTLS/SDS, admin, observability, WASM, and the full
  filter inventory. Token-efficient references, not doc dumps.
tags:
  - envoy
  - proxy
  - xds
  - config-validation
  - networking
  - infrastructure
version: v1.38.0
---

# Envoy Proxy v1.38.0

Use for Envoy config validation, audits, filter lookups, xDS semantics, and troubleshooting.

## Mental Model

```
Bootstrap (node, admin, static_resources)
  ├── listeners          inbound entry points
  │   ├── filter_chains  per-address filter sets
  │   │   └── filters    network filters (TCP layer)
  │   │       └── typed_config → HCM
  │   │           ├── stat_prefix
  │   │           ├── route_config / rds
  │   │           └── http_filters  (HTTP layer)
  │   └── listener_filters   (pre-filter-chain inspection)
  └── clusters           upstream backends
      ├── load_assignment
      ├── health_checks
      ├── circuit_breakers
      ├── outlier_detection
      └── transport_socket (TLS/mTLS/SDS)
```

**Critical invariant:** HCM `http_filters` must end with `router`. Break this and no route resolves.

## Workflow

### 1. Structural validation

Check required top-level keys, `typed_config` (not `typeConfig`), HCM presence, cluster references.

### 2. Security audit

Admin exposure, TLS protocol versions, SNI, upstream cert validation, access logging.

### 3. Resilience audit

connect_timeout, health_checks, circuit_breakers, outlier_detection, retry policy.

See `references/validation-checks.md`, `references/audit-checks.md`, `references/audit-patterns.md`.

## Critical Pitfalls (hard-won)

| # | Pitfall | Symptom |
|---|---------|---------|
| 1 | `typeConfig` instead of `typed_config` | Config silently ignored in v1.31+ |
| 2 | Missing `@type` URL in `typed_config` | Config rejected |
| 3 | `router` not last in `http_filters` | Routes unreachable, 404s |
| 4 | Missing `stat_prefix` on HCM | Metrics namespace collision |
| 5 | No `connect_timeout` on cluster | Defaults to 15s, cascading hangs |
| 6 | Admin on `0.0.0.0` without `allow_paths` | Control plane exposed |
| 7 | Cluster referenced in route not defined | Routes silently dropped |
| 8 | Plain listener without transport_socket | Unencrypted traffic |
| 9 | `ext_authz` followed by filter not calling `clearRouteCache()` | Auth bypass vector |
| 10 | JSON access log using `format` vs `typed_json_format` | Hard to parse at scale |

## Field Name Reference

Use these exact proto3 field names:

```
typed_config              (not typeConfig)
@type                     (type.googleapis.com/envoy.*)
stat_prefix
connect_timeout           (DsJson format: "5s")
cluster_name
socket_address            {address, port_value}
filter_chains
http_filters              (network_filters = TCP layer)
http_connection_manager   (use @type URL not named filter)
virtual_hosts             (inside route_config)
domains
routes
match
route_action
cluster
header_mutation
response_headers_to_add
request_headers_to_add
tls_context               (network-level)
transport_socket          {name: "tls", typed_config}
common_tls_context        (inside tls_context)
tls_certificates          {certificate_chain, private_key}
validation_context        (upstream/ca certs)
verify_subject_alt_name
match_subject_alt_names
allow_paths / deny_paths  (admin)
```

## xDS Quick Reference

| Resource | Type URL | Service |
|----------|----------|---------|
| Listener | `type.googleapis.com/envoy.config.listener.v3.Listener` | LDS |
| RouteConfiguration | `type.googleapis.com/envoy.config.route.v3.RouteConfiguration` | RDS |
| Cluster | `type.googleapis.com/envoy.config.cluster.v3.Cluster` | CDS |
| ClusterLoadAssignment | `type.googleapis.com/envoy.config.endpoint.v3.ClusterLoadAssignment` | EDS |
| Secret | `type.googleapis.com/extensions.transport_sockets.tls.v3.Secret` | SDS |
| Runtime | `type.googleapis.com/envoy.service.runtime.v3.Runtime` | RTDS |

**Protocols:** SotW (basic xDS), incremental xDS, ADS (aggregated), incremental ADS.
**Bootstrap order:** xDS clusters must appear in `static_resources.clusters` BEFORE clusters that depend on them.
**File subscriptions:** Use `inotify`/`kqueue`; no ACK/NACK — last valid config persists, errors go to stats/logs.

## Admin Interface

Defaults: `127.0.0.1:9901`. **Never bind to `0.0.0.0`.**

Key endpoints:
- `GET /ready` — readiness probe (200/503)
- `GET /server_info` — version, state, uptime
- `GET /clusters` — upstream health
- `GET /config_dump` — live config
- `GET /stats` — metrics
- `POST /stats` — filter regex
- `POST /logging` — change log levels

All mutations require POST; GET returns 400.

## Observability

**Stats:** key metrics at `http.manager.*`, `cluster.*`, `listener.*`, `server.*`.
**Access log:** JSON via `typed_json_format`, TEXT via `string_format`. Always add a filter.
**Tracing:** Zipkin, OTel, Datadog — configured on HCM `tracing`.

## Security Priority Order

1. **CRITICAL** — Admin exposed, TLSv1.0, no listener TLS
2. **HIGH** — No connect_timeout, no health_checks, no circuit_breakers, no access_logs
3. **MEDIUM** — No TLS resumption, no SNI, no upstream cert validation
4. **LOW** — LB strategy, outlier thresholds
