"""AgentCore Platform v1.0 - GOV-C2-013 outer graph (Cat 2).

Cat 2: outer AgentBaseGraph with the fixed 5-node backbone. Domain complexity
is encapsulated in CitizenApplicationGraphNode (the `main` slot), which wraps
the inner CitizenApplicationWorkflowGraph. Do NOT override add_edges().

Backbone: initialize -> pre_process(ApplicationIngest) -> main(GraphNode)
          -> post_process(WorkloadReport) -> finalize

CitizenApplicationGraphNode lives here (not under src/nodes/) - the PB-6
invoke-order test only discovers BaseNode subclasses under src/nodes/, and a
GraphNode's __call__ intentionally skips the standard S-2/S-4/S-3 lifecycle
(gating is delegated to the inner subgraph).
"""

from typing import Any, ClassVar, cast

from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.nodes.post_process_node import WorkloadReportNode
from src.nodes.pre_process_node import ApplicationIngestNode
from src.schemas.state import State


class CitizenApplicationGraphNode(GraphNode):
    """Wraps the inner citizen-application processing workflow (Cat 2 composition)."""

    # S-1: the outer main-slot wrapper is the first node to receive caller input,
    # so it must enforce the agent-level trust floor from config/agent.yaml
    # (VERIFIED_EXTERNAL) rather than inheriting BaseNode's permissive ANONYMOUS.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    # "propagate": re-raise inner errors as SubgraphError (fail fast - default).
    error_strategy: ClassVar[str] = "propagate"
    # No HITL in this template.
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, llm: Any = None) -> None:
        super().__init__()
        self._llm = llm

    def get_subgraph(self) -> Any:
        from src.graph.domain_workflow_graph import CitizenApplicationWorkflowGraph

        sg = CitizenApplicationWorkflowGraph(config=self._parent_config())
        sg.compile()
        return sg

    def extract_input(self, state: AgentState) -> str:
        emit_trace_event(
            "citizen_application_workflow_dispatched", {"correlation_id": state.get("correlation_id", "")}, state
        )
        return cast(str, state.get("validated_input", state.get("user_input", "")))

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        emit_trace_event(
            "citizen_application_workflow_completed",
            {"correlation_id": state.get("correlation_id", ""), "status": str(sub_result.get("status"))},
            state,
        )
        return {
            "doc_completeness_result": sub_result.get("doc_completeness_result"),
            "eligibility_decision": sub_result.get("eligibility_decision"),
            "routing_decision": sub_result.get("routing_decision"),
            "status_track_result": sub_result.get("status_track_result"),
            "notification_result": sub_result.get("notification_result"),
            "status": sub_result.get("status"),
        }

    def _parent_config(self) -> dict[str, Any]:
        return {"llm": self._llm}


class CitizenApplicationProcessingAgent(AgentBaseGraph):
    """GOV-C2-013 - Citizen Application Processing & Status Notification Agent (Cat 2)."""

    @property
    def name(self) -> str:
        return "gov-c2-013"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize

        # llm is a test-double seam only (see WorkloadReportNode.__init__ /
        # _resolve_llm) — production wiring never passes one. WorkloadReportNode
        # resolves its own Azure OpenAI client per invocation from
        # config/agent.yaml's declared secrets. CitizenApplicationGraphNode's
        # inner subgraph has no LLM-consuming node, so it no longer receives one.
        self._nodes["pre_process"] = ApplicationIngestNode()
        self._nodes["main"] = CitizenApplicationGraphNode()
        self._nodes["post_process"] = WorkloadReportNode()

    # add_edges() is NOT overridden - backbone wiring belongs to the framework.


# Alias for agent.yaml module:"src.graph" resolution (AgentRegistry / api/server.py).
Graph = CitizenApplicationProcessingAgent
