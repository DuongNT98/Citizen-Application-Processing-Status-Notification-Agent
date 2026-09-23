# GOV-C2-013 - Framework compliance tests TC-01..TC-08.
# Reference shape: another released Cat 1 template's framework compliance test suite,
# adapted to this template's real architecture (Cat 2: outer ApplicationIngest pre_process +
# GraphNode-wrapped inner doc-completeness/eligibility/dept-route/status-track/citizen-notify
# nodes + WorkloadReport post_process).

import os
import re

import pytest
from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.nodes import (
    citizen_notify_node,
    dept_route_node,
    doc_completeness_check_node,
    eligibility_check_node,
    post_process_node,
    pre_process_node,
    status_track_node,
)
from src.schemas.state import State, from_json, to_json

_SRC = os.path.join(os.path.dirname(__file__), "..", "..", "src")
TRUST = TrustLevel.VERIFIED_EXTERNAL.value

VALID_APP = {
    "procedure_type": "転出届",
    "documents": ["identity_proof", "current_address_proof"],
    "applicant_age": 35,
    "is_current_resident": True,
    "elapsed_hours": 10.0,
}


def _src_files():
    for root, _d, files in os.walk(_SRC):
        for f in files:
            if f.endswith(".py"):
                yield os.path.join(root, f)


# TC-01 - State is a flat TypedDict extending AgentState; added fields are
# JSON-serializable primitives or JSON-string-encoded compounds (str | None).
class TestTC01StateContract:
    def test_state_is_typeddict_extending_agent_state(self):
        assert hasattr(State, "__annotations__")
        assert "user_input" in State.__annotations__
        assert set(AgentState.__annotations__).issubset(set(State.__annotations__))

    def test_added_fields_are_json_safe(self):
        added = [k for k in State.__annotations__ if k not in AgentState.__annotations__]
        assert added, "State must declare agent-specific fields"
        # Every added field is a primitive or an Optional[str]/str|None JSON-string
        # holder — never a Pydantic model, dataclass, or arbitrary object.
        for name in added:
            ann_str = str(State.__annotations__[name])
            assert ("str" in ann_str or "int" in ann_str or "bool" in ann_str or "float" in ann_str), (
                f"{name}: {ann_str} - compound fields must be JSON-string-encoded"
            )


# TC-02 - Empty/missing/invalid input yields a fail-closed ERROR outcome, no raise.
class TestTC02Validation:
    def test_empty_input_no_raise(self):
        out = pre_process_node.ApplicationIngestNode().execute({"user_input": to_json({})})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]

    def test_invalid_json_no_raise(self):
        out = pre_process_node.ApplicationIngestNode().execute({"user_input": "not json"})
        assert out["status"] == AgentStatus.ERROR
        assert out["error_log"]


# TC-03 - No JWT / API keys / secrets in src/; no direct os.environ reads.
class TestTC03NoCredentials:
    def test_no_credential_literals(self):
        pat = re.compile(r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")
        offenders = [fp for fp in _src_files() if pat.search(open(fp, encoding="utf-8").read())]
        assert offenders == []

    def test_no_os_environ_secret_reads(self):
        # src/api/server.py reads INVOKE_AUTH_TOKEN (a deployment-level caller
        # credential at the entry-point auth boundary, not an agent secret) -
        # this is the documented entry-point exception to the secrets rule.
        offenders = [
            fp
            for fp in _src_files()
            if "os.environ" in open(fp, encoding="utf-8").read() and not fp.replace("\\", "/").endswith("src/api/server.py")
        ]
        assert offenders == []


# TC-04 - InvocationContext is never stored in State after invoke.
class TestTC04ContextIsolation:
    def test_no_invocationcontext_in_state_after_invoke(self):
        from src.graph.graph import Graph

        agent = Graph()
        agent.compile()
        ctx = InvocationContext(session_id="tc04", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="citizen-tc04")
        result = agent.invoke(to_json(VALID_APP), ctx=ctx)
        for v in result.values():
            assert not isinstance(v, InvocationContext)

    def test_from_state_available(self):
        assert hasattr(InvocationContext, "from_state")


# TC-05 - Domain events: the outer nodes emit >=1 domain event; no node under
# src/nodes/ ever re-emits a framework backbone lifecycle event.
class TestTC05Audit:
    def test_pre_process_emits_domain_event(self, monkeypatch):
        events = []
        monkeypatch.setattr(pre_process_node, "emit_trace_event", lambda e, p, s: events.append(e))
        out = pre_process_node.ApplicationIngestNode().execute({"user_input": to_json(VALID_APP)})
        assert out["status"] == AgentStatus.SUCCESS
        assert "application_ingested" in events
        assert not ({"node_start", "node_complete", "node_error", "node_skip"} & set(events))

    def test_source_has_no_backbone_events(self):
        pat = re.compile(r'emit_trace_event\(\s*["\'](node_start|node_complete|node_error|node_skip)["\']')
        offenders = [fp for fp in _src_files() if pat.search(open(fp, encoding="utf-8").read())]
        assert offenders == []


# TC-06 / TC-07 - S-2/S-3 gates are @final on FunctionNode (overriding raises TypeError at class def).
class TestTC0607FinalGates:
    def test_input_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadIn(FunctionNode):  # noqa: N801
                def _security_gate_input(self, state):
                    return state

    def test_output_gate_is_final(self):
        with pytest.raises(TypeError):

            class BadOut(FunctionNode):  # noqa: N801
                def _security_gate_output(self, result):
                    return result

    def test_extra_hook_is_overridable(self):
        assert (
            post_process_node.WorkloadReportNode._extra_security_gate_output
            is not FunctionNode._extra_security_gate_output
        )
        assert (
            citizen_notify_node.CitizenNotifyNode._extra_security_gate_output
            is not FunctionNode._extra_security_gate_output
        )

    def test_output_gate_blocks_credentials(self):
        # The @final S-3 credential scan actually fires (not vacuous): a
        # credential in the result is blocked, never returned as-is.
        node = post_process_node.WorkloadReportNode()
        with pytest.raises(Exception):
            node._security_gate_output({"formatted_output": "token AKIAIOSFODNN7EXAMPLE leaked"})


# TC-08 - required_trust_level declared valid + enforced: insufficient trust -> ERROR, no raise.
class TestTC08TrustGate:
    def test_declared_trust_levels_valid(self):
        for cls in (
            pre_process_node.ApplicationIngestNode,
            doc_completeness_check_node.DocCompletenessCheckNode,
            eligibility_check_node.EligibilityCheckNode,
            dept_route_node.DeptRouteNode,
            status_track_node.StatusTrackNode,
            citizen_notify_node.CitizenNotifyNode,
            post_process_node.WorkloadReportNode,
        ):
            assert cls.required_trust_level in (TrustLevel.ANONYMOUS, TrustLevel.VERIFIED_EXTERNAL, TrustLevel.INTERNAL)

    def test_insufficient_trust_returns_error(self):
        node = pre_process_node.ApplicationIngestNode()
        out = node({"caller_trust_level": TrustLevel.ANONYMOUS.value, "user_input": to_json(VALID_APP)})
        assert str(out.get("status")).lower().endswith("error")

    def test_sufficient_trust_succeeds(self):
        node = pre_process_node.ApplicationIngestNode()
        out = node({"caller_trust_level": TRUST, "user_input": to_json(VALID_APP)})
        assert out["status"] == AgentStatus.SUCCESS
        assert from_json(out["application_data"], None)
