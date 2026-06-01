# Validation Checks

Structural correctness — run before any other check. Exit non-zero if any FAIL.

## Required top-level fields

```
node:         MANDATORY (envoy.node.v3.Node)
admin:        REQUIRED (even if minimal)
```

## Listener validation

- `name` is non-empty string
- `address` is `socket_address` with `address` + `port_value`
- At least one `filter_chain`; each has `filters` array
- Exactly ONE `typed_config` per filter (not `typeConfig`)
- `typed_config["@type"]` present and valid Envoy type URL
- If filter is HCM: `stat_prefix` non-empty, `route_config` or `rds` present
- HCM `http_filters` array ends with `typed_config["@type"] == envoy.filters.http.router`

## Cluster validation

- `name` non-empty, unique across static + dynamic
- `type` one of: STATIC, STRICT_DNS, ORIGINAL_DST, LOGICAL_DNS, EDS
- `connect_timeout` present and parsable
- Static/cluster type has `load_assignment` with at least one `endpoint`
- If `transport_socket` present: `typed_config["@type"]` valid TLS type

## Cross-reference

- Every `route_action.cluster` in HCM resolves to a known cluster name
- Every SDS `tls_certificate` reference resolves to a defined secret
- Rate limit domain stat prefix matches across descriptors and response

## Common errors

| Field | Problem | Fix |
|------|--------|-----|
| `typeConfig` | Deprecated, silently dropped | Rename to `typed_config` |
| Missing `@type` URL | v1.31+ rejects config | Add `type.googleapis.com/envoy.*` |
| Double `typed_config` | Proto merge conflict | One per filter only |
| HCM in network_filters | Wrong layer, error | Network layer → TCP Proxy; HCM in HTTP layer only |
