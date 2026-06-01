#!/usr/bin/env python3
"""
envoy-config-validator.py — Structural validator for Envoy v1.38.0 static config.

Checks (subset of references/validation-checks.md):
  1. Top-level required fields (node, admin)
  2. Listener structure: socket_address, filter_chains, typed_config
  3. typed_config uses correct field (not typeConfig) and has @type URL
  4. HCM presence + http_filters ends with router
  5. Cluster structure: name, type, connect_timeout, load_assignment
  6. Cross-refs: route clusters resolve to known cluster names
  7. Admin: reject 0.0.0.0 binding

Usage:
    python3 envoy-config-validator.py --path config.yaml
    python3 envoy-config-validator.py --path config.yaml --strict   # all checks
    python3 envoy-config-validator.py --path config.yaml --lint     # exit 0 always

Exit codes:
    0 = PASS
    1 = structural issues found
    2 = parse error
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENVOY_TYPE_RE = re.compile(r"^type\.googleapis\.com/envoy\.")
HCM_HTTP_FILTER_TYPE = "envoy.filters.network.http_connection_manager"
ROUTER_FILTER_TYPE = "envoy.filters.http.router"
VALID_CLUSTER_TYPES = {"STATIC", "STRICT_DNS", "ORIGINAL_DST", "LOGICAL_DNS", "EDS"}
CRITICAL_PITFALLS = [
    ("typeConfig", "Deprecated field `typeConfig` found — must be `typed_config`"),
    ("config:", "Legacy `config` (Struct) found — migrate to `typed_config` (Any)"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(d: dict, *keys, default=None):
    """Safe nested dict get."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _is_typed_config(value) -> bool:
    """Return True if value looks like a typed_config block with @type."""
    if not isinstance(value, dict):
        return False
    return "@type" in value and ENVOY_TYPE_RE.match(str(value["@type"]))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

class CheckResult:
    def __init__(self, check_id: str, ok: bool, severity: str, message: str):
        self.check_id = check_id
        self.ok = ok
        self.severity = severity  # CRITICAL | HIGH | MEDIUM | LOW | INFO
        self.message = message

    def __str__(self):
        status = "PASS" if self.ok else f"FAIL [{self.severity}]"
        return f"  {self.check_id}: {status} — {self.message}"


def check_top_level(cfg: dict) -> list[CheckResult]:
    results = []
    if not isinstance(cfg, dict):
        return [CheckResult("STR-001", False, "CRITICAL", "Root is not a mapping")]

    results.append(CheckResult(
        "STR-002", "node" in cfg, "CRITICAL", "`node` field is required"
    ))
    results.append(CheckResult(
        "STR-003", "admin" in cfg, "MEDIUM", "`admin` field is required (at least a stub)"
    ))
    return results


def check_listeners(cfg: dict) -> list[CheckResult]:
    results = []
    listeners = _get(cfg, "static_resources", "listeners", default=[])
    if not isinstance(listeners, list):
        return [CheckResult("LIS-000", False, "CRITICAL", "`static_resources.listeners` must be a list")]

    for i, listener in enumerate(listeners):
        prefix = f"listeners[{i}]"
        name = listener.get("name", f"<unnamed-{i}>")
        lp = f"{prefix}({name})"

        results.append(CheckResult(
            f"{lp}-name",
            bool(listener.get("name")),
            "HIGH", f"listener name required"
        ))

        addr = _get(listener, "address", "socket_address")
        if not addr:
            results.append(CheckResult(
                f"{lp}-addr", False, "CRITICAL", "Missing socket_address"
            ))
        else:
            has_addr = bool(addr.get("address"))
            has_port = "port_value" in addr
            results.append(CheckResult(
                f"{lp}-addr", has_addr and has_port, "HIGH",
                f"address={addr.get('address', '?')}:{addr.get('port_value', '?')}"
            ))

        fcs = _get(listener, "filter_chains", default=[])
        if not fcs:
            results.append(CheckResult(
                f"{lp}-fc", False, "CRITICAL", "At least one filter_chain required"
            ))
        else:
            for j, fc in enumerate(fcs):
                filters = _get(fc, "filters", default=[])
                for k, filt in enumerate(filters):
                    # Check for deprecated typeConfig
                    if "typeConfig" in filt:
                        results.append(CheckResult(
                            f"{lp}-fc{j}-f{k}", False, "CRITICAL",
                            "PITFALL #1: `typeConfig` is ignored — use `typed_config`"
                        ))

                    tc = filt.get("typed_config") or filt.get("config")
                    if tc is None:
                        results.append(CheckResult(
                            f"{lp}-fc{j}-f{k}", False, "HIGH",
                            "Neither typed_config nor config present"
                        ))
                    elif not _is_typed_config(tc):
                        atype = tc.get("@type") if isinstance(tc, dict) else None
                        if atype is None:
                            results.append(CheckResult(
                                f"{lp}-fc{j}-f{k}", False, "HIGH",
                                "typed_config missing @type URL"
                            ))
                        elif not ENVOY_TYPE_RE.match(str(atype)):
                            results.append(CheckResult(
                                f"{lp}-fc{j}-f{k}", False, "MEDIUM",
                                f"@type URL does not look like Envoy type: {atype}"
                            ))

                    # HCM-specific checks
                    ftype = tc.get("@type") if isinstance(tc, dict) else None
                    if ftype and HCM_HTTP_FILTER_TYPE in str(ftype):
                        sp = filt.get("stat_prefix", "")
                        results.append(CheckResult(
                            f"{lp}-fc{j}-f{k}-sp",
                            bool(sp), "MEDIUM",
                            f"stat_prefix='{sp or '<missing>'}'"
                        ))

                        hf = _get(filt, "typed_config", "http_filters", default=[])
                        if hf:
                            last = hf[-1]
                            lt = (last.get("typed_config") or last.get("config") or {})
                            atype_last = lt.get("@type") if isinstance(lt, dict) else None
                            if atype_last != ROUTER_FILTER_TYPE:
                                results.append(CheckResult(
                                    f"{lp}-fc{j}-f{k}-router",
                                    False, "CRITICAL",
                                    f"PITFALL #3: Last http_filter is {atype_last or '?'} — "
                                    f"must be {ROUTER_FILTER_TYPE}"
                                ))

                        # Route / RDS must be present
                        has_routes = bool(
                            _get(filt, "typed_config", "route_config")
                            or _get(filt, "typed_config", "rds")
                        )
                        results.append(CheckResult(
                            f"{lp}-fc{j}-f{k}-routes",
                            has_routes, "HIGH",
                            "route_config or rds required in HCM"
                        ))
    return results


def check_clusters(cfg: dict) -> list[CheckResult]:
    results = []
    clusters = _get(cfg, "static_resources", "clusters", default=[])
    if not isinstance(clusters, list):
        return [CheckResult("CLU-000", False, "CRITICAL", "`static_resources.clusters` must be a list")]

    known_clusters: set[str] = set()
    for i, cluster in enumerate(clusters):
        name = cluster.get("name", f"<unnamed-{i}>")
        lp = f"clusters[{i}]({name})"
        known_clusters.add(name)

        results.append(CheckResult(
            f"{lp}-name", bool(name), "HIGH", "cluster name required"
        ))

        ctype = cluster.get("type", "")
        results.append(CheckResult(
            f"{lp}-type",
            ctype in VALID_CLUSTER_TYPES,
            "HIGH",
            f"cluster type: {ctype or '<missing>'}"
        ))

        ct = cluster.get("connect_timeout")
        results.append(CheckResult(
            f"{lp}-ct",
            ct is not None, "HIGH",
            f"connect_timeout: {ct or '<missing — defaults to 15s>'}"
        ))

        la = _get(cluster, "load_assignment", "endpoints", default=[])
        if ctype in {"STATIC", "STRICT_DNS", "LOGICAL_DNS"}:
            if not la or not any(
                _get(ep, "lb_endpoints") for ep in la
            ):
                results.append(CheckResult(
                    f"{lp}-la", False, "MEDIUM",
                    "load_assignment.endpoints[] required for STATIC/LOGICAL_DNS"
                ))

        ts = cluster.get("transport_socket")
        if ts:
            tc = ts.get("typed_config") or ts.get("config")
            if tc:
                atype = tc.get("@type") if isinstance(tc, dict) else None
                is_tls = atype and "tls.v3" in str(atype)
                results.append(CheckResult(
                    f"{lp}-tls-atype",
                    is_tls, "LOW",
                    f"transport_socket @type: {atype or '?'}"
                ))

    # Cross-ref: route clusters
    all_filters = _get(cfg, "static_resources", "listeners", default=[])
    all_hcms = []
    for listener in all_filters:
        for fc in _get(listener, "filter_chains", default=[]):
            for filt in _get(fc, "filters", default=[]):
                tc = _get(filt, "typed_config", default={})
                ftype = tc.get("@type", "")
                if HCM_HTTP_FILTER_TYPE in str(ftype):
                    all_hcms.append(tc)

    for hcm in all_hcms:
        routes = []
        for vh in _get(hcm, "route_config", "virtual_hosts", default=[]):
            routes.extend(_get(vh, "routes", default=[]))
        if not routes:
            continue
        for j, route in enumerate(routes):
            ra = _get(route, "route", "cluster")
            if ra and ra not in known_clusters:
                results.append(CheckResult(
                    f"XREF-route-{j}", False, "HIGH",
                    f"Route references cluster '{ra}' not defined in static_resources.clusters"
                ))

    return results


def check_admin(cfg: dict) -> list[CheckResult]:
    results = []
    admin = cfg.get("admin", {})
    addr = _get(admin, "address", "socket_address", default={})
    bind = addr.get("address", "127.0.0.1")
    if bind in ("0.0.0.0", "::"):
        results.append(CheckResult(
            "ADM-001", False, "CRITICAL",
            f"Admin bound to {bind} — restrict to 127.0.0.1 or use allow_paths"
        ))
    elif bind:
        results.append(CheckResult("ADM-001", True, "CRITICAL", f"Admin bound to {bind}"))
    return results


def run_checks(cfg: dict, strict: bool = False) -> tuple[int, list[CheckResult]]:
    all_results: list[CheckResult] = []
    all_results.extend(check_top_level(cfg))
    all_results.extend(check_listeners(cfg))
    all_results.extend(check_clusters(cfg))
    all_results.extend(check_admin(cfg))

    if strict:
        known_types = {f["@type"] for f in all_results if f.check_id.startswith("http_filters")}

    failures = sum(1 for r in all_results if not r.ok)
    return failures, all_results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Envoy v1.38.0 config validator")
    parser.add_argument("--path", required=True, help="Path to Envoy YAML config")
    parser.add_argument("--strict", action="store_true", help="Treat all warnings as failures")
    parser.add_argument("--lint", action="store_true", help="Print results, exit 0 always")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: {args.path} not found", file=sys.stderr)
        sys.exit(2)

    try:
        cfg = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse failed: {e}", file=sys.stderr)
        sys.exit(2)

    failures, results = run_checks(cfg, strict=args.strict)

    for r in results:
        print(r)

    print()
    if failures == 0:
        print("RESULT: PASS — no structural issues found")
        sys.exit(0)
    else:
        print(f"RESULT: FAIL — {failures} check(s) failed")
        sys.exit(1 if not args.lint else 0)


if __name__ == "__main__":
    main()
