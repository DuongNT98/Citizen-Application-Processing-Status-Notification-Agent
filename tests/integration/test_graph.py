# GOV-C2-013 - Integration test: full graph compile + invoke (Cat 2 outer + inner).

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import Graph
from src.schemas.state import to_json

VALID_APP = to_json(
    {
        "procedure_type": "転出届",
        "documents": ["identity_proof", "current_address_proof"],
        "applicant_age": 35,
        "is_current_resident": True,
        "elapsed_hours": 10.0,
    }
)
INELIGIBLE_APP = to_json(
    {
        "procedure_type": "転出届",
        "documents": ["identity_proof", "current_address_proof"],
        "applicant_age": 35,
        "is_current_resident": False,
        "elapsed_hours": 10.0,
    }
)
MY_NUMBER_APP = to_json({"procedure_type": "住民票", "documents": ["identity_proof"], "my_number": "123456789012"})
EMPTY_APP = to_json({})


class TestAgentIntegration:
    def test_eligible_application_processed(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-1", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="citizen-1")
        result = agent.invoke(VALID_APP, ctx=ctx)

        assert result["status"] == "success"
        assert len(result.get("node_history", [])) >= 5

    def test_ineligible_application_still_notifies(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-2", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="citizen-2")
        result = agent.invoke(INELIGIBLE_APP, ctx=ctx)

        assert result["status"] == "success"

    def test_my_number_boundary_rejected(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-3", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="citizen-3")
        result = agent.invoke(MY_NUMBER_APP, ctx=ctx)
        assert result["status"] in ("error", "cancelled")

    def test_empty_application_error(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-4", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="citizen-4")
        result = agent.invoke(EMPTY_APP, ctx=ctx)
        assert result["status"] in ("error", "cancelled")

    def test_invalid_json_error(self):
        agent = Graph(config={"max_retry": 1})
        agent.compile()
        ctx = InvocationContext(session_id="it-5", caller_trust_level=TrustLevel.VERIFIED_EXTERNAL, caller_id="citizen-5")
        result = agent.invoke("not json", ctx=ctx)
        assert result["status"] in ("error", "cancelled")
