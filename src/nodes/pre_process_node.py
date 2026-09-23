"""AgentCore Platform v1.0 - GOV-C2-013 ApplicationIngestNode (outer pre_process slot).

Receive + validate the citizen application (マイナポータル schema / municipal web
form JSON payload). 番号法 boundary: non-suppressible rejection of any application
carrying a マイナンバー key - マイナポータル manages マイナンバー separately, this
agent never processes it.
"""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import to_json
from src.services.service import extract_audit_safe_topic, validate_no_my_number


class ApplicationIngestNode(FunctionNode):
    """Ingest + validate the citizen application; enforce the 番号法 boundary."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        user_input = state.get("user_input", "")

        try:
            app = json.loads(user_input) if isinstance(user_input, str) else user_input
        except (TypeError, ValueError):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ApplicationIngestNode: user_input is not valid JSON"],
            }

        if not isinstance(app, dict) or not app.get("procedure_type"):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["ApplicationIngestNode: application missing or procedure_type absent"],
            }

        violations = validate_no_my_number(app)
        if violations:
            emit_trace_event("my_number_boundary_violation_blocked", {"violation_count": len(violations)}, state)
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [
                    f"ApplicationIngestNode: 番号法 boundary violation - key '{v}' present" for v in violations
                ],
            }

        emit_trace_event("application_ingested", extract_audit_safe_topic(app.get("procedure_type", "")), state)

        return {
            "application_data": to_json(app),
            "validated_input": to_json(app),
            "status": AgentStatus.SUCCESS.value,
        }
