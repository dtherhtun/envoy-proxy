# OIDC / OAuth2 / Keycloak Patterns (v1.38.0)

Three integration patterns, from simplest to most flexible:

| Pattern | Use Case | Filter |
|---------|----------|--------|
| **A — Native OAuth2** | Browser SSO, authorization code flow | `envoy.filters.http.oauth2` |
| **B — JWT validation** | API-to-API, tokens already issued | `envoy.filters.http.jwt_authn` |
| **C — ExtAuthz** | Complex auth, token introspection, group checks | `envoy.filters.http.ext_authz` |

---

## Filter Ordering (Critical)

```
oauth2 → jwt_authn → rbac → wasm → ext_authz → local_ratelimit → cors → header_mutation → lua → router
```

Rules:
- `router` must always be last.
- `oauth2` before `jwt_authn` — OAuth2 sets cookies that JWT reads.
- `jwt_authn` before `rbac` — RBAC checks decoded JWT claims.
- Never put `cors` before `ext_authz` — OPTIONS preflight would bypass auth.

---

## Keycloak URL Patterns

| Endpoint | URL |
|----------|-----|
| OIDC Discovery | `https://keycloak.example.com/realms/{realm}/.well-known/openid-configuration` |
| Authorization | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/auth` |
| Token | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/token` |
| JWKS | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/certs` |
| UserInfo | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/userinfo` |
| Logout | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/logout` |
| Introspect | `https://keycloak.example.com/realms/{realm}/protocol/openid-connect/token/introspect` |

---

## Pattern A — Native OAuth2 Filter (Browser SSO)

### SDS Secrets (required — never inline)

```yaml
# /etc/envoy/secrets/oauth-secrets.yaml
resources:
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_token
  generic_secret:
    secret:
      filename: /etc/envoy/secrets/oauth-client-secret.txt  # OAuth2 client secret
- "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.Secret
  name: oauth_hmac
  generic_secret:
    secret:
      filename: /etc/envoy/secrets/oauth-hmac-key.txt       # Random key ≥ 32 bytes
```

### OAuth2 Filter Config

```yaml
- name: envoy.filters.http.oauth2
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
    config:
      token_endpoint:
        cluster: keycloak
        uri: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/token"
        timeout: 5s
      authorization_endpoint: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/auth"
      redirect_uri: "%REQ(x-forwarded-proto)%://%REQ(:authority)%/callback"
      redirect_path_matcher:
        path:
          exact: /callback
      signout_path:
        path:
          exact: /signout
      credentials:
        client_id: "envoy-proxy"
        token_secret:
          name: oauth_token
          sds_config:
            path: /etc/envoy/secrets/oauth-secrets.yaml
        hmac_secret:
          name: oauth_hmac
          sds_config:
            path: /etc/envoy/secrets/oauth-secrets.yaml
      auth_scopes:
      - openid
      - profile
      - email
      - roles
      forward_bearer_token: true
      use_refresh_token: true
      # cookie_names uses these exact field names (not "hmac" or "expires"):
      cookie_names:
        bearer_token: "OAuth2_BearerToken"
        oauth_hmac: "OAuth2_HMAC"
        oauth_expires: "OAuth2_Expires"
        id_token: "OAuth2_IdToken"
        refresh_token: "OAuth2_RefreshToken"
      # Routes to skip OAuth2 (public paths):
      pass_through_matcher:
      - name: ":path"
        prefix_match: "/api/public/"
      - name: ":path"
        exact_match: "/healthz"
```

> `pass_through_matcher` takes a **list of `HeaderMatcher`** directly — no `header_matcher:` wrapper.
> `cookie_names` fields: `bearer_token`, `oauth_hmac`, `oauth_expires`, `id_token`, `refresh_token`.

### Route Config for OAuth2

```yaml
route_config:
  name: main_route
  virtual_hosts:
  - name: web_app
    domains: ["proxy.example.com"]
    routes:
    # Disable OAuth2 on the callback route itself
    - match:
        path: /callback
      route:
        cluster: keycloak
        timeout: 5s
      typed_per_filter_config:
        envoy.filters.http.oauth2:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2PerRoute
          disabled: true

    # Disable OAuth2 on signout too
    - match:
        path: /signout
      direct_response:
        status: 302
        headers_to_add:
        - header:
            key: Location
            value: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/logout?redirect_uri=https://proxy.example.com/"
      typed_per_filter_config:
        envoy.filters.http.oauth2:
          "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2PerRoute
          disabled: true

    - match:
        prefix: /
      route:
        cluster: web_service
        timeout: 30s
```

### Keycloak Cluster

```yaml
- name: keycloak
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: keycloak
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: keycloak.example.com
              port_value: 8080
```

---

## Pattern B — JWT Validation Only (API-to-API)

```yaml
- name: envoy.filters.http.jwt_authn
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
    providers:
      keycloak_provider:
        issuer: "https://keycloak.example.com/realms/myrealm"
        audiences:
        - "envoy-proxy"
        - "backend-service"
        remote_jwks:
          http_uri:
            uri: "https://keycloak.example.com/realms/myrealm/protocol/openid-connect/certs"
            cluster: keycloak_jwks
            timeout: 5s
          cache_duration: 300s
        # Where to look for the token:
        from_headers:
        - name: "Authorization"
          value_prefix: "Bearer "
        from_cookies:
        - name: "OAuth2_BearerToken"
        # Forward JWT claims as request headers to upstream:
        claim_to_headers:
        - header_name: "x-user-id"
          claim_name: "sub"
        - header_name: "x-user-email"
          claim_name: "email"
        - header_name: "x-user-roles"
          claim_name: "realm_access.roles"
        forward: true                              # forward original token upstream
        forward_payload_header: "x-jwt-payload"   # base64-encoded payload header
    rules:
    # No JWT required on public routes
    - match:
        prefix: /api/public/
      requires:
        allow_missing_or_failed: {}
    # JWT required on all other routes
    - match:
        prefix: /api/
      requires:
        provider_name: keycloak_provider
    # Require JWT for admin routes
    - match:
        prefix: /admin/
      requires:
        provider_name: keycloak_provider
    # Default: require JWT
    - match:
        prefix: /
      requires:
        provider_name: keycloak_provider
```

> `claim_to_headers` uses `header_name` and `claim_name` fields. There is no `format` field.
> `rules[].requires` takes an inline `JwtRequirement` — not a string reference.
> Use `allow_missing_or_failed: {}` to skip JWT validation on a route.

### Disable JWT on a specific route

```yaml
typed_per_filter_config:
  envoy.filters.http.jwt_authn:
    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthenticationPerRoute
    disabled: true
```

### JWKS cluster

```yaml
- name: keycloak_jwks
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: keycloak_jwks
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: keycloak.example.com
              port_value: 8080
```

---

## Pattern C — ExtAuthz with oauth2-proxy Sidecar

```yaml
- name: envoy.filters.http.ext_authz
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.ext_authz.v3.ExtAuthz
    http_service:
      server_uri:
        cluster: oauth2_proxy
        uri: "http://oauth2-proxy:4180/oauth2/auth"
        timeout: 5s
      authorization_request:
        allowed_headers:
          patterns:
          - exact: "authorization"
          - exact: "cookie"
          - prefix: "x-forwarded-"
          - exact: "x-request-id"
      authorization_response:
        allowed_upstream_headers:
          patterns:
          - exact: "set-cookie"
          - exact: "x-auth-request-user"
          - exact: "x-auth-request-email"
          - exact: "x-auth-request-groups"
    failure_mode_allow: false    # deny if oauth2-proxy is unreachable
    transport_api_version: V3
```

> `allowed_upstream_headers` belongs in `authorization_response`, not `authorization_request`.
> `server_uri` fields: `cluster`, `uri`, `timeout` — there is no `port_value` field.

### oauth2-proxy (Keycloak backend)

```bash
oauth2-proxy \
  --provider=keycloak-oidc \
  --oidc-issuer-url=https://keycloak.example.com/realms/myrealm \
  --client-id=envoy-proxy \
  --client-secret=$(cat /etc/oauth2-proxy/client-secret.txt) \
  --cookie-secret=$(cat /etc/oauth2-proxy/cookie-secret.txt) \
  --redirect-url=https://proxy.example.com/oauth2/callback \
  --email-domain=example.com \
  --upstream=static://200 \
  --http-address=0.0.0.0:4180 \
  --set-xauthrequest=true \
  --set-authorization-header=true \
  --pass-user-headers=true \
  --cookie-secure=true \
  --cookie-samesite=lax
```

### oauth2-proxy cluster

```yaml
- name: oauth2_proxy
  type: STRICT_DNS
  connect_timeout: 5s
  lb_policy: ROUND_ROBIN
  load_assignment:
    cluster_name: oauth2_proxy
    endpoints:
    - lb_endpoints:
      - endpoint:
          address:
            socket_address:
              address: oauth2-proxy
              port_value: 4180
```

---

## RBAC Filter

Each RBAC filter instance has **one action** (`ALLOW` or `DENY`) plus a policies map.
To enforce both ALLOW and DENY logic, use two RBAC filters in sequence.

```yaml
# Filter 1: ALLOW only known service accounts
- name: envoy.filters.http.rbac
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC
    rules:
      action: ALLOW
      policies:
        allow-internal-services:
          permissions:
          - any: true
          principals:
          - authenticated:
              principal_name:
                safe_regex:
                  regex: "spiffe://trust-domain/ns/default/sa/.*"

# Filter 2: DENY admin paths from external IPs
- name: envoy.filters.http.rbac
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC
    rules:
      action: DENY
      policies:
        block-external-admin:
          permissions:
          - header:
              name: ":path"
              prefix_match: "/admin/"
          principals:
          - not_id:
              remote_ip:
                address_prefix: "10.0.0.0"
                prefix_len: 8
```

---

## Complete Filter Chain (OAuth2 + JWT + RBAC + CORS)

```yaml
http_filters:
# 1. Browser SSO
- name: envoy.filters.http.oauth2
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.oauth2.v3.OAuth2
    config: { ... }   # see Pattern A

# 2. API token validation
- name: envoy.filters.http.jwt_authn
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
    # ... see Pattern B

# 3. Role / IP access control
- name: envoy.filters.http.rbac
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.rbac.v3.RBAC
    rules:
      action: ALLOW
      policies:
        allow-authenticated:
          permissions:
          - any: true
          principals:
          - any: true

# 4. Rate limiting
- name: envoy.filters.http.local_ratelimit
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit
    stat_prefix: local_rate_limit
    token_bucket:
      max_tokens: 100
      tokens_per_fill: 100
      fill_interval: 60s

# 5. CORS
- name: envoy.filters.http.cors
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.cors.v3.Cors

# 6. Router (always last)
- name: envoy.filters.http.router
  typed_config:
    "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

---

## Keycloak Client Configuration Checklist

| Setting | Value | Notes |
|---------|-------|-------|
| Client Protocol | `openid-connect` | Standard OIDC |
| Access Type | `confidential` | Required for auth code flow |
| Valid Redirect URIs | `https://proxy.example.com/callback` | Must match `redirect_uri` |
| Web Origins | `https://proxy.example.com` | For CORS |
| Standard Flow | `Enabled` | Authorization code flow |
| Direct Access Grants | `Disabled` | Unless needed for testing |

---

## Common Pitfalls

| Pitfall | Impact | Fix |
|---------|--------|-----|
| String-reference `requires: "valid-jwt"` in JWT rules | Config rejected — not a valid proto field | Use inline `JwtRequirement`: `requires: { provider_name: keycloak_provider }` |
| `requires: ""` to skip JWT | Empty string is not valid | Use `allow_missing_or_failed: {}` |
| `pass_through_matcher: header_matcher: { ... }` | Extra wrapper key — rejected | `pass_through_matcher` is a list of `HeaderMatcher` directly |
| `cookie_names.hmac` or `cookie_names.expires` | Wrong field names — silently ignored | Use `oauth_hmac` and `oauth_expires` |
| `claim_to_headers[].key` | Wrong field name | Use `header_name` |
| `claim_to_headers[].claim` | Wrong field name | Use `claim_name` |
| `claim_to_headers[].format` | Field doesn't exist | Remove it |
| `overlapping_unit` in `remote_jwks` | Field doesn't exist — rejected | Remove; use `cache_duration` only |
| `deny_redirect_matcher` in OAuth2Config | Field doesn't exist | Remove it |
| `port_value` in ExtAuthz `server_uri` | Field doesn't exist | Put port in the cluster socket_address |
| `allowed_upstream_headers` in `authorization_request` | Wrong block — headers not forwarded | Move to `authorization_response` |
| Two `action:` types in one RBAC filter | Proto only allows one action per filter | Use two RBAC filter instances |
| Missing `hmac_secret` SDS config | OAuth2 cookies cannot be signed/verified | Always configure both `token_secret` and `hmac_secret` |
| JWT `issuer` mismatch with Keycloak | All token validation fails | `issuer` must exactly match Keycloak's `iss` claim |
| Missing `audiences` in jwt_authn | Tokens accepted without audience check | Always set `audiences` to the expected client IDs |
| Redundant JWT + OAuth2 on same route | Requests validated twice, duplicate latency | Disable JWT on routes covered by OAuth2 using `JwtAuthenticationPerRoute.disabled` |