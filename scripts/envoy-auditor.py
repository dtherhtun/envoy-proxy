#!/usr/bin/env python3
"""
envoy-auditor.py — Production readiness audit for Envoy v1.38.0 configs.

Exit: 0 = PASS, 1 = FAIL on security/resilience checks.

Usage:
    python3 envoy-auditor.py --path config.yaml
    python3 envoy-auditor.py --path config.yaml --check SEC-001,RES-001
    python3 envoy-auditor.py --path config.yaml --summary
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


class AuditResult:
    def __init__(self, check_id: str, ok: bool, severity: str, message: str):
        self.check_id = check_id; self.ok = ok
        self.severity = severity; self.message = message

    def __str__(self):
        s = "PASS" if self.ok else "FAIL"
        return f"  [{self.severity}] {self.check_id}: {s} - {self.message}"


def _get(d, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def audit_admin(cfg):
    results = []
    admin = cfg.get("admin", {})
    addr = _get(admin, "address", "socket_address", default={})
    bind = addr.get("address", "127.0.0.1")
    if bind in ("0.0.0.0", "::", None):
        results.append(AuditResult(
            "SEC-001", False, "CRITICAL",
            f"Admin bound to {bind or 'unset'} - must bind to 127.0.0.1"
        ))
    else:
        results.append(AuditResult("SEC-001", True, "CRITICAL", f"Admin bound to {bind}"))

    allow_paths = _get(admin, "allow_paths", "allow_paths", default=[])
    if not allow_paths and bind not in ("127.0.0.1", "::1"):
        results.append(AuditResult("SEC-001b", False, "HIGH", "No allow_paths set on exposed admin"))
    return results


def audit_tls(cfg):
    results = []
    listeners = _get(cfg, "static_resources", "listeners", default=[])
    deprecated = {"TLSv1_0", "TLSv1_1", "TLSv1_0_WORKING", "TLSv1_1_WORKING"}

    for i, l in enumerate(listeners):
        fcs = _get(l, "filter_chains", default=[])
        for j, fc in enumerate(fcs):
            tls_ctx = _get(l, "filter_chains", j, "transport_socket", "typed_config", default={})
            tls_params = _get(tls_ctx, "tls_params", default={})
            min_proto = _get(tls_params, "tls_minimum_protocol_version", default="")

            if min_proto:
                ok = min_proto not in deprecated
                results.append(AuditResult(
                    f"SEC-002[{i}:{j}]", ok, "CRITICAL",
                    f"tls_minimum_protocol_version={min_proto}"
                ))

            listener_ts = _get(l, "filter_chains", j, "transport_socket")
            if listener_ts:
                at = _get(listener_ts, "typed_config", "@type", default="")
                results.append(AuditResult(
                    f"SEC-003[{i}:{j}]", "tls" in at, "CRITICAL",
                    f"transport_socket @type: {at or '<missing>'}"
                ))
    return results


def audit_clusters(cfg):
    results = []
    clusters = _get(cfg, "static_resources", "clusters", default=[])
    if not isinstance(clusters, list):
        return results

    for i, c in enumerate(clusters):
        name = c.get("name", f"<{i}>")
        ct_val = c.get("connect_timeout")
        ct_fmt = ct_val if ct_val else "MISSING - defaults to 15s"
        results.append(AuditResult(
            f"RES-001[{name}]", ct_val is not None, "HIGH",
            f"connect_timeout: {ct_fmt}"
        ))

        hcs = c.get("health_checks", [])
        results.append(AuditResult(
            f"RES-002[{name}]", bool(hcs), "HIGH",
            f"health_checks: {'set' if hcs else 'MISSING'}"
        ))

        cb = _get(c, "circuit_breakers", "thresholds", default=[])
        cb_list = cb if isinstance(cb, list) else [cb] if cb else []
        has_cb = any(_get(t, "max_connections") for t in cb_list)
        results.append(AuditResult(
            f"RES-003[{name}]", has_cb, "HIGH",
            f"circuit_breakers: {'configured' if has_cb else 'MISSING'}"
        ))

        od = c.get("outlier_detection")
        results.append(AuditResult(
            f"RES-004[{name}]", od is not None, "LOW",
            f"outlier_detection: {'set' if od else 'not set (recommended >=3 endpoints)'}"
        ))
    return results


def audit_access_log(cfg):
    results = []
    listeners = _get(cfg, "static_resources", "listeners", default=[])
    has_log = False
    for l in listeners:
        for fc in _get(l, "filter_chains", default=[]):
            for filt in _get(fc, "filters", default=[]):
                tc = _get(filt, "typed_config", default={})
                if _get(tc, "access_log"):
                    has_log = True
    results.append(AuditResult(
        "OPS-001", has_log, "HIGH",
        "access_log: configured" if has_log else "access_log: MISSING"
    ))
    return results


def run_audit(cfg, selected=None):
    all_checks = []
    all_checks.extend(audit_admin(cfg))
    all_checks.extend(audit_tls(cfg))
    all_checks.extend(audit_clusters(cfg))
    all_checks.extend(audit_access_log(cfg))

    if selected:
        all_checks = [r for r in all_checks if r.check_id.split("[")[0] in selected]

    failures = sum(1 for r in all_checks if not r.ok)
    return failures, all_checks


def main():
    parser = argparse.ArgumentParser(description="Envoy v1.38.0 production audit")
    parser.add_argument("--path", required=True)
    parser.add_argument("--check", help="Comma-separated check IDs (e.g. SEC-001)")
    parser.add_argument("--summary", action="store_true", help="Only show FAILs")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: {args.path} not found", file=sys.stderr); sys.exit(2)

    try:
        cfg = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse: {e}", file=sys.stderr); sys.exit(2)

    selected = set(args.check.split(",")) if args.check else None
    failures, results = run_audit(cfg, selected)

    for r in sorted(results, key=lambda r: (SEVERITY_ORDER.get(r.severity, 9), r.check_id)):
        if args.summary and r.ok:
            continue
        print(r)

    print()
    if failures == 0:
        print("AUDIT: PASS - production readiness checks clear"); sys.exit(0)
    else:
        sev = [r.severity for r in results if not r.ok]
        print(
            f"AUDIT: FAIL - {failures} check(s) failed "
            f"({sev.count('CRITICAL')} CRITICAL, {sev.count('HIGH')} HIGH)"
        ); sys.exit(1)


if __name__ == "__main__":
    main()
