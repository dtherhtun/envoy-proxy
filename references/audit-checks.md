# Audit Checks

Severity: PASS / FAIL. FAIL = must-fix before production.

## Security

### SEC-001: Admin Interface Exposure (CRITICAL)

- `admin.address.socket_address.address` == `127.0.0.1` or `::1`
- Fail if `0.0.0.0`, `::`, or unset/external IP
- `allow_paths` configured if admin on external interface

### SEC-002: TLS Protocol Version (CRITICAL)

- `tls_minimum_protocol_version` == TLSv1_2 or TLSv1_3
- Fail if TLSv1_0, TLSv1_1, or absent

### SEC-003: Listener Transport Socket (CRITICAL)

- Every external-facing listener has `transport_socket` configured
- Transparent/Observability-only listeners may be exempt (document why)

### SEC-004: TLS Cipher Suites (MEDIUM)

- No RC4, DES, 3DES, MD5 in `tls_params.cipher_suites`
- Prefer: `ECDHE-ECDSA-AES256-GCM-SHA384`, `ECDHE-RSA-AES256-GCM-SHA384`

### SEC-005: Upstream Cert Validation (MEDIUM)

- mTLS upstreams: `validation_context` with CA certs, not `allow_untrusted_certificate: true`
- Fail if `allow_untrusted_certificate: true` without explicit justification

### SEC-006: SNI Enforcement (MEDIUM)

- Downstream TLS: `server_name` present in SNI context or set from transport socket

## Resilience

### RES-001: Cluster Connect Timeout (HIGH)

- `connect_timeout` set, not defaulting to 15s
- Recommended: 1-5s for internal, 5-10s for external

### RES-002: Health Checks (HIGH)

- Every non-EDS cluster has `health_checks` configured
- Timeout + interval + unhealthy_threshold + healthy_threshold all present

### RES-003: Circuit Breakers (HIGH)

- `circuit_breakers.thresholds` present with at least `max_connections` and `max_retries`

### RES-004: Outlier Detection (LOW-MEDIUM)

- Recommended for non-trivial upstreams (>=3 endpoints)
- `consecutive_errors` (5), `interval` (2s), `base_ejection_time` (30s)

### RES-005: Retry Policy (MEDIUM)

- HCM `retry_policy` configured for 5xx, connect-failure, refused-stream

### RES-006: Connection Pool Limits (MEDIUM)

- `max_connections_per_host`, `max_retries` non-zero for production

## Operations

### OPS-001: Access Logging (HIGH)

- HCM `access_log` configured with at least one sink
- JSON format preferred: `typed_json_format`

### OPS-002: Runtime Config (LOW)

- `runtime` layer configured for percentage-based rollout

### OPS-003: Graceful Draining (MEDIUM)

- `drain_listeners` interval set (not default)
