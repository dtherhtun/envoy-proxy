# Observability Quick Reference

## Stats Naming Conventions

```
cluster.<name>.upstream_cx_total           (total connections)
cluster.<name>.upstream_rq_total           (total requests)
cluster.<name>.upstream_rq_5xx             (5xx rate)
cluster.<name>.upstream_rq_pending_total   (circuit breaker signal)
http.<stat_prefix>.downstream_rq_total     (HCM request total)
http.<stat_prefix>.downstream_rq_2xx/4xx/5xx
listener.<name>.downstream_cx_total        (listener connections)
server.version                            (Envoy binary version)
```

Prometheus sink: `envoy.stat_sinks.metrics_service` or statsd/Graphite.

## Access Log (preferred JSON template)

```yaml
access_log:
  - name: envoy.access_loggers.file
    typed_config:
      "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
      path: /var/log/envoy/access.log
      typed_json_format:
        "@timestamp": "%START_TIME%"
        authority: "%REQ(:AUTHORITY)%"
        method: "%REQ(:METHOD)%"
        path: "%REQ(X-ENVOY-ORIGINAL-PATH?:PATH)%"
        protocol: "%PROTOCOL%"
        response_code: "%RESPONSE_CODE%"
        response_flags: "%RESPONSE_FLAGS%"
        bytes_received: "%BYTES_RECEIVED%"
        bytes_sent: "%BYTES_SENT%"
        duration: "%DURATION%"
        upstream_host: "%UPSTREAM_HOST%"
```

## Tracing

Add to HCM:

```yaml
tracing:
  providers:
    - name: envoy.tracers.zipkin
      typed_config:
        "@type": type.googleapis.com/envoy.config.trace.v3.ZipkinConfig
        collector_cluster: zipkin
        collector_endpoint: /api/v2/spans
```

Top 3 signals for triage:
1. `upstream_rq_pending_total` > `max_requests` → circuit breaker hitting
2. `upstream_rq_5xx` spike → upstream issue or Envoy misconfigured route
3. `downstream_cx_destroy_remote_active` → client abort patterns
