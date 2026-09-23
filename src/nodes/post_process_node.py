"""AgentCore Platform v1.0 - GOV-C2-013 WorkloadReportNode (outer post_process slot).

Assemble the department workload report (S-3 aggregate-only). Deterministic
narrative is the baseline; an Azure OpenAI client, resolved fresh per
invocation from config/agent.yaml's declared secrets, enhances it when
reachable. Any LLM failure (missing secret, API error, empty/malformed
response) degrades silently back to the deterministic narrative - a
department workload report must always be produced, so an LLM outage is not
a pipeline failure here (contrast the S-3 applicant-identifier re-check
below, which is a real, non-suppressible boundary: on that failure the
output IS dropped entirely, status=ERROR).
"""

import json
import logging
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from shared.services.llm.azure_openai_client import AzureOpenAIClient
from shared.utils.audit_logger import emit_trace_event

from src.schemas.state import from_json, to_json
from src.services.service import (
    assemble_workload_report,
    build_llm_messages,
    extract_llm_text,
    generate_workload_narrative_fallback,
)

logger = logging.getLogger(__name__)

# Applicant-identifying keys that must never appear in the workload report -
# same 番号法 boundary applied at the output edge, plus general PII markers.
DISALLOWED_REPORT_KEYS = ("my_number", "mynumber", "個人番号", "applicant_name", "applicant_id")


class WorkloadReportNode(FunctionNode):
    """Generate department workload report (S-3 aggregate-only); LLM-enhanced narrative."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        # Test-double seam only - production wiring (graph.py register_nodes())
        # never passes this. See _resolve_llm().
        self._llm = llm

    def _resolve_llm(self, state: dict[str, Any]) -> Any:
        """Constructor-injected client wins (test double); otherwise build a
        fresh AzureOpenAIClient per invocation from ctx.secrets. Never cached
        on self - this node instance is reused across callers via the
        registry's node cache, so a cached client would leak one caller's
        credentials to the next. Any failure here (missing secret, no
        InvocationContext-shaped state, ...) means no LLM is available this
        call - the caller (execute()) falls back to the deterministic
        narrative rather than erroring.
        """
        if self._llm is not None:
            return self._llm
        try:
            ctx = InvocationContext.from_state(state)
            return AzureOpenAIClient(
                {
                    "api_key": ctx.secrets.require("AZURE_OPENAI_API_KEY"),
                    "azure_endpoint": ctx.secrets.require("AZURE_OPENAI_ENDPOINT"),
                    "azure_deployment": ctx.secrets.require("AZURE_OPENAI_DEPLOYMENT"),
                }
            )
        except Exception:
            return None

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value):
            return {"status": AgentStatus.ERROR.value}

        routing = from_json(state.get("routing_decision"), None)
        status_track = from_json(state.get("status_track_result"), None)
        if not isinstance(routing, dict) or not isinstance(status_track, dict):
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["WorkloadReportNode: missing routing or status-track result"],
            }

        department = routing["department"]
        lifecycle_status = status_track["lifecycle_status"]
        sla_breach = status_track["sla_breach"]

        # Deterministic narrative is always the baseline. An LLM, when resolved
        # and reachable, enhances it - any failure (missing secret, API error,
        # empty/malformed response) degrades silently back to this baseline.
        # A workload report must always be produced; an LLM outage is not a
        # pipeline failure.
        narrative = generate_workload_narrative_fallback(department, lifecycle_status, sla_breach)
        llm = self._resolve_llm(state)
        if llm is not None:
            prompt = (
                f"Given a municipal department '{department}' with an application currently "
                f"'{lifecycle_status}' (SLA breach: {sla_breach}), write a one-sentence workload "
                f"summary for a municipal IT director."
            )
            try:
                llm_narrative = extract_llm_text(llm.complete(build_llm_messages(prompt))).strip()
                if llm_narrative:
                    narrative = llm_narrative
                else:
                    logger.warning(
                        "WorkloadReportNode: LLM returned empty content, using deterministic "
                        "fallback (correlation_id=%s)",
                        state.get("correlation_id"),
                    )
                    emit_trace_event("workload_narrative_llm_failed", {"reason": "empty_content"}, state)
            except Exception as exc:
                logger.warning(
                    "WorkloadReportNode: LLM completion failed, using deterministic fallback "
                    "(correlation_id=%s): %s",
                    state.get("correlation_id"),
                    exc,
                )
                emit_trace_event("workload_narrative_llm_failed", {"reason": str(type(exc).__name__)}, state)

        report = assemble_workload_report(department, lifecycle_status, sla_breach, narrative)

        emit_trace_event(
            "workload_report_generated",
            {"department": department, "correlation_id": state.get("correlation_id", "")},
            state,
        )

        return {
            "workload_report": to_json(report),
            "formatted_output": report,
            "result": to_json(report),
            "status": AgentStatus.SUCCESS.value,
        }

    def _extra_security_gate_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Non-suppressible re-check: no applicant-identifying key anywhere in the report (own-dict fields only)."""
        report = from_json(state.get("result"), None)
        if not isinstance(report, dict):
            return state

        report_text = json.dumps(report, ensure_ascii=False)
        for key in DISALLOWED_REPORT_KEYS:
            if key in report_text:
                emit_trace_event("output_gate_applicant_identifier_blocked", {}, state)
                return {
                    "status": AgentStatus.ERROR.value,
                    "error_log": [
                        f"Output gate: applicant-identifying key '{key}' detected in workload report - blocked"
                    ],
                }

        return state
