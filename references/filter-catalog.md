# Filter Catalog v1.38.0

Compact cross-reference. Full docs at envoyproxy.io.

## Network Filters (TCP layer)

Use in `listeners[].filter_chains[].filters[]` or `clusters[].transport_socket` flow.

| Filter | @type | Purpose |
|--------|-------|---------|
| TCP Proxy | `envoy.filters.network.tcp_proxy` | Default TCP pass-through |
| HTTP Conn Mgr | `envoy.filters.network.http_connection_manager` | L7 HTTP routing |
| TLS Inspector | `envoy.filters.listener.tls_inspector` | SNI extraction (listener filter) |
| Proxy Protocol | `envoy.filters.network.proxy_protocol` | PROXY protocol v1/v2 |
| Rate Limit | `envoy.filters.network.ratelimit` | Network-level rate limiting |
| Connection Limit | `envoy.filters.network.connection_limit` | Max connections per listener |
| Ext Authz | `envoy.filters.network.ext_authz` | External authorization |
| Direct Response | `envoy.filters.network.direct_response` | Immediate response, no upstream |
| Client TLS Auth | `envoy.filters.network.client_ssl_auth` | mTLS verification |
| RBAC | `envoy.filters.network.rbac` | Network-level RBAC |
| Wasm | `envoy.extensions.filters.network.wasm` | WASM-based Network filter |
| Golang | `envoy.extensions.filters.network.golang` | Go-based Network filter |

## HTTP Filters (HTTP layer, in HCM)

**Ordering constraint:** `router` MUST be last.

| Filter | @type | Placement |
|--------|-------|-----------|
| Router | `envoy.filters.http.router` | LAST, required |
| CORS | `envoy.filters.http.cors` | Before router |
| RBAC | `envoy.filters.http.rbac` | Before router |
| Ext Authz | `envoy.filters.http.ext_authz` | Before router |
| JWT Authn | `envoy.filters.http.jwt_authn` | After ext_authz if both |
| OAuth2 | `envoy.filters.http.oauth2` | End-to-end auth stack |
| Rate Limit | `envoy.filters.http.ratelimit` | After auth |
| IP Geolocation | `envoy.filters.http.ip_geolocation` | Early, metadata enrichment |
| Lua | `envoy.filters.http.lua` | Flexible per-request logic |
| Wasm | `envoy.extensions.filters.http.wasm` | WASM-based HTTP filter |
| Golang | `envoy.extensions.filters.http.golang` | Go-based HTTP filter |
| gRPC-JSON | `envoy.filters.http.grpc_json_transcoder` | gRPC→REST |
| gRPC-Web | `envoy.filters.http.grpc_web` | Browser gRPC |
| Fault Injection | `envoy.filters.http.fault` | Testing resilience |
| Adaptive Concurrency | `envoy.filters.http.adaptive_concurrency` | Auto limit concurrency |
| Bandwidth Limit | `envoy.filters.http.bandwidth_limit` | Per-route bandwidth cap |
| File System Buffer | `envoy.filters.http.file_system_buffer` | Disk-backed response buffer |
| MCP | `envoy.filters.http.mcp` | Model Context Protocol |
| MCP Router | `envoy.filters.http.mcp_router` | MCP routing |

## Filter Pitfalls

- `ext_authz` + `router` are always in pair: auth at network layer → no `http.ext_authz` needed (vice versa also valid)
- `lua` filter ordering matters: `before_router` config allows placement before router in chain; use it.
- `wasm` + `golang` filters load native extensions — validate binary paths before startup
- `config` field (google.protobuf.Struct) is deprecated -> `typed_config` (google.protobuf.Any)

## HTTP/2 and gRPC notes

- `http2_protocol_options`: set on HCM for upstream HTTP/2, or on listener for downstream
- `grpc_http1_bridge`: use on HCM for gRPC-Web or bridge scenarios
- `grpc_json_transcoder`: needs `proto_descriptor` and `services` list
