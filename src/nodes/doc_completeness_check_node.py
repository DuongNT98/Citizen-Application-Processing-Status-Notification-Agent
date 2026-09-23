"""AgentCore Platform v1.0 - GOV-C2-013 DocCompletenessCheckNode (inner subgraph, step 1).

Deterministic per-procedure required-document completeness check. Note: since
AgentBaseGraph's pre_process -> main edge is unconditional, an upstream
pre_process ERROR still dispatches into this inner subgraph. The 番号法
boundary and application-shape validation are therefore re-checked here, never
trusting that the upstream rejection alone stopped the pipeline.
"""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import check_doc_completeness, validate_no_my_number


class DocCompletenessCheckNode(FunctionNode):
    """Check required documents present per per-procedure config."""

    # S-1: inner subgraph node - trust authenticated at outer backbone.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.ANONYMOUS

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        app = from_json(state.get("user_input"), None)
        if not isinstance(app, dict) or not app.get("procedure_type"):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["DocCompletenessCheckNode: missing or invalid application"],
            }

        if validate_no_my_number(app):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["DocCompletenessCheckNode: 番号法 boundary violation - not processed"],
            }

        result = check_doc_completeness(app)

        emit_trace_event(
            "doc_completeness_checked",
            {"complete": result["complete"], "missing_count": len(result["missing_documents"])},
            state,
        )

        if not result["complete"]:
            return {
                "doc_completeness_result": to_json(result),
                "status": AgentStatus.ERROR.value,
                "error_log": [f"DocCompletenessCheckNode: missing documents {result['missing_documents']}"],
            }

        return {
            "doc_completeness_result": to_json(result),
            "status": AgentStatus.SUCCESS.value,
        }
