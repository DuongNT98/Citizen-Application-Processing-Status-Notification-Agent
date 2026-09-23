"""AgentCore Platform v1.0 - GOV-C2-013 DeptRouteNode (inner subgraph, step 3).

Deterministic department routing. Records routing + timestamp for downstream
SLA tracking. Routes both eligible and ineligible applications - the
receiving department also owns rejection follow-up.
"""

from datetime import datetime, timezone
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import route_department


class DeptRouteNode(FunctionNode):
    """Route application to appropriate municipal department; record for SLA."""

    # S-1: inner subgraph node - trust authenticated at outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        app = from_json(state.get("user_input"), None)
        if not isinstance(app, dict) or not app.get("procedure_type"):
            return {"status": AgentStatus.ERROR.value, "error_log": ["DeptRouteNode: missing application"]}

        routed_at = datetime.now(timezone.utc).isoformat()
        routing = route_department(app.get("procedure_type", ""), routed_at)

        emit_trace_event(
            "application_routed",
            {"department": routing["department"], "correlation_id": state.get("correlation_id", "")},
            state,
        )

        return {
            "routing_decision": to_json(routing),
            "status": AgentStatus.SUCCESS.value,
        }
