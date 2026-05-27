# Envoy TLS / mTLS Configuration (v1.38.0)

Complete reference for TLS termination, mTLS, SDS secret files, and SPIFFE/URI SAN matching.

## TLS Context Types

| Context @type | Direction | Use |
|---------------|-----------|-----|
| `...tls.v3.DownstreamTlsContext` | Client → Envoy | TLS termination on listeners |
| `...tls.v3.UpstreamTlsContext` | Envoy → Backend | TLS origination on clusters |

Full prefix: `type.googleapis.com/envoy.extensions.transport_sockets.tls.v3`

---

## Downstream TLS Termination

```yaml
static_resources:
  listeners:
  - name: https_listener
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8443
    filter_chains:
    - transport_socket:
        name: envoy.transport_sockets.tls
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
          common_tls_context:
            tls_params:
              tls_minimum_protocol_version: TLS_V1_2
              tls_maximum_protocol_version: TLS_V1_3
              cipher_suites:
              - "ECDHE-ECDSA-AES256-GCM-SHA384"
              - "ECDHE-RSA-AES256-GCM-SHA384"
              - "ECDHE-ECDSA-AES128-GCM-SHA256"
              - "ECDHE-RSA-AES128-GCM-SHA256"
            tls_certificates:
            - certificate_chain:
                sds_config:
                  path: "/etc/envoy/certs/server-cert.yaml"
              private_key:
                sds_config:
                  path: "/etc/envoy/certs/server-key.yaml"
            alpn_protocols:
            - "h2"
            - "http/1.1"
          # Omit require_client_certificate for TLS-only (no mTLS)
      filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: https_ingress
          codec_type: AUTO
          route_config:
            name: local_route
            virtual_hosts:
            - name: web_app
              domains: ["*"]
              routes:
              - match:
                  prefix: /
                route:
                  cluster: web_service
          http_filters:
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

## Downstream mTLS (Mutual TLS)

Add `combined_validation_context` and `require_client_certificate: true`:

```yaml
transport_socket:
  name: envoy.transport_sockets.tls
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
    require_client_certificate: true
    common_tls_context:
      tls_params:
        tls_minimum_protocol_version: TLS_V1_2
      tls_certificates:
      - certificate_chain:
          sds_config:
            path: "/etc/envoy/certs/server-cert.yaml"
        private_key:
          sds_config:
            path: "/etc/envoy/certs/server-key.yaml"
      alpn_protocols: ["h2", "http/1.1"]
      # Validate client cert against CA + require matching SPIFFE URI SAN
      combined_validation_context:
        default_validation_context:
          match_typed_subject_alt_names:
          - san_type: URI
            matcher:
              exact: "spiffe://trust-domain/ns/default/sa/client-service"
        validation_context_sds_secret_config:
          name: ca_cert
          sds_config:
            path: "/etc/envoy/certs/ca-cert.yaml"
```

---

## Upstream TLS (Envoy → Backend)

```yaml
clusters:
- name: secure_backend
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  transport_socket:
    name: envoy.transport_sockets.tls
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
      sni: secure-backend.example.com
      common_tls_context:
        tls_params:
          tls_minimum_protocol_version: TLS_V1_2
        validation_context:
          trusted_ca:
            sds_config:
              path: "/etc/envoy/certs/ca-cert.yaml"
          match_typed_subject_alt_names:
          - san_type: URI
            matcher:
              exact: "spiffe://trust-domain/ns/default/sa/secure-backend"
  load_assignment:
    cluster_name: secure_backend
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: secure-backend.example.com
              port_value: 443
```

## Upstream mTLS (Envoy presents client cert to backend)

```yaml
transport_socket:
  name: envoy.transport_sockets.tls
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
    sni: secure-backend.example.com
    common_tls_context:
      tls_certificates:
      - certificate_chain:
          sds_config:
            path: "/etc/envoy/certs/client-cert.yaml"
        private_key:
          sds_config:
            path: "/etc/envoy/certs/client-key.yaml"
      validation_context:
        trusted_ca:
          sds_config:
            path: "/etc/envoy/certs/ca-cert.yaml"
        match_typed_subject_alt_names:
        - san_type: URI
          matcher:
            exact: "spiffe://trust-domain/ns/default/sa/secure-backend"
```

---

## SPIFFE / URI SAN Matching

`SubjectAltNameMatcher` uses `san_type` (enum) + `matcher` (StringMatcher).

For SPIFFE IDs (which are URI SANs), always use `san_type: URI`:

```yaml
match_typed_subject_alt_names:
- san_type: URI
  matcher:
    exact: "spiffe://trust-domain/ns/production/sa/api-gateway"
```

Other SAN types:

```yaml
# DNS SAN
- san_type: DNS
  matcher:
    suffix: ".example.com"

# Email SAN
- san_type: EMAIL
  matcher:
    exact: "admin@example.com"
```

> ⚠️ `spiffe_id:` is NOT a valid field. Always use `san_type: URI` + `matcher:`.

---

## SDS Secret Watch Files

Envoy watches these files and hot-reloads secrets when they change — no restart needed.

### Server Certificate (`tls_certificate`)

```yaml
# /etc/envoy/certs/server-cert.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: server_cert
  tls_certificate:
    certificate_chain:
      filename: /etc/envoy/certs/server.crt
    private_key:
      filename: /etc/envoy/certs/server.key
```

### CA / Validation Context

```yaml
# /etc/envoy/certs/ca-cert.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: ca_cert
  validation_context:
    trusted_ca:
      filename: /etc/envoy/certs/ca.crt
```

### OAuth2 Secrets (`generic_secret`)

```yaml
# /etc/envoy/secrets/oauth-secrets.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_token
  generic_secret:
    secret:
      filename: /etc/envoy/secrets/oauth-client-secret.txt
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_hmac
  generic_secret:
    secret:
      filename: /etc/envoy/secrets/oauth-hmac-key.txt
```

---

## SDS Secret Rotation Workflow

```bash
# 1. Write new cert files on disk (cert manager, certbot, etc.)
# 2. Update the SDS watch file to point to the new files
cat > /etc/envoy/certs/server-cert.yaml << 'EOF'
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: server_cert
  tls_certificate:
    certificate_chain:
      filename: /etc/envoy/certs/server.crt
    private_key:
      filename: /etc/envoy/certs/server.key
EOF

# 3. Envoy hot-reloads the secret automatically (watches the path).
# 4. Verify:
curl -s http://127.0.0.1:9901/certs | jq '.'
```

---

## Security Parameters Reference

| Parameter | Recommended | Notes |
|-----------|-------------|-------|
| `tls_minimum_protocol_version` | `TLS_V1_2` | Blocks TLS 1.0/1.1 |
| `tls_maximum_protocol_version` | `TLS_V1_3` | Enable TLS 1.3 |
| `cipher_suites` | ECDHE+AES-GCM only | Exclude CBC, RC4, MD5, SHA1 MAC |
| `alpn_protocols` | `["h2", "http/1.1"]` | HTTP/2 with fallback |
| `require_client_certificate` | `true` for mTLS | `false` for TLS-only termination |
| `san_type: URI` | SPIFFE matching | Use with `matcher.exact` for strict identity |

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| Using `spiffe_id:` shorthand | Config rejected — field doesn't exist | Use `san_type: URI` + `matcher: { exact: "spiffe://..." }` |
| Inline certs in static config | Cert rotation requires full restart + secret exposure | Always use SDS `sds_config.path` |
| Missing `sni` on upstream TLS | Server cert validation fails (no SNI hint) | Set `sni` to the backend's expected hostname |
| `require_client_certificate: true` without `combined_validation_context` | Client cert accepted without CA verification | Always pair with a `validation_context` + CA |
| `combined_validation_context` has `default_validation_context.typed_extension_protocol_options` | Rejected — this subfield doesn't exist | Remove it; use only `default_validation_context` (CertificateValidationContext) |
| Duplicate `match_typed_subject_alt_names` keys in one context | Second entry silently ignored | Use a single list under one key |
| Missing `alpn_protocols` | HTTP/2 negotiation fails silently | Add `["h2", "http/1.1"]` |
| Admin API on `0.0.0.0` | Internal config exposed to network | Bind admin to `127.0.0.1` |
| No health check on TLS upstream | TLS failures go undetected until request time | Add `http_health_check` or `tcp_health_check` |
| Cert expiry unmonitored | Silent service failure | Check `curl http://127.0.0.1:9901/certs` in CI/alerting |