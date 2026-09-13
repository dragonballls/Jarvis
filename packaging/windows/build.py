from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "windows"
DIST = ROOT / "desktop" / "dist"
# Package the real Windows runtime entry point. native_app.py was a minimal
# fallback shell and could produce the old bare-bones desktop experience.
ENTRY = ROOT / "packaging" / "windows" / "app.py"

# Jarvis's desktop runtime serves the already-built production frontend from
# desktop/dist. That bundle must be embedded in the single-file executable;
# otherwise the frozen app starts correctly but fails its UI smoke test because
# _MEIPASS/desktop/dist does not exist.
DIST_SEPARATOR = ";"

# Jarvis is a cloud-first assistant. These optional local-ML stacks are not
# required by the packaged chat/self-coding runtime and can make PyInstaller
# consume several GB of RAM while analyzing the dependency graph.
OPTIONAL_LOCAL_ML = (
    "sentence_transformers", "sentence_transformers.*", "torch", "torch.*",
    "transformers", "transformers.*", "scipy", "scipy.*", "pandas", "pandas.*",
    "sklearn", "sklearn.*", "tensorflow", "tensorflow.*", "keras", "keras.*",
    "matplotlib", "matplotlib.*", "nltk", "nltk.*", "IPython", "IPython.*",
    "sympy", "sympy.*", "pkg_resources",
)


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
        text=True, check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "dev"


def jarvis_pyinstaller_args(name: str, windowed: bool, onefile: bool, distpath: Path, workpath: Path) -> list[str]:
    args = [
        "pyinstaller", "--noconfirm", "--clean",
        "--windowed" if windowed else "--console",
        "--name", name, "--onefile" if onefile else "--onedir",
        "--distpath", str(distpath), "--workpath", str(workpath),
        "--paths", str(ROOT),
        "--collect-submodules", "agent",
        "--collect-submodules", "integrations",
        "--collect-submodules", "plugins",
        "--collect-submodules", "providers",
        "--collect-submodules", "openhands.sdk",
        "--collect-submodules", "openhands.tools",
        "--collect-submodules", "emrg",
        "--hidden-import", "openhands.sdk",
        "--hidden-import", "openhands.tools",
        "--hidden-import", "openhands.tools.file_editor",
        "--hidden-import", "openhands.tools.task_tracker",
        "--hidden-import", "openhands.tools.terminal",
        "--hidden-import", "emrg",
        "--hidden-import", "desktop.api_server",
        "--hidden-import", "desktop",
        "--hidden-import", "webview",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.font",
        # Critical: the real production frontend must travel inside the frozen
        # executable at desktop/dist so app.py can serve it after extraction.
        "--add-data", f"{DIST}{DIST_SEPARATOR}desktop/dist",
    ]

    if (ROOT / "prompts").exists():
        args += ["--add-data", f"{ROOT / 'prompts'}{DIST_SEPARATOR}prompts"]
    args.append(str(ENTRY))
    for module in OPTIONAL_LOCAL_ML:
        args += ["--exclude-module", module]
    return args


def main() -> None:
    if not DIST.joinpath("index.html").is_file():
        raise SystemExit("desktop/dist/index.html is missing; run npm run build first")
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True, exist_ok=True)
    exe = BUILD / "Jarvis.exe"
    run(*jarvis_pyinstaller_args("Jarvis", True, True, BUILD, ROOT / "build" / "pyinstaller-work"))
    if not exe.is_file():
        raise SystemExit(f"PyInstaller did not create {exe}")
    (BUILD / "VERSION").write_text(current_commit() + "\n", encoding="utf-8")
    print(f"Windows Jarvis app ready: {exe}")


if __name__ == "__main__":
    main()
