from __future__ import annotations

"""Discover remote AI authentication without exposing credentials.

This utility is deliberately passive: it reports which provider credential
sources appear to exist and delegates actual authentication/model selection to
OpenCode. It never prints secret values and never attempts to obtain or bypass
credentials.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

# Environment variables commonly used by remote providers. Presence only.
PROVIDER_ENV = {
    "OpenAI": ("OPENAI_API_KEY",),
    "Anthropic": ("ANTHROPIC_API_KEY",),
    "Google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "Groq": ("GROQ_API_KEY",),
    "OpenRouter": ("OPENROUTER_API_KEY",),
    "Mistral": ("MISTRAL_API_KEY",),
    "Cerebras": ("CEREBRAS_API_KEY",),
    "xAI": ("XAI_API_KEY",),
    "Z.AI": ("ZAI_API_KEY",),
}


def _opencode_auth_paths() -> list[Path]:
    home = Path.home()
    candidates = [
        home / ".local" / "share" / "opencode" / "auth.json",
        home / ".config" / "opencode" / "auth.json",
        Path(os.environ.get("LOCALAPPDATA", "")) / "opencode" / "auth.json",
    ]
    seen: set[Path] = set()
    return [p for p in candidates if str(p) and not (p in seen or seen.add(p))]


def env_candidates() -> dict[str, bool]:
    return {name: any(bool(os.environ.get(key)) for key in keys) for name, keys in PROVIDER_ENV.items()}


def opencode_auth_providers() -> list[str]:
    providers: set[str] = set()
    for path in _opencode_auth_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if isinstance(data, dict):
            providers.update(str(k) for k in data if isinstance(k, str))
    return sorted(providers)


def opencode_available() -> bool:
    return shutil.which("opencode") is not None or shutil.which("opencode.cmd") is not None


def opencode_auth_list() -> str | None:
    command = shutil.which("opencode") or shutil.which("opencode.cmd")
    if not command:
        return None
    try:
        result = subprocess.run(
            [command, "auth", "list"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # Never return the raw output because providers can render credential data.
    return "available" if result.returncode == 0 else f"error:{result.returncode}"


def main() -> int:
    print("Jarvis remote-provider bootstrap")
    print(f"OpenCode executable: {'yes' if opencode_available() else 'no'}")
    print(f"OpenCode auth command: {opencode_auth_list() or 'unavailable'}")
    print("Environment credential sources:")
    for name, present in env_candidates().items():
        print(f"  {name}: {'present' if present else 'not detected'}")
    configured = opencode_auth_providers()
    print("OpenCode auth providers: " + (", ".join(configured) if configured else "none detected"))
    print("No local model is selected by this utility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
