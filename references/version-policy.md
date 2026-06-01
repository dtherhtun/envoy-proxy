# v1.38.0 Changelog Highlights

Source: https://www.envoyproxy.io/docs/envoy/v1.38.0/version_history/version_history

## v1.38.0 (features of note)

- Model Context Protocol (MCP) HTTP filters (`mcp`, `mcp_router`)
- `CacheV2` HTTP filter for Programmable HTTP caching
- Gradient Boosted Decision Tree (GBDT) for adaptive concurrency (replaces EWMA)
- Extended Local Rate Limit to QUIC listeners
- Upstream Host Reset Flood Protection
- gRPC Statistics filter (observability)
- Wasm: `deterministic_vm` option for repeated scheduling
- External Processing: server-side header mutation
- File System Buffer: large response buffering to reduce memory pressure

## Versioning

- v3 is the only supported API version
- `resource_api_version: V3` required in xDS configs for new deployments
- v2 API removed; any `type.googleapis.com/envoy.config.listener.v2.*` references must migrate

## Deprecation policy (quick rules)

- Features deprecated at N get removed at N+2 minor releases
- Check `enabled_by_default` flag in release notes
- Never use `config` (google.protobuf.Struct) — migrate to `typed_config` (google.protobuf.Any)

---

## Stable API promise (v1.38.0)

| ApiFamily | stable_at |
|-----------|-----------|
| v3 Bootstrap | v1.12 |
| v3 Listener | v1.12 |
| v3 Cluster | v1.12 |
| v3 Route | v1.12 |
| v3 Endpoint | v1.12 |
| xDS v3 | v1.12 |

All production APIs are stable. **Use only v3.**
