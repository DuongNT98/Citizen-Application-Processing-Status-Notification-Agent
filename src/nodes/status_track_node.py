"""AgentCore Platform v1.0 - GOV-C2-013 StatusTrackNode (inner subgraph, step 4).

Lifecycle status tracking + threshold-based SLA-breach detection. Also
folds in the eligibility outcome so a rejected application surfaces as
"rejected" rather than a generic under-review status.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import track_status


class StatusTrackNode(FunctionNode):
    """Track lifecycle status; threshold SLA-breach detection."""

    # S-1: inner subgraph node - trust authenticated at outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        app = from_json(state.get("user_input"), None)
        eligibility = from_json(state.get("eligibility_decision"), None)
        if not isinstance(app, dict) or not isinstance(eligibility, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["StatusTrackNode: missing application or eligibility decision"],
            }

        elapsed_hours = float(app.get("elapsed_hours", 0.0))
        result = track_status(app.get("procedure_type", ""), elapsed_hours)

        if not eligibility.get("eligible", True):
            result["lifecycle_status"] = "rejected"

        emit_trace_event(
            "status_tracked",
            {"lifecycle_status": result["lifecycle_status"], "sla_breach": result["sla_breach"]},
            state,
        )

        return {
            "status_track_result": to_json(result),
            "status": AgentStatus.SUCCESS.value,
        }
