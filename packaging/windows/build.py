from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "windows"
DIST = ROOT / "desktop" / "dist"
ENTRY = ROOT / "packaging" / "windows" / "native_app.py"

# Jarvis is a cloud-first assistant. These optional local-ML stacks are not
# required by the packaged chat/self-coding runtime and can make PyInstaller
# consume several GB of RAM while analyzing the dependency graph.
OPTIONAL_LOCAL_ML = (
    "sentence_transformers", "sentence_transformers.*", "torch", "torch.*",
    "transformers", "transformers.*", "scipy", "scipy.*", "pandas", "pandas.*",
    "tensorflow", "tensorflow.*", "keras", "keras.*",
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
    separator = ";"
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
        "--hidden-import", "desktop.api_server",
        "--hidden-import", "desktop",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.font",
    ]

    if (ROOT / "prompts").exists():
        args += ["--add-data", f"{ROOT / 'prompts'}{separator}prompts"]
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
