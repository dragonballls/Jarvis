# Component boundaries

Jarvis uses four deliberately separate lifecycles.

## 1. Mark 53

Location: `mark53/`

Mark 53 is an external component. Jarvis communicates with it only through
`mark53.bridge`. The bridge is connection-only and read-only. It must not edit
Mark 53 files, binaries, startup entries, or updater state.

## 2. Mark updater

Location: `mark_updater/`

The Mark updater owns only the Mark 53 release/update lifecycle. It must never
replace `Jarvis.exe`, update the Jarvis Git checkout, or modify the Jarvis
self-coding workspace.

## 3. Jarvis self-coding

Location: `self_coding/` plus the existing `agent/` coding engines.

Self-coding is responsible only for making bounded, verified source changes in
the dedicated `Jarvis-SelfCoding-Workspace`. OpenHands is preferred and
OpenCode is the fallback execution engine. Self-coding does not replace the
running executable directly.

## 4. Jarvis Windows updater

Location: `scripts/update.py` and `packaging/windows/app.py`.

The Jarvis updater owns only verified Jarvis release installation. It fetches a
matching Windows build, verifies its commit and optional SHA-256 digest, stages
the replacement, and restarts Jarvis. It does not update Mark 53.

## Coordination

The components can work together through narrow interfaces:

`Jarvis chat -> self-coding -> GitHub main -> Jarvis Windows updater`

and, independently:

`Jarvis -> Mark 53 bridge -> external Mark 53`

with:

`Mark 53 -> Mark updater -> Mark 53 installation`

No component should share a mutable installation directory, executable,
Git checkout, updater manifest, or runtime state with another component.
