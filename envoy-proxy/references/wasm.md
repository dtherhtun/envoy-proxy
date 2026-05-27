# Envoy WASM Plugin Configuration (v1.38.0)

Complete reference for WASM filters, runtimes, source types, and the OIDC-via-WASM pattern.

**@type:** `type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm`

---

## Runtimes

| Runtime value | Engine | Best For |
|---------------|--------|----------|
| `envoy.wasm.runtime.v8` | V8 (default) | C++, Rust, AssemblyScript plugins |
| `envoy.wasm.runtime.wasmtime` | Cranelift JIT | Performance-sensitive plugins |
| `envoy.wasm.runtime.wamr` | Micro Runtime | Low-memory / embedded environments |
| `envoy.wasm.runtime.null` | No-op (native) | Testing filter chain behavior only |

---

## Source Types

| Field | Use Case | Notes |
|-------|----------|-------|
| `local: { filename: }` | Development, pre-baked images | Verify integrity externally |
| `remote: { http_uri:, sha256: }` | CI/CD, centralized plugin registry | SHA-256 **required** for security |
| `inline_bytes:` | Tiny plugins embedded in config | Base64-encoded; limit ~64 KB |

---

## Local File Plugin

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "local-plugin"
      root_id: "local_root"
      configuration:
        "@type": type.googleapis.com/google.protobuf.StringValue
        value: |
          {
            "debug": true,
            "log_level": "info"
          }
      vm_config:
        vm_id: "local_vm"
        runtime: envoy.wasm.runtime.v8
        code:
          local:
            filename: "/etc/envoy/plugins/example.wasm"
```

## Remote Plugin (Production)

SHA-256 is mandatory. Obtain it with `sha256sum example.wasm`.

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "remote-plugin"
      root_id: "remote_root"
      configuration:
        "@type": type.googleapis.com/google.protobuf.StringValue
        value: |
          {
            "key1": "value1",
            "key2": "value2"
          }
      vm_config:
        vm_id: "remote_vm"
        runtime: envoy.wasm.runtime.v8
        code:
          remote:
            http_uri:
              uri: "https://plugins.example.com/example.wasm"
              cluster: wasm_plugin_registry
              timeout: 30s
            sha256: "a948904f2f0f479b8f936dg..."  # sha256sum of .wasm binary
            retry_policy:
              retry_back_off:
                base_interval: 1s
                max_interval: 10s
              num_retries: 3
```

The cluster referenced in `http_uri.cluster` must be defined in `static_resources.clusters`:

```yaml
- name: wasm_plugin_registry
  type: STRICT_DNS
  connect_timeout: 10s
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: wasm_plugin_registry
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: plugins.example.com
              port_value: 443
  transport_socket:
    name: envoy.transport_sockets.tls
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext
      sni: plugins.example.com
```

## Inline Plugin (Small Only)

```yaml
vm_config:
  vm_id: "inline_vm"
  runtime: envoy.wasm.runtime.v8
  code:
    inline_bytes: "<base64-encoded-wasm-binary>"
```

---

## VM Sharing with `vm_id`

When two filter instances share the same `vm_id` and same code source, Envoy reuses one VM
sandbox — saving memory for large plugins.

```yaml
# Listener A — plugin instance 1
vm_config:
  vm_id: "shared_auth_vm"
  runtime: envoy.wasm.runtime.v8
  code:
    local:
      filename: /etc/envoy/plugins/auth.wasm

# Listener B — plugin instance 2 (same vm_id = shared sandbox)
vm_config:
  vm_id: "shared_auth_vm"
  runtime: envoy.wasm.runtime.v8
  code:
    local:
      filename: /etc/envoy/plugins/auth.wasm
```

---

## Per-Route WASM Override

### Disable WASM on a specific route

```yaml
# In route config under virtual_hosts[].routes[]:
typed_per_filter_config:
  envoy.filters.http.wasm:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.WasmPerRoute
    disabled: true
```

`WasmPerRoute` has only one field: `disabled` (bool). There is no `config` or `override` subfield.

---

## Configuration Block Pattern

Plugin configuration is passed as a JSON string inside `google.protobuf.StringValue`:

```yaml
configuration:
  "@type": type.googleapis.com/google.protobuf.StringValue
  value: |
    {
      "allow_public_routes": true,
      "require_signed": false,
      "upstream_header": "x-user-id"
    }
```

The plugin reads this at init time via `proxy_wasm_get_plugin_configuration()`.

---

## OIDC via WASM Pattern

Used when native `envoy.filters.http.oauth2` is not available or a custom OIDC flow is needed.

```yaml
- name: envoy.filters.http.wasm
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.wasm.v3.Wasm
    config:
      name: "oidc-wasm-plugin"
      root_id: "oidc_root"
      configuration:
        "@type": type.googleapis.com/google.protobuf.StringValue
        value: |
          {
            "issuer_url":         "https://keycloak.example.com/realms/myrealm",
            "client_id":          "envoy-proxy",
            "client_secret":      "REPLACE_WITH_SECRET",
            "scopes":             ["openid", "email", "profile"],
            "callback_url":       "https://proxy.example.com/oidc/callback",
            "logout_url":         "https://proxy.example.com/oidc/logout",
            "jwks_uri":           "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs",
            "forward_access_token": true,
            "access_token_header": "X-Access-Token",
            "id_token_header":    "X-Id-Token",
            "upstream_headers_to_add": [
              {"key": "X-User-Email", "value": "{{email}}"},
              {"key": "X-User-Name",  "value": "{{name}}"}
            ]
          }
      vm_config:
        vm_id: "oidc_vm"
        runtime: envoy.wasm.runtime.v8
        code:
          remote:
            http_uri:
              uri: "https://plugins.example.com/oidc.wasm"
              cluster: wasm_plugin_registry
              timeout: 30s
            sha256: "replace-with-actual-sha256-of-oidc.wasm"
```

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| SHA-256 mismatch | Plugin download rejected at startup | Run `sha256sum plugin.wasm` and paste the exact value |
| `root_id` mismatch between filter and plugin | Plugin silently skipped | `config.root_id` must match the root context registered in plugin code |
| Missing `cluster` in `remote.http_uri` | Plugin fails to download | Define a cluster for the plugin registry host |
| `local_file:` used instead of `local: { filename: }` | Config rejected | Correct field is `code.local.filename` |
| `inline_bytes` with plugin > ~64 KB | Envoy rejects config | Use `local` or `remote` source for large plugins |
| Missing `vm_id` on shared plugins | Each filter creates its own VM, high memory | Set identical `vm_id` across filter instances that share code |
| `WasmPerRoute` with `config:` or `override:` | Config rejected — these fields don't exist | `WasmPerRoute` only has `disabled: true/false` |
| WASM runtime not compiled into Envoy binary | Startup failure | Build Envoy with the target runtime or use the official distroless image |
| Blocking I/O inside plugin without async API | Envoy thread stuck | All network I/O in plugins must use async proxy-wasm host calls |
| No `log_level` set during development | Hard to debug | Add `"log_level": "trace"` in the plugin configuration JSON |