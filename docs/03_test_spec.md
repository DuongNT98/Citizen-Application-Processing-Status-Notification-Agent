# Test Specification

## Test Strategy
- Coverage target: every node ≥1 success + ≥1 error/edge; full graph ≥1 integration compile+invoke
- Test types: Unit (`tests/unit/`), Integration (`tests/integration/`), Proof-of-Boundary (`tests/proof_of_boundary/`)

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict | Type check pass, no Pydantic/dataclass | Pass |
| TC-02 | Fail-closed validation on invalid input | ERROR dict returned, no raise | Pass |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations (S-5 enforcement moved to CI) | Pass |
| TC-04 | InvocationContext via configurable only | Direct access raises error | Pass |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start` / `node_complete` / `node_error` absent from `execute()` body | 0 duplicates |
| TC-06 | S-2: `_security_gate_input()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-07 | S-3: `_security_gate_output()` not overridden (`FunctionNode` subclass) | `TypeError` raised at class definition if overridden (`@final` enforced by framework) | 0 overrides |
| TC-08 | `required_trust_level` enforced | Insufficient trust → refused | Pass |
| TC-09 | S-2: `_extra_security_gate_input()` non-trivial when domain checks needed | N/A — 番号法/completeness/eligibility validation done fail-closed inside `execute()`, not the input-gate hook | N/A |
| TC-10 | S-3: `_extra_security_gate_output()` non-trivial when domain checks needed | `CitizenNotifyNode` (status-token-only re-check) and `WorkloadReportNode` (no applicant-identifier re-check) | Hook body non-trivial |
| TC-11 | S-4: at least one domain `emit_trace_event()` inside each `execute()` | Domain event emitted on every invocation path | ≥1 per node |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → EventEmitter | `emit_trace_event()` fires on every invocation path | No silent failures | Pass |
| PB-2 | State serialization | Post-invoke State is primitives only | No Pydantic/dataclass | Pass |
| PB-3 | Level 2 → External service | マイナポータル/LGWAN integration — deferred to production deployment (long-lead prerequisite, proposal §12) | N/A at scaffold/impl stage | N/A |
| PB-4 | Import isolation | No Level 0 imports | AST scan: 0 violations | Pass |
| PB-5 | Checkpoint safety | No JWT/Pydantic in checkpoint | Inspection pass | Pass |
| PB-6 | Invoke execution order | `__call__()`: S-1 trust gate → S-4 `node_start` → S-2 `_security_gate_input` → `execute()` → S-3 `_security_gate_output` → S-4 `node_complete` | Order verified for every `src/nodes/` node | Pass |
| PB-7 | HITL interrupt propagation | `hitl.enabled` not set — stub auto-skips (no HITL in this template) | Auto-skip | Skip (N/A) |

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | 番号法 boundary enforcement | Application carrying a `my_number` key | `ApplicationIngestNode` rejects with ERROR (non-suppressible) | Pass |
| BL-02 | Document completeness | Application missing a required document for its procedure type | `DocCompletenessCheckNode` returns ERROR with `missing_documents` | Pass |
| BL-03 | Deterministic eligibility | Applicant not a current resident applying for 転出届 | `EligibilityCheckNode` returns `eligible: false` as a SUCCESS business outcome (pipeline continues) | Pass |
| BL-04 | SLA-breach detection | `elapsed_hours` exceeds the procedure's SLA deadline | `StatusTrackNode` sets `sla_breach: true` | Pass |
| BL-05 | Citizen notification payload scope | Notification result assembled | `CitizenNotifyNode` output carries only `channel`/`status_token`/`sent` (S-3 re-check) | Pass |
| BL-06 | Workload report — no applicant identifier | Workload report assembled | `WorkloadReportNode` output never carries an applicant-identifying key (S-3 re-check) | Pass |
| BL-07 | LLM narrative used when resolved | Constructor-injected fake LLM returns a canonical `{"content": ...}` dict | `WorkloadReportNode` narrative is the LLM's text | Pass |
| BL-08 | LLM raising falls back to deterministic narrative | Constructor-injected fake LLM raises on `.complete()` | `WorkloadReportNode` still returns SUCCESS with the deterministic narrative, no `status=error` | Pass |
| BL-09 | LLM empty response falls back to deterministic narrative | Constructor-injected fake LLM returns empty `content` | `WorkloadReportNode` still returns SUCCESS with the deterministic narrative | Pass |
| BL-10 | No LLM configured / no secrets bound | No `llm=` injected, no `SecretProvider` bound (the real production shape absent Azure OpenAI secrets) | `WorkloadReportNode` returns SUCCESS with the deterministic narrative | Pass |
| BL-11 | `_resolve_llm()` on a bare state does not raise | `WorkloadReportNode()._resolve_llm({})` (no lifecycle identity fields — the PB-6 discovery shape) | Returns `None`, no exception | Pass |

## Test Execution Summary
- Execution date: 2026-07-12 (local verify pre-push; CI `run-tests` gate is the record-of-truth)
- Total tests: see `pytest tests/ -v` output in the MR pipeline
- Pass: / Fail: / Skip: PB-7 skip expected (HITL not enabled), PB-5 skip expected (checkpointing not enabled)
- Coverage: framework compliance (TC-01..11), proof-of-boundary (PB-1..7), and business-logic (BL-01..11) all covered
