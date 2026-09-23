"""AgentCore Platform v1.0 - GOV-C2-013 EligibilityCheckNode (inner subgraph, step 2).

Deterministic per-procedure eligibility rule evaluation. Deliberately no LLM -
eligibility decisions must be auditable.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import check_eligibility


class EligibilityCheckNode(FunctionNode):
    """Evaluate per-procedure rule YAML deterministically (no LLM for eligibility)."""

    # S-1: inner subgraph node - trust authenticated at outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        app = from_json(state.get("user_input"), None)
        completeness = from_json(state.get("doc_completeness_result"), None)
        if not isinstance(app, dict) or not isinstance(completeness, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["EligibilityCheckNode: missing application or completeness result"],
            }

        if not completeness.get("complete", False):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["EligibilityCheckNode: incomplete documents - not evaluated"],
            }

        decision = check_eligibility(app)

        emit_trace_event(
            "eligibility_checked",
            {"eligible": decision["eligible"], "reason_count": len(decision["reasons"])},
            state,
        )

        # NOTE: an ineligible decision is a valid business outcome, not a
        # system error - the pipeline continues so DeptRoute/StatusTrack/
        # CitizenNotify can still route, track, and notify the citizen of the
        # rejection (rather than silently dropping the application).
        return {
            "eligibility_decision": to_json(decision),
            "status": AgentStatus.SUCCESS.value,
        }
