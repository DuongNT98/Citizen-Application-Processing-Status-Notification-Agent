# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: CitizenApplicationProcessingAgent
- **L1 Base**: AgentBaseGraph (Cat 2 — outer graph; `main` slot wraps an inner `BaseGraph` via `GraphNode`)
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

Cat 2 — outer backbone (fixed 5-node pipeline) + `main` slot wraps an inner subgraph
(`CitizenApplicationWorkflowGraph`) that holds the 5 core domain steps.

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | schema_version, session_id, trust_level | — | — | InitializeNode (default) |
| pre_process | ApplicationIngestNode — receive + validate application, enforce 番号法 boundary | `user_input` | `application_data`, `validated_input` | FunctionNode |
| main | CitizenApplicationGraphNode — wraps inner subgraph (5 steps below) | `validated_input` | `doc_completeness_result`, `eligibility_decision`, `routing_decision`, `status_track_result`, `notification_result` | GraphNode |
| ↳ inner: doc_completeness_check | DocCompletenessCheckNode — required-doc check per procedure | `user_input` (inner) | `doc_completeness_result` | FunctionNode |
| ↳ inner: eligibility_check | EligibilityCheckNode — deterministic per-procedure rule eval (no LLM) | `doc_completeness_result` | `eligibility_decision` | FunctionNode |
| ↳ inner: dept_route | DeptRouteNode — route to municipal department + SLA timestamp | `user_input` (inner) | `routing_decision` | FunctionNode |
| ↳ inner: status_track | StatusTrackNode — lifecycle status + SLA-breach detection | `eligibility_decision` | `status_track_result` | FunctionNode |
| ↳ inner: citizen_notify | CitizenNotifyNode — LINE/マイナポータル notification (S-3 status-token only) | `routing_decision`, `status_track_result` | `notification_result` | FunctionNode |
| post_process | WorkloadReportNode — department workload report (LLM narrative + fallback) | `routing_decision`, `status_track_result` | `workload_report`, `formatted_output` | FunctionNode |
| finalize | response_metadata, total_time_ms | — | — | FinalizeNode (default) |

### Data Flow

```
START → initialize → pre_process(ApplicationIngest) → main(GraphNode) → post_process(WorkloadReport) → finalize → END
                                                              │
                                                              ▼ (inner subgraph, invoked via GraphNode)
                              doc_completeness_check → eligibility_check → dept_route → status_track → citizen_notify
```

Inner pipeline is fail-fast on ERROR (missing/invalid data), **except** `eligibility_check`: an
ineligible decision is a valid business outcome (not a system error) and never short-circuits —
`status_track`/`citizen_notify` still run so the citizen is notified of the rejection.

### State Definition

| Field | Type | Purpose | Required |
|-------|------|---------|----------|
| `application_data` | `NotRequired[str \| None]` (JSON) | Validated application (no マイナンバー) | No |
| `doc_completeness_result` | `NotRequired[str \| None]` (JSON) | `{complete, missing_documents}` | No |
| `eligibility_decision` | `NotRequired[str \| None]` (JSON) | `{eligible, reasons}` | No |
| `routing_decision` | `NotRequired[str \| None]` (JSON) | `{department, routed_at}` | No |
| `status_track_result` | `NotRequired[str \| None]` (JSON) | `{lifecycle_status, sla_breach, sla_deadline_hours}` | No |
| `notification_result` | `NotRequired[str \| None]` (JSON) | `{channel, status_token, sent}` — S-3 status-token only | No |
| `workload_report` | `NotRequired[str \| None]` (JSON) | `{department, aggregate_counts, narrative}` | No |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types)
- No JWT, API keys, credentials in State (checkpoint DB leakage)
- InvocationContext via `config["configurable"]` only (not in State)
- No Pydantic models, dataclass, arbitrary Python objects (msgpack incompatible)
- No マイナンバー ever — 番号法 boundary enforced at `ApplicationIngestNode` (ingest) and
  re-checked at the first inner node (`DocCompletenessCheckNode`, since the outer
  pre_process → main edge is unconditional).

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle)
- [ ] ConnectionPolicy (retry/timeout strategy)
- [ ] SecurityViolationError
- [x] S-2: `_extra_security_gate_input()` — not used; 番号法/completeness validation is
      done inside `execute()` as fail-closed ERROR returns (raise-free), not via the input
      gate hook — matches the "validation raise-able" guidance in the security checklist.
- [x] S-3: `_extra_security_gate_output()` — used on `CitizenNotifyNode` (notification payload
      must carry only `channel`/`status_token`/`sent`) and `WorkloadReportNode` (workload report
      must never carry an applicant-identifying key). Both re-check the node's own output dict.
- [x] S-4: `emit_trace_event()` — at least one domain-specific event inside each `execute()`
      (**mandatory**; do NOT emit `node_start` / `node_complete` / `node_error` —
      `BaseNode.__call__()` emits these automatically; duplicates corrupt audit trail)

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: GraphNode (subgraph) — `CitizenApplicationGraphNode` wraps the inner
  `CitizenApplicationWorkflowGraph` (`BaseGraph`) holding the 5 core domain steps.
- **Composition target**: `src/graph/domain_workflow_graph.py::CitizenApplicationWorkflowGraph`
- **Error propagation strategy**: `propagate` (fail fast — inner ERROR surfaces as outer ERROR
  via `SubgraphError`; no HITL in this template).

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: framework/ and shared/ only (no agents/base/ required)

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Fixed 7-step pipeline, no autonomous loop needed (a Cat 3 autonomous variant is a separate proposal) |
| Composition pattern | Flat 3-slot (Cat 1 style) | GraphNode + inner subgraph (Cat 2) | GraphNode + inner subgraph | Cat 2 requires the 3-layer composition (`gate-composition`); 5 core steps live in the inner subgraph |
| Eligibility check | LLM-based | Deterministic rule YAML (local fallback dict) | Deterministic | Auditable, government-compliance requirement (no LLM in the eligibility decision path) |
| Workload report narrative LLM wiring | Constructor-injected at graph-build time (`register_nodes()`) | Resolved fresh per invocation inside `execute()`, from `ctx.secrets` | Resolved per invocation | Node instances are constructed once and reused across every invocation via the registry's node cache; a client built once at graph-build time (or cached on `self`) would carry one caller's Azure OpenAI credentials into every subsequent invocation. `WorkloadReportNode.__init__(llm=...)` stays as a test-double seam only. |
| Workload report LLM failure mode | Fail-closed (`status=error` on any LLM failure) | Fail-open (silent fallback to the deterministic narrative) | Fail-open | A department workload report is a real deliverable with a valid non-LLM baseline (`generate_workload_narrative_fallback`); an LLM outage must not take down report generation. Contrast the S-3 applicant-identifier re-check on the same node, which stays fail-closed (a real security boundary, not narrative quality). |

## EU AI Act Art.13 Design-Time Evidence (Annex III, Area 5 — In scope, see docs/01)

| Requirement | Evidence |
|---|---|
| Intended purpose and operating context | Determines per-procedure eligibility for citizen administrative applications (住民票, 転出届, 補助金申請) submitted via マイナポータル/web form, for municipal government use in Japan. Output feeds downstream routing/status-tracking/notification; it is not a final, unappealable administrative decision — see human oversight row below. |
| Capabilities and limitations | Deterministic rule-YAML evaluation only (`EligibilityCheckNode`, no LLM/ML in the decision path) against the declared per-procedure rule set; limited to the procedures configured in the rule YAML, requires complete documents (`doc_completeness_result.complete`) before evaluating, and does not assess cases outside its declared rule scope (out-of-scope inputs surface as `ERROR`, not a silent guess). |
| User-facing transparency information | `CitizenNotifyNode` triggers a status notification (LINE/マイナポータル) carrying a lookup `status_token` only (S-3 non-suppressible: no eligibility outcome or applicant content in the payload itself, by design — see §2 above). The human-readable disclosure text presented to the citizen (that the eligibility outcome was automated, plus the routed department and appeal path) is resolved downstream by the LINE/マイナポータル channel keyed on that token — outside this template's implementation scope. **Gap, tracked**: no committed evidence yet that the downstream channel's message copy actually states the determination was automated; owning team for that copy is the municipal digital-service integration, not this template. |
| Human oversight mechanism | An ineligible decision is routed (not silently dropped) to the assigned municipal department via `DeptRouteNode`/`StatusTrackNode` for human case-worker review and possible override before any citizen-facing benefit action is finalized; this template makes no irreversible payment/benefit action itself. |

### WorkloadReportNode LLM wiring (Azure OpenAI)

`config/agent.yaml` declares `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_ENDPOINT` /
`AZURE_OPENAI_DEPLOYMENT` under `requires.secrets` and `openai` under
`requires.extras`. `WorkloadReportNode._resolve_llm()` builds an
`AzureOpenAIClient` fresh on every call from `InvocationContext.from_state(state).secrets`
(never cached on `self`, never built in `register_nodes()`). Any resolution or
completion failure — missing secret, unreachable endpoint, malformed/empty
response — is caught and the node falls back to the deterministic narrative;
`WorkloadReportNode.execute()` never returns `status=error` solely because the
LLM was unavailable. `AZURE_OPENAI_ENDPOINT` must be the bare Azure AI Foundry
resource endpoint (`https://<resource>.services.ai.azure.com`, no `/openai`
path segment) — `AzureOpenAIClient` rejects, rather than rewrites, a value
that already looks like an API path.
