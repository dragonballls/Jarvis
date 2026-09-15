# Guarded Windows Maintenance and Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an isolated Windows maintenance subsystem that diagnoses the PC, safely cleans eligible user processes, persistently manages eligible user-app startup entries, performs guarded repairs, verifies every mutation, and preserves all existing Jarvis functionality.

**Architecture:** Add a dedicated `windows_maintenance/` package with typed Windows adapters, policy evaluation, planning, diagnostics, persistent startup policy, audit/rollback state, and a narrow facade. The model requests structured operations only; it never supplies arbitrary PowerShell. Existing chat, self-coding, updater, God’s Eye, provider routing, minimal UI, and packaging lifecycles remain unchanged.

**Tech Stack:** Python 3.12+, Windows PowerShell/CIM/registry/startup APIs behind typed adapters, JSON component-local state, pytest, existing Jarvis Quart API/agent/runtime, GitHub Actions Windows CI.

**Spec:** `docs/superpowers/specs/2026-09-15-windows-maintenance-design.md`

## Global Constraints

- `windows_maintenance/` owns only Windows maintenance discovery, policy, planning, execution adapters, rollback records, persistent maintenance policy, and tests.
- All mutating actions pass through policy evaluation before execution.
- Protected targets include Jarvis, OmniRoute, Windows-critical processes, security software, drivers, required task processes, and explicitly protected targets.
- Read-only diagnostics may run automatically; low-risk process cleanup may run automatically only for explicit supported goals; startup/configuration changes require confirmation unless the exact class has persistent authorization.
- High-risk destructive, security-sensitive, driver, boot, arbitrary-registry, protected-system, and uncertain actions are denied by default.
- The model cannot provide unchecked shell commands as an execution primitive.
- Persistent startup blocking is limited to eligible user-app entries; system-wide or ambiguous entries are not silently changed.
- Failed verification halts the current plan; supported rollback is attempted and verified.
- Maintenance failure must not take down Jarvis chat or unrelated subsystems.
- Existing backend, desktop, startup, self-coding, packaging, and minimal-interface regressions must remain passing.
- Tests must distinguish observed facts from heuristic findings.

---

### Task 1: Establish the isolated maintenance package and contracts

**Files:**
- Create: `windows_maintenance/__init__.py`
- Create: `windows_maintenance/models.py`
- Create: `windows_maintenance/errors.py`
- Create: `windows_maintenance/contracts.py`
- Test: `windows_maintenance/tests/test_contracts.py`

**Interfaces:**
- Produces typed `MaintenanceAction`, `MaintenancePlan`, `PolicyDecision`, `DiagnosticFinding`, `MaintenanceRecord`, and `OperationResult` models used by all later tasks.
- Produces adapter protocols that do not depend on Windows-specific implementation details.

- [ ] **Step 1: Write failing contract tests**

```python
from windows_maintenance.models import MaintenanceAction, RiskClass


def test_action_requires_structured_operation_and_arguments():
    action = MaintenanceAction(
        operation="process.stop",
        target_id="steam.exe",
        arguments={"pid": 1234},
        risk=RiskClass.REVERSIBLE_LOW_RISK,
    )
    assert action.operation == "process.stop"
    assert action.arguments["pid"] == 1234
```

- [ ] **Step 2: Run the focused tests**

Run: `python -m pytest windows_maintenance/tests/test_contracts.py -v`
Expected: FAIL because the package and models do not yet exist.

- [ ] **Step 3: Implement minimal typed models and protocols**

Define enums for risk and policy outcomes, immutable action/plan records, diagnostic findings, operation results, and protocol interfaces for collectors/executors. Reject empty operation names and missing target identities for mutations.

- [ ] **Step 4: Run the focused tests**

Run: `python -m pytest windows_maintenance/tests/test_contracts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add windows_maintenance
 git commit -m "feat: add Windows maintenance contracts"
```

### Task 2: Build the protection policy and structured-action validator

**Files:**
- Create: `windows_maintenance/policy.py`
- Create: `windows_maintenance/validator.py`
- Test: `windows_maintenance/tests/test_policy.py`
- Test: `windows_maintenance/tests/test_validator.py`

**Interfaces:**
- Consumes: `MaintenanceAction`, configured protected-target patterns, current task context.
- Produces: `PolicyDecision` and validated action arguments.

- [ ] **Step 1: Write failing policy tests**

```python
from windows_maintenance.models import MaintenanceAction, RiskClass
from windows_maintenance.policy import MaintenancePolicy


def test_jarvis_process_is_protected():
    policy = MaintenancePolicy()
    action = MaintenanceAction(
        operation="process.stop",
        target_id="Jarvis.exe",
        arguments={"pid": 44},
        risk=RiskClass.REVERSIBLE_LOW_RISK,
    )
    decision = policy.evaluate(action)
    assert not decision.allowed


def test_explicit_user_app_cleanup_is_allowed_when_not_protected():
    policy = MaintenancePolicy()
    action = MaintenanceAction(
        operation="process.stop",
        target_id="steam.exe",
        arguments={"pid": 55},
        risk=RiskClass.REVERSIBLE_LOW_RISK,
    )
    decision = policy.evaluate(action, explicit_user_request=True)
    assert decision.allowed
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest windows_maintenance/tests/test_policy.py windows_maintenance/tests/test_validator.py -v`
Expected: FAIL because policy and validation are not implemented.

- [ ] **Step 3: Implement policy and validation**

Implement deny-by-default operation allowlists, protected names/process publishers/paths, required-risk checks, task-process protection, argument schema validation, and explicit-user-intent handling. A mutation must be rejected before reaching any executor if its target cannot be classified confidently.

- [ ] **Step 4: Add adversarial tests**

Test case-insensitive protected names, critical Windows services/processes, security software, Jarvis/OmniRoute, missing PIDs, invalid startup entry identifiers, unsupported operation names, and attempts to smuggle shell commands inside arguments.

- [ ] **Step 5: Run focused tests**

Run: `python -m pytest windows_maintenance/tests/test_policy.py windows_maintenance/tests/test_validator.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add windows_maintenance/policy.py windows_maintenance/validator.py windows_maintenance/tests/test_policy.py windows_maintenance/tests/test_validator.py
git commit -m "feat: enforce Windows maintenance protection policy"
```

### Task 3: Add read-only Windows diagnostics

**Files:**
- Create: `windows_maintenance/diagnostics.py`
- Create: `windows_maintenance/adapters/diagnostics_windows.py`
- Create: `windows_maintenance/adapters/__init__.py`
- Test: `windows_maintenance/tests/test_diagnostics.py`
- Test: `windows_maintenance/tests/test_diagnostics_windows.py`

**Interfaces:**
- Consumes: no mutating state; optional current-process/task context.
- Produces: `list[DiagnosticFinding]` grouped by CPU/RAM/disk/GPU/network/process/service/startup/errors/drivers/updates/system-files/configuration.

- [ ] **Step 1: Write failing collector tests**

```python
from windows_maintenance.diagnostics import DiagnosticCollector


def test_failed_check_does_not_abort_other_checks():
    collector = DiagnosticCollector([lambda: (_ for _ in ()).throw(OSError("disk query failed")), lambda: "ok"])
    result = collector.collect()
    assert len(result.failures) == 1
    assert result.completed_checks == 1
```

- [ ] **Step 2: Run the focused test**

Run: `python -m pytest windows_maintenance/tests/test_diagnostics.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement fault-isolated diagnostics orchestration**

Implement independent checks with typed timeout/error results. Never execute a mutation. Normalize observations into findings with severity and confidence; mark heuristics as heuristics rather than facts.

- [ ] **Step 4: Implement Windows-backed read-only adapters**

Use safe typed queries for resource metrics, process inventory, startup inventory, services, network configuration/connectivity, Windows event/error signals, device/driver indicators, update state, disk health/free space, and system-file/component-store health indicators. Avoid a single monolithic PowerShell command.

- [ ] **Step 5: Run tests**

Run: `python -m pytest windows_maintenance/tests/test_diagnostics.py windows_maintenance/tests/test_diagnostics_windows.py -v`
Expected: PASS on cross-platform mocks; Windows-backed tests are skipped or marked Windows-only outside Windows.

- [ ] **Step 6: Commit**

```bash
git add windows_maintenance/diagnostics.py windows_maintenance/adapters windows_maintenance/tests/test_diagnostics.py windows_maintenance/tests/test_diagnostics_windows.py
git commit -m "feat: add fault-isolated Windows diagnostics"
```

### Task 4: Implement process cleanup with active-use protection

**Files:**
- Create: `windows_maintenance/processes.py`
- Create: `windows_maintenance/adapters/process_windows.py`
- Test: `windows_maintenance/tests/test_processes.py`
- Test: `windows_maintenance/tests/test_processes_windows.py`

**Interfaces:**
- Consumes: policy decisions, process inventory, active-task context.
- Produces: structured cleanup plans and verified `OperationResult` values.

- [ ] **Step 1: Write failing process-safety tests**

```python
def test_active_user_process_is_not_selected_for_cleanup(process_manager):
    plan = process_manager.plan_stop("notepad.exe", pid=99, active_user_pids={99})
    assert plan.allowed is False
```

- [ ] **Step 2: Run focused test**

Run: `python -m pytest windows_maintenance/tests/test_processes.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement eligibility checks**

Require a stable PID/process identity, verify executable path/publisher where possible, reject protected targets, reject active task processes, and prefer process-tree aware handling so a child process required by another active application is not accidentally terminated.

- [ ] **Step 4: Implement typed Windows stop adapter**

The executor accepts only a validated PID plus expected process identity. After requesting termination, re-query the PID and verify the process is gone or report failure-to-verify. Do not expose a generic `kill(command_string)` API.

- [ ] **Step 5: Run tests**

Run: `python -m pytest windows_maintenance/tests/test_processes.py windows_maintenance/tests/test_processes_windows.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add windows_maintenance/processes.py windows_maintenance/adapters/process_windows.py windows_maintenance/tests/test_processes.py windows_maintenance/tests/test_processes_windows.py
git commit -m "feat: add guarded process cleanup"
```

### Task 5: Implement persistent startup inspection, disablement, and reconciliation

**Files:**
- Create: `windows_maintenance/startup.py`
- Create: `windows_maintenance/persistence.py`
- Create: `windows_maintenance/adapters/startup_windows.py`
- Test: `windows_maintenance/tests/test_startup.py`
- Test: `windows_maintenance/tests/test_startup_persistence.py`
- Test: `windows_maintenance/tests/test_startup_windows.py`

**Interfaces:**
- Consumes: startup inventory and policy decisions.
- Produces: startup classification, idempotent disable operations, persistent user-intent records, and reconciliation results.

- [ ] **Step 1: Write failing startup tests**

```python
def test_user_app_startup_entry_can_be_disabled_and_recorded(startup_manager):
    result = startup_manager.disable("Steam", source="HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run")
    assert result.changed is True
    assert result.rollback_available is True


def test_second_disable_is_idempotent(startup_manager):
    startup_manager.disable("Steam", source="HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run")
    result = startup_manager.disable("Steam", source="HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run")
    assert result.changed is False
```

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest windows_maintenance/tests/test_startup.py windows_maintenance/tests/test_startup_persistence.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement startup classification**

Classify entries as protected, user-managed, unknown, or unsafe-to-change. Track source, normalized identity, command/path, publisher, scope, current state, and confidence. User-scoped application entries are eligible when ownership is clear; ambiguous or machine-wide entries require higher risk handling.

- [ ] **Step 4: Implement persistent maintenance policy storage**

Store only maintenance-owned JSON records under a component-specific state directory. Each record contains startup target identity, source, previous state, desired state, creation timestamp, reason, and rollback metadata. Validate on read and reject malformed records without crashing the subsystem.

- [ ] **Step 5: Implement typed Windows startup mutations**

Support user startup folders and user Run/RunOnce entries through code-owned adapters. Before mutation, re-check target identity and protection status. After mutation, re-enumerate startup entries to verify desired state.

- [ ] **Step 6: Implement reconciliation**

Provide an explicit `reconcile_policies()` operation invoked during a maintenance request/diagnostic pass. It detects an eligible application that recreated a previously blocked startup entry and reports it as a proposed re-enforcement rather than silently starting a permanent background enforcement loop.

- [ ] **Step 7: Run tests**

Run: `python -m pytest windows_maintenance/tests/test_startup.py windows_maintenance/tests/test_startup_persistence.py windows_maintenance/tests/test_startup_windows.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add windows_maintenance/startup.py windows_maintenance/persistence.py windows_maintenance/adapters/startup_windows.py windows_maintenance/tests/test_startup.py windows_maintenance/tests/test_startup_persistence.py windows_maintenance/tests/test_startup_windows.py
git commit -m "feat: add persistent guarded startup management"
```

### Task 6: Add mutation audit, verification, and rollback state machine

**Files:**
- Create: `windows_maintenance/audit.py`
- Create: `windows_maintenance/execution.py`
- Test: `windows_maintenance/tests/test_execution.py`
- Test: `windows_maintenance/tests/test_audit.py`

**Interfaces:**
- Consumes: validated actions and typed adapters.
- Produces: append-only `MaintenanceRecord` entries and verified operation outcomes.

- [ ] **Step 1: Write failing rollback tests**

```python
def test_failed_verification_triggers_supported_rollback(executor, adapter):
    adapter.verify_result = False
    result = executor.execute(action)
    assert result.success is False
    assert result.rollback_attempted is True
    assert result.continue_plan is False
```

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest windows_maintenance/tests/test_execution.py windows_maintenance/tests/test_audit.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement append-only maintenance audit records**

Persist correlation ID, operation, target, previous state, resulting state, verification result, rollback data, and error information. Do not store secrets or raw model prompts.

- [ ] **Step 4: Implement execution state machine**

Enforce `policy -> prepare -> execute -> verify -> rollback-if-supported`. A failed or unknown verification stops the current plan. Subsequent unrelated actions cannot run after a critical failure.

- [ ] **Step 5: Run tests**

Run: `python -m pytest windows_maintenance/tests/test_execution.py windows_maintenance/tests/test_audit.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add windows_maintenance/audit.py windows_maintenance/execution.py windows_maintenance/tests/test_execution.py windows_maintenance/tests/test_audit.py
git commit -m "feat: verify and rollback maintenance mutations"
```

### Task 7: Add guarded repair adapters

**Files:**
- Create: `windows_maintenance/repairs.py`
- Create: `windows_maintenance/adapters/system_repair_windows.py`
- Create: `windows_maintenance/adapters/network_windows.py`
- Create: `windows_maintenance/adapters/application_windows.py`
- Test: `windows_maintenance/tests/test_repairs.py`
- Test: `windows_maintenance/tests/test_repairs_windows.py`

**Interfaces:**
- Consumes: diagnostic findings plus explicit, policy-approved repair actions.
- Produces: typed repair operations with preconditions and verification criteria.

- [ ] **Step 1: Write failing repair-policy tests**

```python
def test_system_file_repair_requires_supported_operation(repairs):
    action = repairs.plan("system.files.repair")
    assert action.operation == "system.files.repair"


def test_arbitrary_registry_repair_is_denied(repairs):
    decision = repairs.policy_for("registry.arbitrary.write")
    assert decision.allowed is False
```

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest windows_maintenance/tests/test_repairs.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement supported repair allowlist**

Cover system-file/component-store checks and repairs, selected application repair/reset operations, and supported network configuration resets. Each operation defines exact executable/API arguments, required privileges, side effects, verification probes, rollback support, and required confirmation risk.

- [ ] **Step 4: Keep privileged operations behind explicit adapters**

Use code-owned PowerShell/API invocations with fixed command templates and parameter validation. Never concatenate model text into shell source. Do not add automatic driver replacement, security disablement, boot changes, arbitrary registry editing, or partition operations.

- [ ] **Step 5: Run Windows-specific tests**

Run on Windows: `python -m pytest windows_maintenance/tests/test_repairs_windows.py -v`
Expected: safe fixture/mocked paths PASS; actual dangerous mutation paths are not part of CI.

- [ ] **Step 6: Commit**

```bash
git add windows_maintenance/repairs.py windows_maintenance/adapters/system_repair_windows.py windows_maintenance/adapters/network_windows.py windows_maintenance/adapters/application_windows.py windows_maintenance/tests/test_repairs.py windows_maintenance/tests/test_repairs_windows.py
git commit -m "feat: add guarded Windows repair adapters"
```

### Task 8: Create the maintenance planner and narrow Jarvis facade

**Files:**
- Create: `windows_maintenance/planner.py`
- Create: `windows_maintenance/facade.py`
- Test: `windows_maintenance/tests/test_planner.py`
- Test: `windows_maintenance/tests/test_facade.py`

**Interfaces:**
- Consumes: natural-language maintenance intent, diagnostics, policy, and typed operation registry.
- Produces: structured `MaintenancePlan` with actions, explanations, confirmations, rollback, and verification criteria.

- [ ] **Step 1: Write failing planner tests**

```python
def test_fix_everything_never_becomes_unrestricted_mutation(planner):
    plan = planner.plan("fix whatever is wrong")
    assert all(action.risk.name != "HIGH_RISK" for action in plan.actions)
    assert plan.skipped_risks


def test_stop_steam_request_creates_process_and_startup_actions(planner):
    plan = planner.plan("stop Steam from running in the background and keep it from launching at startup")
    assert {a.operation for a in plan.actions} >= {"process.stop", "startup.disable"}
```

- [ ] **Step 2: Run focused tests**

Run: `python -m pytest windows_maintenance/tests/test_planner.py windows_maintenance/tests/test_facade.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement deterministic intent-to-operation mapping**

Recognize diagnostics, cleanup, startup prevention, gaming optimization, and guarded repair intents. Require target disambiguation when multiple applications match. The planner emits explanations and skipped actions for unsupported/high-risk requests.

- [ ] **Step 4: Implement facade orchestration**

Provide a narrow interface such as `MaintenanceFacade.handle(request: str, context: MaintenanceContext) -> MaintenanceResponse`. It performs diagnostics when needed, plans operations, applies policy, executes approved actions, and returns a human-readable summary plus machine-readable audit references.

- [ ] **Step 5: Add ambiguity and safety tests**

Test empty requests, vague “fix everything,” protected-target requests, unsupported shell-command attempts, duplicate startup requests, and explicit gaming optimization. No facade test should require the desktop UI or unrelated services to initialize.

- [ ] **Step 6: Run tests**

Run: `python -m pytest windows_maintenance/tests/test_planner.py windows_maintenance/tests/test_facade.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add windows_maintenance/planner.py windows_maintenance/facade.py windows_maintenance/tests/test_planner.py windows_maintenance/tests/test_facade.py
git commit -m "feat: add guarded maintenance planner and facade"
```

### Task 9: Integrate maintenance into Jarvis chat without changing the public API surface

**Files:**
- Modify: `desktop/api_server.py`
- Modify: existing agent routing file identified by the current maintenance dispatch boundary
- Test: `windows_maintenance/tests/test_integration_boundary.py`
- Test: existing relevant backend API tests

**Interfaces:**
- Consumes: `MaintenanceFacade` through a small dependency injection boundary.
- Produces: normal Jarvis chat events describing diagnosis, proposed actions, confirmations, results, and verification.

- [ ] **Step 1: Add an integration test that proves normal chat remains available**

```python
async def test_chat_without_maintenance_request_stays_on_existing_path(client):
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200
```

- [ ] **Step 2: Run the regression test and record current failure state if any**

Run: `python -m pytest <existing chat test path> -v`
Expected: PASS before integration changes. If the current repository has a pre-existing failure, record it without attributing it to this feature.

- [ ] **Step 3: Add narrow maintenance dispatch**

Detect supported maintenance intents in the normal agent flow and invoke only the facade. Do not add arbitrary maintenance HTTP routes or weaken `before_request` route restrictions.

- [ ] **Step 4: Run backend regression tests**

Run: `python -m pytest <existing chat test path> windows_maintenance/tests/test_integration_boundary.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add desktop/api_server.py windows_maintenance/tests/test_integration_boundary.py <agent-routing-file>
git commit -m "feat: route guarded maintenance through Jarvis chat"
```

### Task 10: Add Windows CI validation and release regression coverage

**Files:**
- Modify: `.github/workflows/jarvis-integration.yml`
- Modify: `.github/workflows/windows-app.yml`
- Create: `windows_maintenance/tests/test_windows_ci_contract.py`

**Interfaces:**
- Consumes: installed package and test suite.
- Produces: independent Windows maintenance CI validation without changing packaging lifecycle.

- [ ] **Step 1: Add CI test contract**

```python
def test_windows_maintenance_package_imports_without_desktop_bootstrap():
    import windows_maintenance
    assert windows_maintenance.__name__ == "windows_maintenance"
```

- [ ] **Step 2: Configure dedicated Windows test job**

Run package unit tests plus safe Windows adapter integration tests on a Windows runner. Do not perform destructive actions on CI hosts.

- [ ] **Step 3: Run required CI-local tests**

Run: `python -m pytest windows_maintenance/tests -v`
Expected: PASS on Windows; cross-platform tests pass elsewhere and Windows-only tests skip outside Windows.

- [ ] **Step 4: Run existing desktop/package checks**

Run the repository’s existing Windows packaging smoke path and desktop build checks. Do not alter packaging files unless a test demonstrates a direct incompatibility.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/jarvis-integration.yml .github/workflows/windows-app.yml windows_maintenance/tests/test_windows_ci_contract.py
git commit -m "test: verify Windows maintenance on CI"
```

### Task 11: Final full-system verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE_COMPONENTS.md`
- Modify: `AGENTS.md`
- Create: `windows_maintenance/README.md`
- Test: complete existing backend, frontend, packaging, and maintenance suites

**Interfaces:**
- Documents: maintenance boundary, supported natural-language actions, protections, persistent startup behavior, rollback expectations, and verification requirements.

- [ ] **Step 1: Document the new component boundary**

State explicitly that `windows_maintenance/` does not own self-coding, updater, packaging, Git state, God's Eye, or provider state; all mutations are typed and policy checked.

- [ ] **Step 2: Document persistent startup behavior**

Explain that eligible user-app startup entries can be disabled persistently, that the change is auditable and reversible when supported, and that machine-wide/ambiguous entries are not silently disabled.

- [ ] **Step 3: Run all maintenance tests**

Run: `python -m pytest windows_maintenance/tests -v`
Expected: PASS.

- [ ] **Step 4: Run all backend tests**

Run: `python -m pytest tests/ -v`
Expected: PASS.

- [ ] **Step 5: Run frontend validation**

Run: `cd desktop && npm run test && npm run lint && npx tsc --noEmit && npm run build`
Expected: PASS.

- [ ] **Step 6: Run packaging/smoke verification**

Run the existing Windows packaging and smoke-test workflow. Confirm Jarvis still launches through the existing startup path and the minimal chat bar remains the only visible application control.

- [ ] **Step 7: Review the Git diff for cross-component contamination**

Confirm no maintenance code modifies self-coding workspaces, Jarvis updater state, Git checkout state, provider credentials, God's Eye state, or external component installations.

- [ ] **Step 8: Commit documentation and final verification**

```bash
git add README.md ARCHITECTURE_COMPONENTS.md AGENTS.md windows_maintenance/README.md
git commit -m "docs: document guarded Windows maintenance"
```

### Final verification gate

- [ ] Run the full Python test suite.
- [ ] Run the maintenance suite independently.
- [ ] Run frontend tests/lint/type-check/build.
- [ ] Run Windows packaging/smoke verification.
- [ ] Verify GitHub Actions reports every required job successful.
- [ ] Verify maintenance import isolation independently.
- [ ] Verify protected process/startup targets are denied before execution.
- [ ] Verify an eligible user startup entry remains disabled after re-inventory/sign-in simulation.
- [ ] Verify a failed mutation verification halts the plan and rolls back where supported.
- [ ] Verify normal chat, self-coding, startup, updater, and packaging behavior is unchanged.
