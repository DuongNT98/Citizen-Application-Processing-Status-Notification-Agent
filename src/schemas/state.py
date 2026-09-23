"""AgentCore Platform v1.0 - GOV-C2-013 state schema."""

# ADR-005: State must be a flat TypedDict - never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects (and nested
# dict/list containers) are not msgpack-safe. Extend AgentState with agent-specific
# fields only. Nested list/dict fields are stored as JSON strings and
# (de)serialized at the node boundary via to_json/from_json below. Do NOT add
# credentials, secrets, or Pydantic models.
#
# 番号法 boundary: マイナンバー (Japan's individual number) is NEVER stored in
# State — マイナポータル manages it separately. ApplicationIngestNode enforces
# this at ingestion; OutputValidateNode re-checks it non-suppressibly.

from __future__ import annotations

import json
from typing import Any, NotRequired, Optional

from framework.schemas.agent_state import AgentState


def to_json(value: Any) -> Optional[str]:
    """Serialize a list/dict State value to a compact JSON string (ADR-005, msgpack-safe)."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def from_json(value: Any, default: Any) -> Any:
    """Deserialize a JSON-string State value back to its list/dict form (tolerant)."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class State(AgentState):
    """Citizen application processing & status notification state.

    Shared fields (user_input, validated_input, status, session_id, node_history,
    error_log, result, formatted_output, hitl_*, etc.) are inherited from AgentState.
    Only agent-specific, flat, JSON-serializable fields are declared below; all are
    NotRequired (written mid-pipeline).
    """

    # AgentState is a TypedDict at runtime, but the SDK ships no py.typed marker,
    # so mypy sees it as Any and no longer recognizes State as a TypedDict body -
    # it then rejects every NotRequired[] below as used outside a TypedDict
    # definition. This is a mypy/stub-visibility limitation, not a code error
    # (verified: TypedDict-ness and NotRequired all work correctly at runtime).
    # JSON dict{procedure_type, applicant_ref, documents:[...]} - validated application (no マイナンバー).
    application_data: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{complete: bool, missing_documents: [...]} - document completeness result.
    doc_completeness_result: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{eligible: bool, reasons: [...]} - deterministic eligibility decision.
    eligibility_decision: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{department, routed_at} - department routing decision.
    routing_decision: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{lifecycle_status, sla_breach: bool, sla_deadline} - status + SLA tracking.
    status_track_result: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{channel, status_token, sent: bool} - citizen notification result (S-3 status-token only).
    notification_result: NotRequired[str | None]  # type: ignore[valid-type]
    # JSON dict{department, aggregate_counts, narrative} - department workload report.
    workload_report: NotRequired[str | None]  # type: ignore[valid-type]
