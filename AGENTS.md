# AI Agent Guide for Jarvis

This file instructs AI coding agents (OpenHands, OpenCode, Claude Code, Cline, Cursor, and similar tools) how to work safely in this project.

## Core rule: isolate every addition

Every current and future integration, feature, engine, service, updater, runtime, or external component must have its own identifiable boundary before implementation begins.

Do not combine unrelated additions into one mutable lifecycle, installer, updater, workspace, runtime-state directory, or executable. They may coordinate through narrow, explicit interfaces, but they must remain independently testable and diagnosable.

### Required structure for a new integration

For every new integration or subsystem:

1. Give it a unique top-level package/directory when practical.
2. Give it a component-specific configuration/state namespace; never reuse another component's mutable state.
3. Give it a component-specific bridge or facade for communication with Jarvis.
4. Give it dedicated tests that can run without unrelated integrations.
5. Give its errors/logging a component identifier.
6. Add a dedicated CI job when the integration is substantial enough to require independent installation, runtime, or compatibility verification.
7. Keep installation/update/replacement responsibilities inside that component's boundary.
8. Never silently let one component become responsible for modifying another component's files, binaries, Git checkout, updater manifest, or persistent state.

### Current component boundaries

- `mark53/` — Mark 53 integration boundary only. Read-only bridge; no Mark files, binaries, updater state, or startup management.
- `mark_updater/` — Mark 53 updater boundary only. Never updates Jarvis or its self-coding workspace.
- `self_coding/` — Jarvis self-coding facade only. Never replaces `Jarvis.exe` directly.
- `agent/openhands_runtime.py` — OpenHands runtime adapter only.
- `core/opencode_agent.py` — coding-engine routing only; OpenHands/OpenCode operate through the self-coding boundary.
- `agent/evolution.py` — EMRG-style bounded evolution/verification only; no executable updater responsibility.
- `integrations/gods_eye/` plus God's Eye bridge/context tests — God's Eye only.
- `providers/`, `config/`, and `core/blackout.py` — provider/routing/privacy behavior only.
- `scripts/update.py` — Jarvis source/release updater only.
- `packaging/windows/` — Windows packaging and executable lifecycle only.

## Integration coordination

The supported pattern is:

`Jarvis chat -> self-coding -> verified GitHub change -> Jarvis Windows updater`

Independent external-component patterns are:

`Jarvis -> component bridge -> external component`

and:

`external component -> component-specific updater -> external component installation`

Coordination must not collapse these lifecycles into a shared mutable installation or state directory.

## Verification requirements

Before declaring an addition complete:

- Compile/import the component independently.
- Run its dedicated tests.
- Run the relevant existing regression tests.
- Confirm the component does not require another unrelated component merely to import or initialize.
- Confirm failure messages identify the component.
- For packaged/runtime changes, run the applicable packaging or smoke-test path.
- Do not call an external integration "working" merely because its adapter imports; verify the actual runtime separately when credentials/environment are available.

## Development commands

### Backend (Python)

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
python -m pytest tests/ -v --cov
ruff check .
ruff format --check .
```

### Frontend

```bash
cd desktop
npm install
npm run test
npm run lint
npx tsc --noEmit
npm run build
```

## Coding conventions

### Commits
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `perf:`, `chore:`, `test:`
- Imperative mood.
- Use `feat/`, `fix/`, or `docs/` branches when branches are used.

### Python
PEP 8, 120-character lines, double quotes, Ruff formatting, and type hints on all function signatures.

### TypeScript
Strict mode, named exports, grouped imports, and the existing project lint/type-check configuration.

## Important API/testing notes

`desktop/api_server.py` uses Quart and has module-level initialization. Tests that import it must patch the documented dependencies before import. Persistence uses JSON files.

See `ARCHITECTURE_COMPONENTS.md` for the authoritative lifecycle map.
