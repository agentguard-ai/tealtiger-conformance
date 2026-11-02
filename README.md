# TealTiger Conformance Corpus

A language-neutral suite of cases that defines what a TealTiger policy decision
must be, independently of any implementation.

Each case is a `(policy, request, expected decision)` triple in flat JSON. Any
implementation — the TypeScript SDK, the Python SDK, or anything else that
claims to evaluate TealTiger policy — can be run against the same cases and
scored by the same rules.

---

## Current conformance status

**This corpus covers one rule type. Read the table before drawing conclusions
from it.**

| Rule type | Specified | TypeScript | Python |
|---|---|---|---|
| Tool allowlist (TA-1 – TA-7) | yes | **16/16** (unmerged branch) | **0/16** |
| PII | no | not implemented | not implemented |
| Prompt injection | no | not implemented | not implemented |
| Code execution | no | unvalidated | not implemented |
| Cost and budget | no | partial | not implemented |
| Rate limiting | no | not implemented | not implemented |
| Memory governance | no | TypeScript only | absent |
| Secrets, provenance, supply chain | no | TypeScript only | absent |

Stated plainly, because a conformance repository that implies more coverage
than it has is worse than none:

- **One rule type of eight is specified and covered.** The remaining seven are
  blocked on product decisions about what the semantics should be, not on
  engineering.
- **TypeScript passes all 16 cases on a branch that is not yet merged.** No
  released version of either SDK passes this corpus.
- **Python passes none of them.** Its policy engine does not evaluate policy:
  `TealEngine._evaluate_policies()` returns `allowed: true` unconditionally and
  never reads the configured policy.
- **`risk_score` is deliberately not asserted anywhere here.** There is no
  severity model in either implementation, so scoring it would manufacture
  failures that carry no governance meaning.

---

## Why this exists

The two SDKs were each validated against a corpus held inside their own source
tree. Measured in October 2026:

- TypeScript's suite had **69** cases, Python's **25**, and **3** inputs in
  common. Not a superset relationship — two private, near-disjoint sets.
- `ReasonCode` shared **15** members out of 46 and 32.
- Against TypeScript's own 69 cases, TypeScript satisfied **8** and Python
  **9** — with Python scoring *higher while denying nothing at all*, because
  permissiveness happens to satisfy the cases that expect an allow.
- Of 58 cases expecting a denial, exactly **one** passed on merit, in one
  implementation.

A corpus that lives inside one implementation is a corpus that implementation
cannot fail. This one is deliberately external and shared.

---

## Running it

The harness lives with each implementation; this repository holds only the
cases.

**TypeScript**

```bash
git clone https://github.com/agentguard-ai/tealtiger-conformance.git
cd /path/to/tealtiger-typescript
CONFORMANCE_CORPUS=/path/to/tealtiger-conformance/suites/tool-allowlist.v0.1.json \
  npm run conformance
```

A conforming run reports every case passing and exits 0. A harness that cannot
locate the corpus **must fail rather than skip** — a gate that reports green
while checking nothing is the defect this corpus exists to catch.

**Validating the corpus itself**

```bash
python tools/lint_corpus.py suites/tool-allowlist.v0.1.json
```

---

## What a case looks like

```json
{
  "test_id": "ta4-absent-defaults-deny",
  "description": "TA-4: a tool absent from the map is denied.",
  "targets": "tools.unregistered_tool.absent",
  "input": {
    "request": { "agentId": "agent-1", "action": "tool.execute", "tool": "unregistered_tool" },
    "context": { "environment": "prod" }
  },
  "expected": {
    "decision_action": "DENY",
    "reason_codes": ["POLICY_VIOLATION", "TOOL_NOT_ALLOWED"],
    "triggering_clause": "tools.unregistered_tool.absent"
  },
  "policy": { "tools": { "search": { "allowed": true } } },
  "tags": ["ta-4", "default-deny"]
}
```

`targets` and `expected.triggering_clause` are the load-bearing fields.

A correct verdict reached by the wrong mechanism is not correct governance. All
13 cases in the old unsafe-code suite returned the expected `DENY` with the
expected `UNSAFE_CODE_DETECTED` — and all 13 were produced by a language
precondition rather than by inspecting the code, so `eval`, `exec`,
`os.system` and `pickle.loads` detection was never executed once. Two benign
snippets were denied as unsafe. Nothing could detect any of it, because nothing
recorded *which clause decided*.

So every case names the clause it exercises, and a decision must report the
clause that produced it.

---

## Case validity rules

A case that violates any of these is rejected by `tools/lint_corpus.py` before
it is ever run, because a defective case produces a misleading result rather
than no result. 18 of the 69 cases in the original TypeScript suite would fail
these checks.

| | Rule |
|---|---|
| **CV-1** | A case must declare `targets`, the clause it exercises. |
| **CV-2** | A case must assert the decision's `triggering_clause` equals `targets`. A verdict produced by any other clause fails the case. |
| **CV-3** | A case targeting a detection clause must satisfy every precondition of that section. |
| **CV-4** | A case expecting `DENY` must be denied by a clause the attached policy actually expresses. |
| **CV-5** | A case must not assert a reason code outside the target implementation's declared support. |
| **CV-6** | A case must not assert an unspecified property, including `risk_score`. |
| **CV-7** | Every case must be falsifiable. A suite satisfiable by a constant function is not a governance test. |

CV-7 is checked mechanically, not taken on trust. For the current suite an
always-`ALLOW` engine passes 5 of 16 and an always-`DENY` engine 11 of 16, so
neither constant function satisfies it, and 10 distinct denying clauses are
asserted so a mechanism error cannot hide behind a single one.

---

## Versioning

Suites are versioned independently of any SDK. A suite filename carries its
version; the `spec_version` field records which revision of the conformance
specification it was authored against.

Adding cases is a minor change. Changing what an existing case expects is a
breaking change to the standard and requires a specification revision, because
an implementation that was conformant must not silently become non-conformant.

## Licence

Apache-2.0, matching the TealTiger SDKs.
