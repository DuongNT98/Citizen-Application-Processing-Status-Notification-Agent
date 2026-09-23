# GOV-C2-013 - Unit tests: per-node success + error/edge paths.

from framework.schemas.agent_status import AgentStatus

from src.nodes.citizen_notify_node import CitizenNotifyNode
from src.nodes.dept_route_node import DeptRouteNode
from src.nodes.doc_completeness_check_node import DocCompletenessCheckNode
from src.nodes.eligibility_check_node import EligibilityCheckNode
from src.nodes.post_process_node import WorkloadReportNode
from src.nodes.pre_process_node import ApplicationIngestNode
from src.nodes.status_track_node import StatusTrackNode
from src.schemas.state import from_json, to_json

class DictLLM:
    """Canonical fake: complete(messages: list) -> {"content": str, ...}."""

    def __init__(self, content: str):
        self._content = content
        self.last_messages = None

    def complete(self, messages):
        self.last_messages = messages
        return {"content": self._content, "tool_calls": [], "model": "fake", "usage": {}}


class StringLLM:
    """Legacy fake that returns a bare string (backward-compat path)."""

    def __init__(self, content: str):
        self._content = content

    def complete(self, messages):
        return self._content


class RaisingLLM:
    """Configured LLM whose provider call fails - must fall back to the deterministic narrative."""

    def complete(self, messages):
        raise RuntimeError("provider timeout")


class EmptyLLM:
    """Configured LLM returning empty content - must fall back to the deterministic narrative."""

    def complete(self, messages):
        return {"content": "", "tool_calls": [], "model": "fake", "usage": {}}


VALID_APP = {
    "procedure_type": "転出届",
    "documents": ["identity_proof", "current_address_proof"],
    "applicant_age": 35,
    "is_current_resident": True,
    "elapsed_hours": 10.0,
}
INCOMPLETE_APP = {"procedure_type": "転出届", "documents": ["identity_proof"], "applicant_age": 35, "is_current_resident": True}
INELIGIBLE_APP = {"procedure_type": "転出届", "documents": ["identity_proof", "current_address_proof"], "applicant_age": 35, "is_current_resident": False}
MY_NUMBER_APP = {"procedure_type": "住民票", "documents": ["identity_proof"], "my_number": "123456789012"}


class TestApplicationIngestNode:
    def test_success(self):
        r = ApplicationIngestNode().execute({"user_input": to_json(VALID_APP)})
        assert r["status"] == AgentStatus.SUCCESS
        assert from_json(r["application_data"], {})["procedure_type"] == "転出届"

    def test_invalid_json_error(self):
        assert ApplicationIngestNode().execute({"user_input": "not json"})["status"] == AgentStatus.ERROR

    def test_missing_procedure_type_error(self):
        assert ApplicationIngestNode().execute({"user_input": to_json({"documents": []})})["status"] == AgentStatus.ERROR

    def test_my_number_boundary_violation_rejected(self):
        assert ApplicationIngestNode().execute({"user_input": to_json(MY_NUMBER_APP)})["status"] == AgentStatus.ERROR


class TestDocCompletenessCheckNode:
    def test_success(self):
        state = {"user_input": to_json(VALID_APP)}
        r = DocCompletenessCheckNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert from_json(r["doc_completeness_result"], {})["complete"] is True

    def test_missing_documents_error(self):
        state = {"user_input": to_json(INCOMPLETE_APP)}
        r = DocCompletenessCheckNode().execute(state)
        assert r["status"] == AgentStatus.ERROR

    def test_my_number_rechecked_and_rejected(self):
        state = {"user_input": to_json(MY_NUMBER_APP)}
        assert DocCompletenessCheckNode().execute(state)["status"] == AgentStatus.ERROR

    def test_missing_input_error(self):
        assert DocCompletenessCheckNode().execute({"user_input": None})["status"] == AgentStatus.ERROR


class TestEligibilityCheckNode:
    def test_eligible_success(self):
        state = {
            "user_input": to_json(VALID_APP),
            "doc_completeness_result": to_json({"complete": True, "missing_documents": []}),
        }
        r = EligibilityCheckNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        assert from_json(r["eligibility_decision"], {})["eligible"] is True

    def test_ineligible_is_still_success(self):
        """An ineligible decision is a business outcome, not a system error."""
        state = {
            "user_input": to_json(INELIGIBLE_APP),
            "doc_completeness_result": to_json({"complete": True, "missing_documents": []}),
        }
        r = EligibilityCheckNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        decision = from_json(r["eligibility_decision"], {})
        assert decision["eligible"] is False
        assert decision["reasons"]

    def test_incomplete_docs_not_evaluated(self):
        state = {
            "user_input": to_json(VALID_APP),
            "doc_completeness_result": to_json({"complete": False, "missing_documents": ["x"]}),
        }
        assert EligibilityCheckNode().execute(state)["status"] == AgentStatus.ERROR

    def test_missing_inputs_error(self):
        assert EligibilityCheckNode().execute({"user_input": None, "doc_completeness_result": None})["status"] == AgentStatus.ERROR


class TestDeptRouteNode:
    def test_success(self):
        r = DeptRouteNode().execute({"user_input": to_json(VALID_APP)})
        assert r["status"] == AgentStatus.SUCCESS
        assert from_json(r["routing_decision"], {})["department"] == "市民課"

    def test_missing_application_error(self):
        assert DeptRouteNode().execute({"user_input": None})["status"] == AgentStatus.ERROR


class TestStatusTrackNode:
    def test_success_under_sla(self):
        state = {
            "user_input": to_json(VALID_APP),
            "eligibility_decision": to_json({"eligible": True, "reasons": []}),
        }
        r = StatusTrackNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        result = from_json(r["status_track_result"], {})
        assert result["lifecycle_status"] == "under_review"
        assert result["sla_breach"] is False

    def test_sla_breach_detected(self):
        breached_app = {**VALID_APP, "elapsed_hours": 200.0}
        state = {
            "user_input": to_json(breached_app),
            "eligibility_decision": to_json({"eligible": True, "reasons": []}),
        }
        r = StatusTrackNode().execute(state)
        result = from_json(r["status_track_result"], {})
        assert result["sla_breach"] is True

    def test_rejected_status_when_ineligible(self):
        state = {
            "user_input": to_json(VALID_APP),
            "eligibility_decision": to_json({"eligible": False, "reasons": ["not resident"]}),
        }
        r = StatusTrackNode().execute(state)
        result = from_json(r["status_track_result"], {})
        assert result["lifecycle_status"] == "rejected"

    def test_missing_inputs_error(self):
        assert StatusTrackNode().execute({"user_input": None, "eligibility_decision": None})["status"] == AgentStatus.ERROR


class TestCitizenNotifyNode:
    def test_success(self):
        state = {
            "routing_decision": to_json({"department": "市民課", "routed_at": "2026-01-01T00:00:00+00:00"}),
            "status_track_result": to_json({"lifecycle_status": "under_review", "sla_breach": False, "sla_deadline_hours": 72.0}),
        }
        r = CitizenNotifyNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        notification = from_json(r["notification_result"], {})
        assert notification["status_token"] == "市民課:under_review"

    def test_missing_inputs_error(self):
        assert CitizenNotifyNode().execute({"routing_decision": None, "status_track_result": None})["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_payload_overreach(self):
        bad = to_json({"channel": "line", "status_token": "x", "sent": True, "applicant_name": "leak"})
        out = CitizenNotifyNode()._extra_security_gate_output({"notification_result": bad})
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_passthrough_clean_payload(self):
        good = to_json({"channel": "line", "status_token": "x", "sent": True})
        state = {"notification_result": good}
        assert CitizenNotifyNode()._extra_security_gate_output(state) is state


class TestWorkloadReportNode:
    def test_success(self):
        state = {
            "routing_decision": to_json({"department": "市民課", "routed_at": "2026-01-01T00:00:00+00:00"}),
            "status_track_result": to_json({"lifecycle_status": "under_review", "sla_breach": False, "sla_deadline_hours": 72.0}),
        }
        r = WorkloadReportNode().execute(state)
        assert r["status"] == AgentStatus.SUCCESS
        report = from_json(r["workload_report"], {})
        assert report["department"] == "市民課"

    def test_upstream_error_short_circuits(self):
        assert WorkloadReportNode().execute({"status": AgentStatus.ERROR})["status"] == AgentStatus.ERROR

    def test_missing_inputs_error(self):
        assert WorkloadReportNode().execute({"routing_decision": None, "status_track_result": None})["status"] == AgentStatus.ERROR

    def test_extra_gate_blocks_applicant_identifier(self):
        bad = to_json({"department": "市民課", "aggregate_counts": {}, "narrative": "ok", "applicant_name": "leak"})
        out = WorkloadReportNode()._extra_security_gate_output({"result": bad})
        assert out["status"] == AgentStatus.ERROR

    def test_extra_gate_passthrough_clean_report(self):
        good = to_json({"department": "市民課", "aggregate_counts": {"applications_in_scope": 1}, "narrative": "ok"})
        state = {"result": good}
        assert WorkloadReportNode()._extra_security_gate_output(state) is state

    def _state(self):
        return {
            "routing_decision": to_json({"department": "市民課", "routed_at": "2026-01-01T00:00:00+00:00"}),
            "status_track_result": to_json({"lifecycle_status": "under_review", "sla_breach": False, "sla_deadline_hours": 72.0}),
        }

    def test_llm_narrative_used_from_canonical_dict(self):
        r = WorkloadReportNode(llm=DictLLM("Workload is steady.")).execute(self._state())
        assert r["status"] == AgentStatus.SUCCESS.value
        assert from_json(r["workload_report"], {})["narrative"] == "Workload is steady."

    def test_llm_receives_canonical_message_list(self):
        llm = DictLLM("ok")
        WorkloadReportNode(llm=llm).execute(self._state())
        assert isinstance(llm.last_messages, list)
        assert llm.last_messages[0]["role"] == "user"

    def test_llm_string_response_still_accepted(self):
        r = WorkloadReportNode(llm=StringLLM("legacy narrative")).execute(self._state())
        assert from_json(r["workload_report"], {})["narrative"] == "legacy narrative"

    def test_configured_llm_raising_falls_back_to_deterministic_narrative(self):
        r = WorkloadReportNode(llm=RaisingLLM()).execute(self._state())
        assert r["status"] == AgentStatus.SUCCESS.value
        assert from_json(r["workload_report"], {})["narrative"]

    def test_configured_llm_empty_content_falls_back_to_deterministic_narrative(self):
        r = WorkloadReportNode(llm=EmptyLLM()).execute(self._state())
        assert r["status"] == AgentStatus.SUCCESS.value
        assert from_json(r["workload_report"], {})["narrative"]

    def test_no_llm_configured_uses_deterministic_fallback(self):
        # Deterministic fallback is the baseline: no LLM injected, no
        # InvocationContext-shaped state, so _resolve_llm() has nothing to
        # resolve. Failure is not the point here (that's the two tests
        # above) - this is the ordinary, expected no-LLM-configured shape.
        r = WorkloadReportNode(llm=None).execute(self._state())
        assert r["status"] == AgentStatus.SUCCESS.value
        assert from_json(r["workload_report"], {})["narrative"]

    def test_production_shape_no_secrets_bound_falls_back_to_deterministic(self):
        # Real production shape: no llm= injected at all (register_nodes()
        # never passes one) and no SecretProvider bound in this state - the
        # exact case an environment without Azure OpenAI secrets provisioned
        # hits. Must still succeed with the deterministic narrative, not error.
        r = WorkloadReportNode().execute(self._state())
        assert r["status"] == AgentStatus.SUCCESS.value
        assert from_json(r["workload_report"], {})["narrative"]

    def test_resolve_llm_returns_none_on_bare_state_without_raising(self):
        # PB-6's generic node-discovery fixture calls execute() with a bare
        # state (no session_id/thread_id/trace_id) - InvocationContext.from_state()
        # indexes those and would KeyError; _resolve_llm() must swallow that
        # and return None rather than letting it escape.
        assert WorkloadReportNode()._resolve_llm({}) is None
