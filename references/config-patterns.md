# Config Patterns

## Minimal Static Bootstrap

```yaml
static_resources:
  listeners:
    - name: ingress
      address:
        socket_address:
          address: 0.0.0.0
          port_value: 8080
      filter_chains:
        - filters:
            - name: envoy.filters.network.http_connection_manager
              typed_config:
                "@type": type.googleapis.com/envoy.config.network.v3.HttpConnectionManager
                stat_prefix: ingress_http
                route_config:
                  name: local_route
                  virtual_hosts:
                    - name: backend
                      domains: ["*"]
                      routes:
                        - match: {prefix: "/"}
                          route: {cluster: backend_api}
                http_filters:
                  - name: envoy.filters.http.router
                    typed_config:
                      "@type": type.googleapis.com/envoy.config.http.v3.Router
  clusters:
    - name: my-xds-server
      connect_timeout: 5s
      type: STRICT_DNS
      lb_policy: ROUND_ROBIN
      load_assignment:
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: xds.example.com
                      port_value: 18000
admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901
  allow_paths:
    allow_paths:
      - exact: /ready
```

## Dynamic Resource (xDS) Pattern

```yaml
dynamic_resources:
  cds_config:
    resource_api_version: V3
    api_config_source:
      api_type: GRPC
      transport_api_version: V3
      grpc_services:
        - envoy_grpc:
            cluster_name: my-xds-server
  lds_config:
    resource_api_version: V3
    api_config_source:
      api_type: GRPC
      transport_api_version: V3
      grpc_services:
        - envoy_grpc:
            cluster_name: my-xds-server
node:
  id: proxy-node-1
  cluster: ingress-cluster
```

## mTLS Upstream (SDS pattern)

```yaml
transport_socket:
  name: envoy.transport_sockets.tls
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.UpstreamTls
    common_tls_context:
      tls_certificates:
        - certificate_chain: {filename: "/certs/cert-chain.pem"}
          private_key: {filename: "/certs/key.pem"}
      validation_context:
        trusted_ca: {filename: "/certs/ca-cert.pem"}
        match_subject_alt_names:
          - exact: "*.internal.example.com"
```

## Rate Limit (cluster level)

`circuit_breakers` on cluster:

```yaml
circuit_breakers:
  thresholds:
    - priority: DEFAULT
      max_connections: 1024
      max_pending_requests: 1024
      max_requests: 1024
      max_retries: 3
```

Per-route rate limit: HTTP rate limit filter with `domain` + `descriptors`.

## Health Check (passive + active)

```yaml
health_checks:
  - timeout: 2s
    interval: 5s
    unhealthy_threshold: 2
    healthy_threshold: 2
    http_health_check:
      host: localhost
      path: /healthz
      expected_codes:
        - 200

outlier_detection:
  consecutive_5xx: 5
  interval: 2s
  base_ejection_time: 30s
  max_ejection_percent: 50
```
