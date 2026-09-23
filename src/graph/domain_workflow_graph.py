"""AgentCore Platform v1.0 - GOV-C2-013 inner domain workflow graph.

Cat 2 inner graph: document completeness -> eligibility check -> department
routing -> status tracking -> citizen notification. Instantiated by
CitizenApplicationGraphNode.get_subgraph() in graph.py.

Pipeline (linear, fail-fast on ERROR - except eligibility, which is a valid
business outcome and never short-circuits):
    START -> doc_completeness_check -> eligibility_check -> dept_route
          -> status_track -> citizen_notify -> END
"""

from typing import Any

from langgraph.graph import END, START

from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus

from src.nodes.citizen_notify_node import CitizenNotifyNode
from src.nodes.dept_route_node import DeptRouteNode
from src.nodes.doc_completeness_check_node import DocCompletenessCheckNode
from src.nodes.eligibility_check_node import EligibilityCheckNode
from src.nodes.status_track_node import StatusTrackNode
from src.schemas.state import State


class CitizenApplicationWorkflowGraph(BaseGraph):
    """Inner graph for the GOV-C2-013 citizen-application processing workflow."""

    @property
    def name(self) -> str:
        return "citizen-application-workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        # No mandatory config: llm is optional (deterministic fallback exists).
        pass

    def register_nodes(self) -> None:
        # No super() - BaseGraph.register_nodes() is abstract.
        self._nodes["doc_completeness_check"] = DocCompletenessCheckNode()
        self._nodes["eligibility_check"] = EligibilityCheckNode()
        self._nodes["dept_route"] = DeptRouteNode()
        self._nodes["status_track"] = StatusTrackNode()
        self._nodes["citizen_notify"] = CitizenNotifyNode()

    def add_edges(self) -> None:
        self._sg.add_edge(START, "doc_completeness_check")
        self._sg.add_conditional_edges(
            "doc_completeness_check",
            lambda s: END if self._is_error(s) else "eligibility_check",
            {"eligibility_check": "eligibility_check", END: END},
        )
        # eligibility_check never returns ERROR by design (ineligible is a
        # valid business outcome) - still guard defensively.
        self._sg.add_conditional_edges(
            "eligibility_check",
            lambda s: END if self._is_error(s) else "dept_route",
            {"dept_route": "dept_route", END: END},
        )
        self._sg.add_conditional_edges(
            "dept_route",
            lambda s: END if self._is_error(s) else "status_track",
            {"status_track": "status_track", END: END},
        )
        self._sg.add_conditional_edges(
            "status_track",
            lambda s: END if self._is_error(s) else "citizen_notify",
            {"citizen_notify": "citizen_notify", END: END},
        )
        self._sg.add_edge("citizen_notify", END)

    @staticmethod
    def _is_error(state: AgentState) -> bool:
        return state.get("status") in (AgentStatus.ERROR.value, AgentStatus.ERROR.value)

    def route(self, state: AgentState) -> str:
        return END if self._is_error(state) else "citizen_notify"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        return {
            "doc_completeness_result": state.get("doc_completeness_result"),
            "eligibility_decision": state.get("eligibility_decision"),
            "routing_decision": state.get("routing_decision"),
            "status_track_result": state.get("status_track_result"),
            "notification_result": state.get("notification_result"),
            "status": state.get("status"),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
