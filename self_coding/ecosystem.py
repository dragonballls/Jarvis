from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import quote
from urllib.request import Request, urlopen

GITHUB_API = "https://api.github.com/search/repositories"
MAX_RESULTS = 6


def _queries(goal: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_-]{3,}", goal.lower())
    useful = [t for t in terms if t not in {"the", "and", "for", "with", "that", "this", "from", "safe", "jarvis"}]
    seeds = ["autonomous coding agent", "AI assistant agent", "self improving agent", "OpenHands coding agent", "browser automation agent"]
    if useful:
        seeds.insert(0, " ".join(useful[:5]) + " AI agent")
    return seeds[:5]


def _search(query: str) -> list[dict]:
    url = f"{GITHUB_API}?q={quote(query)}&sort=stars&order=desc&per_page={MAX_RESULTS}"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Jarvis-Ecosystem-Discovery/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    return payload.get("items", []) if isinstance(payload, dict) else []


def discover(goal: str) -> list[dict[str, str | int | bool]]:
    """Find promising public repositories without executing or importing them."""
    seen: set[str] = set()
    results: list[dict[str, str | int | bool]] = []
    for query in _queries(goal):
        for item in _search(query):
            full_name = str(item.get("full_name") or "")
            if not full_name or full_name.lower() == "dragonballls/jarvis" or full_name.lower() in seen:
                continue
            seen.add(full_name.lower())
            license_name = ""
            license_data = item.get("license")
            if isinstance(license_data, dict):
                license_name = str(license_data.get("spdx_id") or license_data.get("name") or "")
            results.append(
                {
                    "full_name": full_name,
                    "html_url": str(item.get("html_url") or ""),
                    "description": str(item.get("description") or ""),
                    "stars": int(item.get("stargazers_count") or 0),
                    "fork": bool(item.get("fork")),
                    "license": license_name,
                }
            )
            if len(results) >= MAX_RESULTS:
                return results
    return results


def format_report(results: Iterable[dict]) -> str:
    lines = [
        "External ecosystem discovery results:",
        "These repositories are references only. Do not execute untrusted repository code.",
    ]
    for result in results:
        lines.append(
            f"- {result.get('full_name')} | stars={result.get('stars', 0)} | "
            f"fork={result.get('fork', False)} | license={result.get('license') or 'unknown'} | "
            f"{result.get('html_url')} | {result.get('description') or 'no description'}"
        )
    return "\n".join(lines)
