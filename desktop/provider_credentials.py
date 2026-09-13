"""Secure local storage for Jarvis cloud-provider API keys.

Windows uses DPAPI, so credentials are encrypted for the current Windows user
and are never written to the repository or returned by the API in plaintext.
The module intentionally has no dependency on the provider/config modules to
avoid import cycles.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import tempfile
from pathlib import Path

PROVIDERS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "zen_coder": "ZEN_CODER_API_KEY",
    "groq": "GROQ_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}


def _store_path() -> Path:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(root) / "Jarvis" / "credentials.json"


if os.name == "nt":
    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DATA_BLOB)
    ]
    _crypt32.CryptProtectData.restype = ctypes.c_bool
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(_DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DATA_BLOB)
    ]
    _crypt32.CryptUnprotectData.restype = ctypes.c_bool
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def _protect(value: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Secure provider-key storage requires Windows DPAPI")
    raw = value.encode("utf-8")
    source = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    inp = _DATA_BLOB(len(raw), source)
    out = _DATA_BLOB()
    if not _crypt32.CryptProtectData(ctypes.byref(inp), "Jarvis provider key", None, None, None, 0, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
    try:
        encrypted = ctypes.string_at(out.pbData, out.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        _kernel32.LocalFree(out.pbData)


def _unprotect(value: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Secure provider-key storage requires Windows DPAPI")
    encrypted = base64.b64decode(value.encode("ascii"), validate=True)
    source = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
    inp = _DATA_BLOB(len(encrypted), source)
    out = _DATA_BLOB()
    description = ctypes.c_wchar_p()
    if not _crypt32.CryptUnprotectData(ctypes.byref(inp), ctypes.byref(description), None, None, None, 0, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        _kernel32.LocalFree(out.pbData)
        if description:
            _kernel32.LocalFree(description)


def _read() -> dict[str, str]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write(data: dict[str, str]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="credentials-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def save_key(provider: str, api_key: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    api_key = str(api_key).strip()
    if not api_key:
        raise ValueError("API key cannot be empty")
    data = _read()
    data[provider] = _protect(api_key)
    _write(data)


def delete_key(provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    data = _read()
    data.pop(provider, None)
    _write(data)


def get_key(provider: str) -> str:
    if provider not in PROVIDERS:
        return ""
    encrypted = _read().get(provider, "")
    if not encrypted:
        return ""
    try:
        return _unprotect(encrypted)
    except (OSError, ValueError, RuntimeError, UnicodeError):
        return ""


def configured(provider: str) -> bool:
    return bool(get_key(provider))


def public_status() -> list[dict[str, object]]:
    return [
        {"id": provider, "env_var": env_var, "configured": configured(provider)}
        for provider, env_var in PROVIDERS.items()
    ]