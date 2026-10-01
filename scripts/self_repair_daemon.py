from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPO = "dragonballls/Friday"
INTERVAL = max(30, int(os.environ.get("FRIDAY_REPAIR_INTERVAL", "120")))
MAX_ATTEMPTS = max(1, int(os.environ.get("FRIDAY_REPAIR_MAX_ATTEMPTS", "8")))
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def run(*args: str, check: bool = False, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=check)


def gh(*args: str, check: bool = False, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("gh") or (r"C:\Program Files\GitHub CLI\gh.exe" if os.name == "nt" else "gh")
    return subprocess.run([exe, *args], cwd=ROOT, text=True, capture_output=True, timeout=timeout, check=check)


def log(message: str) -> None:
    print(f"[Friday self-repair] {message}", flush=True)


def latest_failed_run() -> dict | None:
    result = gh("run", "list", "--repo", REPO, "--limit", "10", "--json", "databaseId,headBranch,status,conclusion,name,event", check=False)
    if result.returncode != 0:
        return None
    try:
        runs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    for item in runs:
        if item.get("status") == "completed" and item.get("conclusion") == "failure" and item.get("headBranch") == "main":
            return item
    return None


def ask_cloud_agent(failure: str) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        log("OPENROUTER_API_KEY is not configured; waiting without modifying the repository.")
        return None
    prompt = (
        "You are Friday's cloud repair engineer. Diagnose the supplied CI failure and return only a unified diff. "
        "Never modify main directly. Preserve functionality and security boundaries. Do not use Ollama.\n\n"
        f"CI FAILURE:\n{failure[:40000]}"
    )
    payload = json.dumps({
        "model": os.environ.get("FRIDAY_REPAIR_MODEL", "openai/gpt-5-mini"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }).encode("utf-8")
    request = Request(OPENROUTER_URL, data=payload, headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/dragonballls/Friday",
        "X-Title": "Friday Self Repair",
    }, method="POST")
    try:
        with urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        log(f"cloud repair request failed: {exc}")
        return None


def apply_patch(text: str) -> bool:
    if "```diff" not in text:
        return False
    diff = text.split("```diff", 1)[1].split("```", 1)[0].strip() + "\n"
    patch = ROOT / ".friday-repair.patch"
    patch.write_text(diff, encoding="utf-8")
    try:
        return run("git", "apply", "--3way", str(patch)).returncode == 0
    finally:
        patch.unlink(missing_ok=True)


def repair_once(run_info: dict, attempt: int) -> bool:
    branch = f"friday/self-repair-{run_info['databaseId']}-{attempt}"
    run("git", "fetch", "origin", "main", "--prune")
    run("git", "switch", "--create", branch, "origin/main")
    failure = gh("run", "view", str(run_info["databaseId"]), "--repo", REPO, "--log-failed", check=False, timeout=300)
    answer = ask_cloud_agent(failure.stdout + failure.stderr)
    if not answer or not apply_patch(answer):
        run("git", "switch", "main")
        return False
    tests = run("python", "-m", "pytest", "tests", "-q", timeout=900)
    if tests.returncode != 0:
        run("git", "reset", "--hard", "origin/main")
        run("git", "switch", "main")
        return False
    run("git", "add", "-A", check=True)
    run("git", "commit", "-m", f"fix: automated Friday self-repair {run_info['databaseId']}-{attempt}", check=True)
    if run("git", "push", "--set-upstream", "origin", branch, timeout=300).returncode != 0:
        run("git", "switch", "main")
        return False
    pr = gh("pr", "create", "--repo", REPO, "--base", "main", "--head", branch, "--title", f"Friday self-repair {run_info['databaseId']}-{attempt}", "--body", "Automated cloud repair. Local tests passed; main is never modified directly.", check=False)
    run("git", "switch", "main")
    return pr.returncode == 0


def main() -> int:
    log(f"continuous monitor active; interval={INTERVAL}s; max attempts={MAX_ATTEMPTS}")
    handled: set[int] = set()
    while True:
        try:
            failed = latest_failed_run()
            if failed:
                run_id = int(failed["databaseId"])
                if run_id not in handled:
                    handled.add(run_id)
                    for attempt in range(1, MAX_ATTEMPTS + 1):
                        if repair_once(failed, attempt):
                            log(f"repair PR created for run {run_id}")
                            break
            time.sleep(INTERVAL)
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            log(f"monitor error: {exc}")
            time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
