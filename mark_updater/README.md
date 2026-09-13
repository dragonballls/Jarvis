# Mark updater boundary

The Mark updater is separate from both Mark 53 and Jarvis self-coding.

Responsibilities are intentionally limited to the Mark component's own
installation/release lifecycle. It must never replace `Jarvis.exe`, modify the
`Jarvis-SelfCoding-Workspace`, or change Jarvis Git history.

A future Mark updater implementation should use a Mark-specific release
manifest and installation directory rather than reusing Jarvis's updater
state.
