from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Mark53Config:
    """Connection-only configuration for the external Mark 53 service."""

    base_url: str

    @classmethod
    def from_environment(cls) -> Mark53Config | None:
        value = os.getenv("JARVIS_MARK53_URL", "").strip().rstrip("/")
        return cls(value) if value else None


class Mark53Bridge:
    """Small, read-only bridge between Jarvis and an external Mark 53 runtime.

    This class intentionally has no filesystem or process-management powers.
    Mark 53 remains independently installable, updateable, and testable.
    """

    def __init__(self, config: Mark53Config) -> None:
        if not config.base_url.startswith(("http://", "https://")):
            raise ValueError("Mark 53 URL must use HTTP or HTTPS")
        self._config = config

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def health(self, timeout: float = 3.0) -> dict[str, object]:
        request = Request(
            f"{self.base_url}/health",
            headers={"User-Agent": "Jarvis-Mark53-Bridge/1.0", "Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                return {"ok": False, "error": "Mark 53 health response was not an object"}
            return {"ok": True, "data": payload}
        except (OSError, URLError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}


def mark53_enabled() -> bool:
    return Mark53Config.from_environment() is not None
