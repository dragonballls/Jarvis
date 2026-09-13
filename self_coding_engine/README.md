# Standalone Self-Coding Engine

This directory is the detached self-coding core extracted from the application-level coding orchestration.

## Dependency boundary

The engine imports only Python standard-library modules. It has no imports from `agent`, `core`, `desktop`, `providers`, `Jarvis`, or `Friday`.

The host supplies:

- `planner(goal, context) -> CodingPlan`
- `executor(step, workspace, context)`
- `verifier(step, workspace)`
- optional `repairer(step, attempt_number, previous_result, workspace)`

The engine owns workspace confinement, explicit authorized paths, rollback of an unsuccessful attempt, bounded retries, and completion events.

## Intended host integration

A voice assistant such as the Mark 53 application can instantiate `SelfCodingEngine` and provide its own LLM/tool callbacks. The engine does not require that host to expose an HTTP API, a desktop UI, a provider registry, a persona system, an application event bus, or a startup process.

## Detachment status

This package is intentionally standalone. The existing application integrations are not part of this package and should not be imported into it.
