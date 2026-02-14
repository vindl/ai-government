# Architectural Decisions

## ADR-001: Claude Code SDK over Claude Agent SDK
**Date**: 2026-02-14
**Status**: Accepted

**Context**: The plan originally called for `claude-agent-sdk` but the actual package available is `claude-code-sdk` which wraps Claude Code CLI as subprocesses.

**Decision**: Use `claude-code-sdk` (the Claude Code SDK) for agent orchestration. Each government agent runs as a Claude Code subprocess with a specific system prompt.

**Consequences**: Agents are isolated processes. Communication happens through structured inputs/outputs (JSON). This gives us natural parallelism and fault isolation.

---

## ADR-002: Pydantic v2 for All Data Models
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need structured, validated data flowing between agents.

**Decision**: All inter-agent data uses Pydantic v2 models with strict validation.

**Consequences**: Type safety throughout the pipeline. Easy JSON serialization for agent communication.

---

## ADR-003: Two-Fleet Architecture
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need both runtime AI agents (government simulation) and development tooling.

**Decision**:
- Fleet 1 (Government Mirror): Python agents orchestrated by Claude Code SDK — ministry subagents analyzing decisions
- Fleet 2 (Dev Fleet): Claude Code instances with role-specific `CLAUDE.md` prompts (coder, reviewer, tester, pm, devops)

**Consequences**: Clean separation between the product (government simulation) and the development process. Dev fleet members can work on the codebase with specialized expertise.

---

## ADR-004: anyio for Async Concurrency
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need to run multiple ministry agents in parallel for performance.

**Decision**: Use `anyio` instead of raw `asyncio` for all async operations.

**Consequences**: Backend-agnostic async code. Cleaner task group API for parallel agent dispatch.

---

## ADR-005: Montenegrin Government Focus
**Date**: 2026-02-14
**Status**: Accepted

**Context**: Need a specific government to mirror for concrete, testable output.

**Decision**: Focus on Montenegro's government structure with 5 initial ministries: Finance, Justice, EU Integration, Health, Interior.

**Consequences**: Prompts and scrapers are Montenegro-specific. The architecture is general enough to adapt to other governments later.
