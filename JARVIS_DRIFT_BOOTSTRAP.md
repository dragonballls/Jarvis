# Jarvis on Drift

This repository is the Jarvis intelligence/workspace layer for the Drift Windows desktop.

## Hard requirements

- No Ollama, llama.cpp, or bundled/local LLM is required or selected.
- Use remote/cloud AI providers only.
- Prefer providers that are legitimately available to the user, including free tiers or existing authenticated accounts.
- Never scrape, steal, expose, or bypass another person's credentials or provider limits.
- Do not hard-code API keys into the repository.

## Bootstrap objective

When Drift opens this repository, the Jarvis agent should:

1. Inspect the workspace and current provider/auth state.
2. Detect usable remote providers and models available to OpenCode.
3. Prefer a working provider with the lowest practical cost, while preserving a stronger fallback.
4. Run a small authenticated capability check before attempting autonomous coding.
5. If no provider is usable, explain exactly what legitimate connection is missing instead of silently falling back to a local model.
6. Once a provider is working, inspect the repository, run tests, make the smallest safe improvement, verify it, and continue.
7. Keep changes auditable in Git and never publish secrets.
8. Treat the repository's tests and build checks as the gate for self-updates.

## Architecture direction

Drift is the Windows desktop shell and managed OpenCode engine. OpenCode is the remote-AI orchestration layer. This repository supplies Jarvis-specific instructions, agents, provider-bootstrap utilities, tests, and future tools. The old custom desktop/backend launcher is no longer the foundation.

The long-term Jarvis assistant can grow on top of this stable base without reimplementing the desktop, engine lifecycle, provider plumbing, or updater.
