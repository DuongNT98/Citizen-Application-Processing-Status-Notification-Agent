# GOV-C2-013 — Citizen Application Processing & Status Notification Agent

> **Category**: Cat 2 (multiple processing steps combined to complete one specific use case)
> **Industry**: Government

## Overview

Processes a citizen's application to a Japanese municipal government (for example a resident
registration, a move-out notification, or a subsidy application) end-to-end. Input is an
application submitted through Japan's myna Portal (マイナポータル) API or a web form, together with
its supporting documents. The pipeline checks the submission for document completeness, evaluates
per-procedure eligibility against a deterministic, configuration-driven rule set (no LLM in this
decision), routes the application to the correct municipal department, tracks its processing
status and flags SLA-breach risk, sends status notifications back to the citizen (received /
under review / approved / complete) over LINE or myna Portal, and produces an aggregate,
department-level workload report. Japan's My Number Act boundary is enforced at intake: the
citizen's My Number identifier is never processed or stored by this template — myna Portal
handles that separately. The template does not set eligibility policy itself (that is supplied as
per-procedure configuration) and does not autonomously follow up with citizens beyond the fixed
notification points in its pipeline.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and operational documentation
```

See `docs/` for the design spec and test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
