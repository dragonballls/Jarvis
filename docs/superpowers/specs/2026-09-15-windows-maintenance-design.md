# Guarded Windows Maintenance and Repair Design

**Date:** 2026-09-15  
**Status:** Design approved in chat; awaiting written-spec review before implementation planning.

## Goal

Add a guarded Windows maintenance and repair subsystem to Jarvis that can diagnose, explain, propose, execute, verify, and—where practical—reverse safe changes without weakening Jarvis's existing permission boundary, self-coding lifecycle, or minimal chat-only interface.

The subsystem is explicitly not an unrestricted Windows administrator. Its operating target is maximum useful automation subject to protected-resource rules, action risk classification, confirmation requirements, rollback support, and post-action verification.

## Architectural Boundary

Create a dedicated top-level package:

`windows_maintenance/`

The package owns Windows maintenance discovery, policy evaluation, action planning, execution adapters, rollback records, and maintenance-specific tests. It does not own Jarvis self-coding, Git checkout updates, Windows application packaging, God's Eye, provider routing, or UI state.

Jarvis communicates with the subsystem through a narrow maintenance facade/service interface. Existing agent and API layers remain responsible for deciding when a user request should invoke that facade; they must not embed raw PowerShell or Windows mutation logic.

Component-specific mutable state is stored under a maintenance-owned namespace. Logs and errors use a component identifier such as `windows_maintenance`.

## Capabilities

### Resource cleanup

Read CPU, memory, disk, GPU, network, process, and selected application activity metrics. Detect sustained resource pressure and identify candidate user applications that are idle or unnecessary for the current task.

Actions may include stopping eligible user applications/processes. The policy must protect Jarvis, OmniRoute, security software, Windows-critical processes, active user applications, processes required by the current task, and explicitly protected processes.

Jarvis should prefer recommendation over automatic termination when confidence is low or when the process relationship is unclear.

### Startup management

Inspect Windows startup mechanisms relevant to the current user and common application startup locations. Classify entries as protected, user-managed, unknown, or unsafe-to-change.

Disable only eligible user-application startup entries. Never blindly disable all startup items. Protect Windows components, drivers, security software, Jarvis, dependencies, and entries whose ownership or impact cannot be established safely.

Every startup mutation records the source, previous state, new state, reason, and reversibility information.

### Diagnostics

A diagnostic collector gathers, as available:

- CPU, memory, disk, and GPU pressure
- disk free space and health indicators exposed by supported Windows APIs/commands
- service and startup state
- network configuration and connectivity signals
- crashed or hung application information
- relevant Windows/system error signals
- driver/device problem indicators
- Windows update state
- system-file/component-store health indicators
- common configuration anomalies

Diagnostics are read-only. Collection failures are captured per-check and do not abort unrelated checks.

### Safe repair

Repairs use a risk-tier pipeline:

`diagnose -> explain -> propose -> confirmation when required -> safety/rollback preparation -> execute -> verify -> rollback on failed verification when supported`

Examples include supported Windows system-file and component-store repair flows, application repair actions, network reset/reconfiguration actions, and narrowly scoped settings repairs.

Protected system components, arbitrary registry edits, driver replacement, security-control changes, boot configuration changes, and similarly high-risk operations are not automatically performed from heuristic reasoning. They require explicit policy support and the appropriate confirmation/escalation path.

## Policy and Permission Model

The maintenance facade evaluates every requested action before execution.

### Action classes

- **READ_ONLY:** diagnostics and inventory; may run automatically.
- **REVERSIBLE_LOW_RISK:** safe cleanup or user-app process actions when the policy can prove eligibility; may execute automatically for explicitly requested cleanup/optimization goals.
- **REVERSIBLE_MEDIUM_RISK:** startup changes and selected configuration changes; require confirmation unless a persistent user policy explicitly authorizes that exact class of change.
- **HIGH_RISK:** destructive, security-sensitive, driver, boot, arbitrary registry, protected-system, or uncertain actions; denied by default and never inferred from vague natural language.

The policy is deny-by-default for any action outside an explicitly supported operation and target class.

Protected targets are evaluated before a command or API is executed, not after.

## Action Planning

Natural-language requests are converted into a structured maintenance plan before execution. A plan contains:

- intent and scope
- diagnostics consulted
- proposed actions
- target identities
- risk classes
- protection decisions
- confirmation requirements
- rollback strategy
- verification criteria

The planner must never turn a vague request such as “fix everything” into unrestricted system mutation. It should select the safest supported plan that addresses the detected issues and report skipped items with reasons.

## Execution Adapters

Use typed adapters for Windows operations rather than constructing arbitrary shell commands from model output.

Initial adapters should cover supported Windows process, startup, diagnostics, system-file/component-store, application, network, and verification operations. PowerShell may be used behind an adapter where Windows does not expose an equivalent practical API, but command construction remains code-owned and parameterized.

The model can request an operation by structured name and validated arguments; it cannot supply an unchecked command string as the execution primitive.

## Rollback and Audit

Each mutating action emits an append-only maintenance record containing a correlation ID, timestamp, operation, target, previous state when known, resulting state, verification result, and rollback information.

Rollback support is operation-specific. If an operation cannot be safely reversed, the planner must classify that explicitly and require the corresponding higher-risk confirmation before execution.

A failed verification must stop the current maintenance plan. Where rollback is available, Jarvis attempts it and then verifies the rollback result. It must not continue executing subsequent unrelated mutations after a failed critical repair step.

## API Integration

The existing minimal API remains the public surface for chat and self-coding. Maintenance requests should be dispatched through the normal chat/agent path to avoid creating a competing control plane.

A narrowly scoped maintenance service/facade may be exposed internally to the agent runtime. Any future HTTP maintenance endpoint, if justified later, must be separately authenticated, policy-checked, and added only with dedicated tests.

The existing `desktop/api_server.py` minimal-mode route protection must remain intact. fileciteturn13file0

## Natural-Language Behaviors

Examples the implementation must support include:

- “Clean up whatever is wasting resources.”
- “Stop Steam from running in the background and keep it from launching at startup.”
- “Diagnose my PC.”
- “Fix whatever is wrong, but don't change anything important.”
- “Optimize my PC for gaming.”

The assistant should explain what it found and what it proposes before medium- or high-risk actions. Explicit user intent can authorize supported low-risk actions without an unnecessary confirmation loop, but protected-target and risk rules always remain authoritative.

## Failure Handling

The subsystem is fault-isolated. A failed Windows query returns a typed diagnostic failure and does not take down Jarvis chat or unrelated maintenance checks.

Execution failures include operation, target, Windows error information when available, and the policy decision. Timeouts are bounded and followed by state re-checks where possible.

Unknown post-action state is treated as failure-to-verify, not success.

## Testing

Dedicated tests live under `windows_maintenance/tests/` and must cover:

- protected-process and protected-startup classification
- allow/deny policy decisions
- structured action validation
- read-only diagnostics
- process cleanup safety
- startup mutation safety
- rollback bookkeeping
- verification and rollback-on-failure behavior
- malformed/ambiguous natural-language planning inputs at the facade boundary
- component import isolation

Windows-specific integration tests should run on Windows CI and use safe fixtures/mocks for mutation paths. Cross-platform unit tests should cover policy, planning, validation, and state-machine logic without requiring Windows.

Relevant existing Jarvis regression and packaging tests remain required for release readiness.

## Compatibility and Continuity

The design preserves the existing architectural separation: self-coding remains responsible for bounded source changes, the Jarvis Windows updater remains responsible for Jarvis release installation, and external components retain their own lifecycles. fileciteturn12file0

The user-facing product remains the single visible chat bar. Maintenance activity is communicated through normal Jarvis responses rather than introducing a dashboard or persistent maintenance UI. fileciteturn7file0

## Non-Goals

This first subsystem does not provide:

- unrestricted administrator command execution
- arbitrary model-authored PowerShell as a primitive
- automatic security-software disabling
- automatic driver replacement
- unrestricted registry editing
- automatic bootloader or partition changes
- silent mass process termination
- automatic changes to other Jarvis component installations or update state

## Success Criteria

The feature is ready only when:

1. The subsystem imports independently and has dedicated tests.
2. Every supported mutation passes through policy evaluation.
3. Protected targets are rejected before execution.
4. Medium/high-risk actions follow the required confirmation policy.
5. Mutating operations record enough state for supported rollback.
6. Verification is mandatory for completed mutations and failed verification prevents blind continuation.
7. Windows CI validates safe integration paths.
8. Existing Jarvis backend, desktop build, packaging, startup, self-coding, and minimal-interface regression tests remain passing.
9. The component can fail without making unrelated Jarvis functions unavailable.
