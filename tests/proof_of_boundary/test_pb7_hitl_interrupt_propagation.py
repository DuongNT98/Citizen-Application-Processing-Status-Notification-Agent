# PB-7: HITL Interrupt Propagation
#
# Per the scaffold's Proof-of-Boundary manifest, this stub is required in
# every template regardless of HITL usage. GOV-C2-013 does not set
# `hitl.enabled: true` in config/config.yaml (no interrupt() call anywhere in
# src/nodes/), so the boundary is N/A here and the test auto-skips.
# A template that turns on HITL must replace this stub with a real
# GraphInterrupt-propagation test (see the framework's PB-7 spec).

import os
import re

import pytest


def _hitl_enabled() -> bool:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "agent.yaml")
    if not os.path.exists(config_path):
        return False
    with open(config_path, encoding="utf-8") as f:
        content = f.read()
    # Matches a "hitl:" block containing "enabled: true" (YAML nested key),
    # without pulling in a PyYAML dependency for this one boolean check.
    return bool(re.search(r"hitl:\s*\n(?:\s+.*\n)*?\s+enabled:\s*true", content))


@pytest.mark.skipif(not _hitl_enabled(), reason="hitl.enabled is not set in config/agent.yaml — PB-7 N/A for this template")
def test_hitl_interrupt_propagation():
    """Placeholder — only meaningful for templates with hitl.enabled: true.

    For a real GraphInterrupt-propagation check, see a HITL-enabled sibling
    template's proof_of_boundary suite (e.g. an AutoRemediate-style node
    that calls interrupt() from execute()).
    """
    pytest.skip("HITL not enabled for this template")
