"""AgentCore Platform v1.0 - GOV-C2-013 CitizenNotifyNode (inner subgraph, step 5).

Status notification via LINE official account / マイナポータル. S-3
non-suppressible: the notification payload must carry a status token only -
never applicant PII or document content.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import build_notification


class CitizenNotifyNode(FunctionNode):
    """Send status notification via LINE/マイナポータル; S-3 status-token only."""

    # S-1: inner subgraph node - trust authenticated at outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        routing = from_json(state.get("routing_decision"), None)
        status_track = from_json(state.get("status_track_result"), None)
        if not isinstance(routing, dict) or not isinstance(status_track, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["CitizenNotifyNode: missing routing or status-track result"],
            }

        notification = build_notification(routing["department"], status_track["lifecycle_status"])

        emit_trace_event(
            "citizen_notified",
            {"channel": notification["channel"], "sent": notification["sent"]},
            state,
        )

        return {
            "notification_result": to_json(notification),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Non-suppressible re-check: notification_result must carry a status token only."""
        notification = from_json(state.get("notification_result"), None)
        if not isinstance(notification, dict):
            return state

        allowed_keys = {"channel", "status_token", "sent"}
        if set(notification.keys()) - allowed_keys:
            emit_trace_event("output_gate_notification_payload_overreach_blocked", {}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    "CitizenNotifyNode output gate: notification payload carries fields beyond channel/status_token/sent"
                ],
            }

        return state
