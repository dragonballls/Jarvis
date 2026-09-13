# AI Agent Guide for Friday

This file instructs AI coding agents (opencode, Claude Code, Cline, Cursor, etc.) how to work effectively with this project.

## Quick Start for Agents

### Backend (Python)

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
python -m pytest tests/ -v --cov
python -m pytest tests/ --cov --cov-fail-under=50 --ignore=tests/test_api_server.py
python -m pytest tests/test_api_server.py --cov=desktop --cov-fail-under=40
ruff check .
ruff format --check .
python main.py
python desktop/api_server.py
```

### Frontend (TypeScript/React)

```bash
cd desktop
npm install
npm run test
npm run test:watch
npm run lint
npx tsc --noEmit
npm run dev
npm run build
```

## Key Conventions

### Commits
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `perf:`, `chore:`, `test:`
- Imperative mood: "add feature" not "added feature"
- Branch naming: `feat/your-feature-name`, `fix/`, `docs/`

### Code Style
- **Python:** PEP 8, line length 120, double quotes, Ruff formatter
- **TypeScript:** Strict mode, named exports, grouped imports (React -> third-party -> local)
- Use `async/await` for I/O, `asyncio.to_thread` for blocking calls
- Type hints required on all Python function signatures

## Project Structure
- `core/` — Business logic (executor, memory, proactive, automations, etc.)
- `desktop/api_server.py` — Quart REST API
- `desktop/src/` — React/TypeScript frontend
- `tests/` — Python tests
- `desktop/src/test/` — TypeScript tests
- `plugins/` — Tool plugins
- `providers/` — LLM provider abstraction

## Important Architecture Notes

### API Server (`desktop/api_server.py`)
- Uses Quart
- Module-level code runs at import time: `discover_plugins()`, `_broadcaster = EventBroadcaster()`
- Tests must patch `core.registry.discover_plugins` and `desktop.api_server._proactive` BEFORE import
- Persistence uses JSON files

### Testing
- **Backend:** pytest with `pytest-asyncio` strict mode
- **Frontend:** Vitest with jsdom environment and Testing Library
- Python test methods must use `@pytest.mark.asyncio` where required by strict mode

### Linting
- Python: Ruff
- TypeScript: oxlint

### LLM Providers
- Registered via `providers/registry.py`
- Default: OpenRouter; also supports OpenAI, Ollama, and OpenAI-compatible APIs
- Config via `config/providers.toml`

## Component Isolation Rule

Every current and future addition must have an identifiable component boundary. Do not combine unrelated additions into one mutable lifecycle, installer, updater, workspace, runtime state directory, or executable.

The current boundaries are:

- `mark53/` — Mark 53 integration boundary only. Read-only bridge; no Mark files, binaries, updater state, or startup management.
- `mark_updater/` — Mark 53 updater boundary only. Never updates Jarvis or its self-coding workspace.
- `self_coding/` — Jarvis self-coding facade only. Never replaces `Jarvis.exe` directly.
- `agent/` OpenHands/OpenCode execution — coding engines only; operate through the self-coding boundary.
- `core/` EMRG evolution logic — bounded evolution/verification only; do not merge updater responsibilities into it.
- `integrations/gods_eye/` and related God's Eye bridge/context files — God's Eye only.
- `providers/`, `config/`, and `core/blackout.py` — provider/routing/privacy behavior only.
- `scripts/update.py` — Jarvis source/release updater only.
- `packaging/windows/` — Windows packaging and executable lifecycle only.

A new feature must get its own named directory or explicit subsystem boundary plus component-specific tests. Its errors should identify the component name. Coordination is allowed only through narrow interfaces.

Never make one component responsible for replacing, deleting, or modifying another component's installation, executable, Git checkout, updater manifest, or persistent state.

See `ARCHITECTURE_COMPONENTS.md` for the authoritative component lifecycle map.

## Common Tasks

### Adding an API endpoint
1. Define route in `desktop/api_server.py`
2. Add `@require_auth` for authenticated endpoints
3. Add validation helpers
4. Write tests

### Adding a tool
1. Create a plugin class in `plugins/builtins/` or a standalone function in `tools/`
2. Ensure discovery behavior is preserved
3. Write tests

### Adding a frontend component
1. Create the component in `desktop/src/components/<category>/`
2. Add types in `desktop/src/types/index.ts`
3. Write tests in `desktop/src/test/`
4. Use Zustand from `desktop/src/core/`
