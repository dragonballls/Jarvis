# Mark 53 boundary

Mark 53 is a deliberately separate application/component.

Jarvis may call Mark 53 through `mark53.bridge.Mark53Bridge` when
`JARVIS_MARK53_URL` is configured. The bridge is read-only and owns no Mark 53
files, executable, updater, or startup configuration.

Do not place Mark 53 source code, binaries, or updater logic in the Jarvis
self-coding workspace.
