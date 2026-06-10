# Envoy Proxy Skill (v1.38.0)

AI-engineering skill for Envoy proxy v1.38.0: validate configs, audit production readiness, and query reference docs — token-efficient and model-friendly.

## Install / Use

**A. As an AI skill (e.g. Hermes, OpenCode, Claude Code)**

Copy or symlink the full directory into your skills path:

```bash
cp -r envoy-proxy /path/to/skills/envoy-proxy
# or
ln -s "$PWD/envoy-proxy" /path/to/skills/envoy-proxy
```

The skill is driven by `SKILL.md`. Reference files under `references/` are loaded on demand, keeping token cost low. Scripts under `scripts/` are executable validators/auditors — run them directly or let the model invoke them.

**B. Validator / Auditor CLI (standalone)**

```bash
python3 scripts/envoy-config-validator.py assets/config-good.yaml
python3 scripts/envoy-auditor.py         assets/config-bad.yaml
```

Requires `PyYAML 6+`:

```bash
# uv
uv tool install pyyaml

# or pip (install into same venv as your agent)
python3 -m pip install pyyaml
```

## Quick Start

```bash
# Structural check — must-pass gate before deployment
python3 scripts/envoy-config-validator.py envoy.yaml

# Production readiness audit — lint for security/resilience gaps
python3 scripts/envoy-auditor.py envoy.yaml

# Exit codes: 0 = pass, 1 = fail. Human-readable report to stdout.
```

## What It Checks

**Validator (structural, ~27 rules)**

- `node`, `static_resources`, `admin` present
- No `typeConfig` typo vs `typed_config`
- Every dynamic resource has `@type: type.googleapis.com/...`
- HCM has `http_filters` ending with `envoy.filters.http.router`
- Clusters have `load_assignment` + `lb_policy` + type (`typed_config` or `cluster_type`)
- Admin `address` bound to `127.0.0.1`, not `0.0.0.0`
- TLS present on inbound listeners in production-like configs

**Auditor (readiness, ~50 checks)**

- Security: no `allow_any_header`, no plaintext to upstream, admin not exposed
- Resilience: `connect_timeout`, `circuit_breakers`, `health_checks`, `outlier_detection`, retries
- Observability: `access_log` present on both listener and cluster
- Operations: `statsd` / `stats_config`, tracing provider configured

Checks are tiered: `CRITICAL` / `HIGH` / `MEDIUM` / `LOW`.

## File Layout

```
envoy-proxy/
├── SKILL.md                   # Skill entry point, triggers, tags
├── references/
│   ├── validation-checks.md   # Structural validation rules
│   ├── audit-checks.md        # Security / resilience / observability checklist
│   ├── filter-catalog.md      # Network + HTTP filter inventory (v1.38.0)
│   ├── observability.md       # Stats naming, access log, tracing
│   ├── config-patterns.md     # Canonical static/bootstrap YAML
│   └── version-policy.md      # v1.38.0 changelog, deprecations
├── scripts/
│   ├── envoy-config-validator.py
│   └── envoy-auditor.py
└── assets/
    ├── config-good.yaml       # PASS-through fixture
    └── config-bad.yaml        # Triggers all documented pitfalls
```

## Repo

Pushed to: `github.com/dtherhtun/envoy-proxy.git`

Target Envoy version: `v1.38.0`
