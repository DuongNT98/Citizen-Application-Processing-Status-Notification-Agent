"""AgentCore Platform v1.0 - GOV-C2-013 domain services.

Deterministic helpers only: マイナンバー boundary validation (番号法), per-
procedure document-completeness check, per-procedure eligibility rule
evaluation, department routing, SLA lifecycle tracking, citizen notification
payload construction (status-token only), and department workload report
assembly. No agenticstar imports.
"""

from __future__ import annotations

from typing import Any

# 番号法 boundary: these keys must never appear anywhere in an ingested
# application or in any downstream output. マイナポータル manages マイナンバー
# separately - this agent never processes it.
MY_NUMBER_KEYS = ("my_number", "mynumber", "個人番号", "kojin_bango")

# Per-procedure required documents (deterministic local fallback per proposal
# §12 dependency #2/#3 - the referenced common-pattern templates are unreleased).
REQUIRED_DOCUMENTS: dict[str, list[str]] = {
    "住民票": ["identity_proof"],
    "転出届": ["identity_proof", "current_address_proof"],
    "補助金申請": ["identity_proof", "income_proof", "application_form"],
}

# Per-procedure deterministic eligibility rules (local fallback; production
# swaps in the per-procedure municipal rule YAML per proposal §4).
ELIGIBILITY_RULES: dict[str, dict[str, Any]] = {
    "住民票": {"min_age": 0},
    "転出届": {"min_age": 0, "requires_current_resident": True},
    "補助金申請": {"min_age": 18, "max_income_jpy": 4_000_000},
}

# Per-procedure department routing (deterministic local fallback).
DEPARTMENT_ROUTING: dict[str, str] = {
    "住民票": "市民課",
    "転出届": "市民課",
    "補助金申請": "福祉課",
}

# SLA target hours per procedure (3 business days ~= 72h for 転出届 per proposal §9).
SLA_HOURS: dict[str, float] = {
    "住民票": 24.0,
    "転出届": 72.0,
    "補助金申請": 120.0,
}


def _flatten_keys(value: Any, acc: set[str] | None = None) -> set[str]:
    if acc is None:
        acc = set()
    if isinstance(value, dict):
        for k, v in value.items():
            acc.add(str(k).lower())
            _flatten_keys(v, acc)
    elif isinstance(value, list):
        for v in value:
            _flatten_keys(v, acc)
    return acc


def validate_no_my_number(app: dict[str, Any]) -> list[str]:
    """S-1/番号法 non-suppressible: reject any application carrying a マイナンバー key."""
    text_keys = _flatten_keys(app)
    return [k for k in MY_NUMBER_KEYS if k in text_keys]


def check_doc_completeness(app: dict[str, Any]) -> dict[str, Any]:
    """Deterministic per-procedure required-document completeness check."""
    procedure_type = app.get("procedure_type", "")
    required = REQUIRED_DOCUMENTS.get(procedure_type, [])
    provided = set(app.get("documents", []))
    missing = [d for d in required if d not in provided]
    return {"complete": not missing, "missing_documents": missing}


def check_eligibility(app: dict[str, Any]) -> dict[str, Any]:
    """Deterministic per-procedure eligibility rule evaluation (no LLM - auditable)."""
    procedure_type = app.get("procedure_type", "")
    rules = ELIGIBILITY_RULES.get(procedure_type, {})
    reasons: list[str] = []

    age = app.get("applicant_age")
    min_age = rules.get("min_age")
    if min_age is not None and (age is None or age < min_age):
        reasons.append(f"applicant_age below required minimum ({min_age})")

    if rules.get("requires_current_resident") and not app.get("is_current_resident", False):
        reasons.append("applicant is not a registered current resident")

    max_income = rules.get("max_income_jpy")
    income = app.get("annual_income_jpy")
    if max_income is not None and income is not None and income > max_income:
        reasons.append(f"annual_income_jpy exceeds eligibility ceiling ({max_income})")

    return {"eligible": not reasons, "reasons": reasons}


def route_department(procedure_type: str, routed_at: str) -> dict[str, Any]:
    """Deterministic department routing + SLA-tracking timestamp record."""
    department = DEPARTMENT_ROUTING.get(procedure_type, "総合窓口課")
    return {"department": department, "routed_at": routed_at}


def track_status(procedure_type: str, elapsed_hours: float) -> dict[str, Any]:
    """Lifecycle status + threshold-based SLA-breach detection."""
    sla_deadline = SLA_HOURS.get(procedure_type, 72.0)
    sla_breach = elapsed_hours > sla_deadline
    lifecycle_status = "under_review" if elapsed_hours < sla_deadline else "sla_breach_review"
    return {
        "lifecycle_status": lifecycle_status,
        "sla_breach": sla_breach,
        "sla_deadline_hours": sla_deadline,
    }


def build_notification(department: str, lifecycle_status: str, channel: str = "line") -> dict[str, Any]:
    """S-3: citizen notification carrying a status token only - never PII/content."""
    status_token = f"{department}:{lifecycle_status}"
    return {"channel": channel, "status_token": status_token, "sent": True}


def generate_workload_narrative_fallback(department: str, lifecycle_status: str, sla_breach: bool) -> str:
    """Deterministic fallback narrative when no LLM is configured."""
    breach_note = "an SLA breach requiring escalation" if sla_breach else "on schedule"
    return f"{department}: 1 application currently {lifecycle_status} ({breach_note})."


def build_llm_messages(prompt: str) -> list[dict[str, Any]]:
    """Wrap a prompt in the canonical `BaseLLM.complete(messages: list)` shape.

    `BaseLLM.complete()` takes a message list, not a bare prompt string; passing
    a str makes a real provider raise.
    """
    return [{"role": "user", "content": prompt}]


def extract_llm_text(raw: Any) -> str:
    """Normalise a `BaseLLM.complete()` response to text.

    Canonical `complete()` returns `{"content": str, ...}`. A bare string is
    also accepted for backward compatibility with string-returning test fakes.
    Anything else (missing/non-str `content`, unexpected type) yields `""`, which
    the caller MUST treat as a failed completion — not as usable text.
    """
    if isinstance(raw, dict):
        content = raw.get("content", "")
        return content if isinstance(content, str) else ""
    if isinstance(raw, str):
        return raw
    return ""


def assemble_workload_report(
    department: str, lifecycle_status: str, sla_breach: bool, narrative: str
) -> dict[str, Any]:
    """Assemble the department workload report (S-3 aggregate-only)."""
    return {
        "department": department,
        "aggregate_counts": {"applications_in_scope": 1, "sla_breaches": 1 if sla_breach else 0},
        "narrative": narrative,
    }


def extract_audit_safe_topic(procedure_type: str) -> dict[str, Any]:
    """S-4: audit-safe metadata - procedure type only, never applicant PII."""
    return {"procedure_type": procedure_type}
