#!/usr/bin/env python3
"""Validate a TealTiger conformance suite against the case validity rules.

    python tools/lint_corpus.py suites/tool-allowlist.v0.1.json
    python tools/lint_corpus.py suites/*.json --registry path/to/teec.reason_codes.yaml

A defective case produces a misleading result rather than no result, so suites
are linted before they are ever run. 18 of the 69 cases in the corpus this
replaced would fail these checks.

Exit status is 0 only if every applicable rule passes. CV-5 needs the
reason-code registry; without it CV-5 is reported as SKIPPED, never as passed.
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import re
import sys
from typing import Optional


def load_registry(path: Optional[str]) -> Optional[set]:
    """Extract reason codes from a TEEC reason-codes YAML registry."""
    if not path:
        return None
    text = io.open(path, encoding="utf-8").read()
    codes = set(re.findall(r"^\s*-\s*code:\s*([A-Z][A-Z0-9_]+)", text, re.M))
    return codes or None


def lint(suite_path: str, registry: Optional[set]) -> int:
    suite = json.loads(io.open(suite_path, encoding="utf-8").read())
    tests = suite.get("tests", [])
    errors = []
    notes = []

    def err(tid, cv, msg):
        errors.append("[{}] {}: {}".format(cv, tid, msg))

    seen_ids = set()

    for t in tests:
        tid = t.get("test_id", "<missing test_id>")
        if tid in seen_ids:
            err(tid, "CV-1", "duplicate test_id")
        seen_ids.add(tid)

        targets = t.get("targets")
        if not targets:
            err(tid, "CV-1", "no `targets` declared")

        exp = t.get("expected", {})

        # CV-2 — a verdict produced by any other clause must fail the case.
        tc = exp.get("triggering_clause")
        if tc is None:
            err(tid, "CV-2", "does not assert expected.triggering_clause")
        elif tc != targets:
            err(tid, "CV-2", "targets={!r} but asserts triggering_clause={!r}".format(targets, tc))

        # CV-3 — a case must satisfy the preconditions of the clause it targets.
        req = t.get("input", {}).get("request", {})
        if isinstance(targets, str):
            if targets.startswith("tools.") and not req.get("tool"):
                err(tid, "CV-3", "targets a tools clause but the request names no tool")
            if targets.startswith("codeExecution.") and not req.get("code"):
                err(tid, "CV-3", "targets a codeExecution clause but the request carries no code")

        # CV-4 — a DENY must be produced by a clause the attached policy expresses.
        if exp.get("decision_action") == "DENY" and isinstance(targets, str):
            pol_tools = (t.get("policy") or {}).get("tools")
            m = re.match(r"^tools\.(.+)\.(allowed|absent)$", targets)
            if m:
                name, kind = m.group(1), m.group(2)
                if pol_tools is None:
                    err(tid, "CV-4", "expects a tools denial but the policy has no tools section")
                elif kind == "allowed":
                    entry = pol_tools.get(name)
                    if entry is None:
                        err(tid, "CV-4", "expects tools.{}.allowed but no such entry exists".format(name))
                    elif entry.get("allowed") is not False:
                        err(tid, "CV-4", "expects tools.{}.allowed to deny but it is not allowed:false".format(name))
                else:
                    if name in pol_tools:
                        err(tid, "CV-4", "expects tools.{}.absent but the policy declares it".format(name))
                    wildcard = pol_tools.get("*")
                    if wildcard is not None and wildcard.get("allowed") is not False:
                        err(tid, "CV-4", "expects an absent-deny but a permitting '*' fallback exists")
            elif not targets.startswith("request."):
                notes.append("{}: DENY targets {!r}, not machine-checkable by CV-4".format(tid, targets))

        # CV-5 — no reason code outside the registry. Requires the registry.
        if registry is not None:
            codes = (exp.get("reason_codes") or []) + (exp.get("reason_codes_absent") or [])
            for c in codes:
                if c not in registry:
                    err(tid, "CV-5", "reason code {} is not in the supplied registry".format(c))

        # CV-6 — must not assert an unspecified property.
        for k in exp:
            if "risk" in k.lower():
                err(tid, "CV-6", "asserts {}, but risk_score is unspecified".format(k))

    # CV-7 — falsifiability, checked mechanically rather than taken on trust.
    actions = [t.get("expected", {}).get("decision_action") for t in tests]
    total = len(tests)
    allow_passes = sum(1 for a in actions if a == "ALLOW")
    deny_passes = sum(1 for a in actions if a == "DENY")
    deny_clauses = set(
        t.get("targets") for t in tests if t.get("expected", {}).get("decision_action") == "DENY"
    )

    print("suite   : {}".format(suite.get("suite_id", suite_path)))
    print("spec    : {}".format(suite.get("spec_version", "unstated")))
    print("cases   : {}".format(total))
    print("clauses : {} distinct".format(len(set(t.get("targets") for t in tests))))
    print("")
    print("CV-7 falsifiability")
    print("  always-ALLOW engine passes {}/{}".format(allow_passes, total))
    print("  always-DENY  engine passes {}/{}".format(deny_passes, total))
    print("  distinct denying clauses   {}".format(len(deny_clauses)))
    if total and (allow_passes == total or deny_passes == total):
        errors.append("[CV-7] the suite is satisfiable by a constant function")
    elif total and (allow_passes == 0 or deny_passes == 0):
        errors.append("[CV-7] the suite tests only one verdict direction")
    if len(deny_clauses) < 2:
        errors.append("[CV-7] all denials assert the same clause; a mechanism error could not be detected")

    print("")
    if registry is None:
        print("CV-5    : SKIPPED - no registry supplied, so reason codes were not")
        print("          validated. Pass --registry to enable. This is not a pass.")
        print("")

    if notes:
        print("notes:")
        for n in notes:
            print("  - {}".format(n))
        print("")

    if errors:
        print("FAILED - {} violation(s):".format(len(errors)))
        for e in errors:
            print("  x {}".format(e))
        return 1

    suffix = "" if registry is not None else " (CV-5 skipped)"
    print("OK - {} cases pass CV-1..CV-7{}".format(total, suffix))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate TealTiger conformance suites against CV-1..CV-7."
    )
    ap.add_argument("suites", nargs="+", help="suite JSON file(s); globs accepted")
    ap.add_argument("--registry", help="TEEC reason-codes YAML; enables CV-5")
    args = ap.parse_args()

    registry = load_registry(args.registry)
    if args.registry and registry is None:
        print("error: no reason codes found in {}".format(args.registry), file=sys.stderr)
        return 2

    paths = []
    for s in args.suites:
        expanded = sorted(glob.glob(s))
        paths.extend(expanded if expanded else [s])

    rc = 0
    for i, p in enumerate(paths):
        if i:
            print("\n" + "-" * 68 + "\n")
        rc = lint(p, registry) or rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
