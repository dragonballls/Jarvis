"""Minimal local API for Jarvis: conversation, self-coding, provider settings, and voice."""

import argparse
import asyncio
import json
import os
import re
import sys
from functools import wraps
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quart import Quart, Response, jsonify, make_response, request
from quart_cors import cors

from agent.core import Agent
from agent.evolution import run_evolution_cycle
from agent.self_coding_runtime import is_self_coding_goal
from desktop.provider_credentials import PROVIDERS, delete_key, get_key, public_status, save_key

API_PREFIX = "/api/v1"
MINIMAL_MODE = True
_API_SECRET = os.environ.get("API_SECRET", "")
_MAX_MESSAGE_LENGTH = 10_000
_MAX_TTS_LENGTH = 8_000
_DEFAULT_TTS_VOICE_ID = "6WwXjDDEMyNmFG95zycZ"
_DEFAULT_TTS_MODEL = "eleven_v3_conversational"
_TTS_FALLBACK_MODEL = "eleven_flash_v2_5"


def require_auth(f):
    @wraps(f)
    async def wrapper(*args, **kwargs):
        if _API_SECRET and request.headers.get("X-API-Key", "") != _API_SECRET:
            return jsonify({"error": "Unauthorized"}), 401
        return await f(*args, **kwargs)
    return wrapper


def validate_chat_input(data: dict) -> str | None:
    msg = data.get("message", "")
    if not isinstance(msg, str):
        return "message must be a string"
    if not msg.strip():
        return "message cannot be empty"
    if len(msg) > _MAX_MESSAGE_LENGTH:
        return f"message exceeds {_MAX_MESSAGE_LENGTH} characters"
    return None


def validate_workspace(path: str | None) -> str | None:
    if not path:
        return None
    if ".." in path or path.startswith("~"):
        return "invalid workspace path"
    return None


def run_coding_agent(workspace: str | Path, goal: str):
    """Backward-compatible self-coding entry point used by integrations/tests."""
    return run_evolution_cycle(Path(workspace), goal)


def _tts_voice_id() -> str:
    return os.environ.get("JARVIS_TTS_VOICE_ID", _DEFAULT_TTS_VOICE_ID).strip() or _DEFAULT_TTS_VOICE_ID


def _tts_model_id() -> str:
    return os.environ.get("JARVIS_TTS_MODEL_ID", _DEFAULT_TTS_MODEL).strip() or _DEFAULT_TTS_MODEL


def _tts_float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return min(max(float(raw), minimum), maximum)
    except ValueError:
        return default


def _prepare_tts_text(text: str, model_id: str | None = None) -> str:
    """Shape ordinary assistant text for calm, precise British-assistant delivery."""
    value = re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()
    if not value:
        return value
    replacements = {
        r"\bAI\b": "A.I.",
        r"\bAPI\b": "A.P.I.",
        r"\bGPU\b": "G.P.U.",
        r"\bCPU\b": "C.P.U.",
        r"\bUI\b": "U.I.",
        r"\bURL\b": "U.R.L.",
        r"\bSSH\b": "S.S.H.",
        r"\bGitHub\b": "GitHub",
    }
    for pattern, replacement in replacements.items():
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\s*[;]\s*", "; ", value)
    # Eleven v3 Conversational accepts natural-language audio tags. Keep them sparse so
    # the assistant stays composed rather than sounding theatrically over-directed.
    if model_id == "eleven_v3_conversational":
        lowered = value.lower()
        if any(marker in lowered for marker in ("warning:", "critical:", "danger:", "error:")):
            value = f"[serious] {value}"
        elif value.endswith("?"):
            value = f"[curious] {value}"
    return value


app = Quart(__name__)
app = cors(app, allow_origin={"http://localhost:5173", "http://127.0.0.1:5173"}, allow_methods={"GET", "POST", "DELETE", "OPTIONS"}, allow_headers={"Content-Type", "X-API-Key"}, allow_credentials=True)
_agents: dict[str, Agent] = {}


def get_agent(session_id: str = "default") -> Agent:
    if session_id not in _agents:
        _agents[session_id] = Agent(persona="jarvis")
    return _agents[session_id]


@app.before_request
async def reject_non_core_api():
    if request.method == "OPTIONS":
        return None
    allowed = {f"{API_PREFIX}/chat", f"{API_PREFIX}/autopilot", f"{API_PREFIX}/health", f"{API_PREFIX}/providers", f"{API_PREFIX}/providers/test", f"{API_PREFIX}/voice/status", f"{API_PREFIX}/voice/synthesize"}
    if request.path.startswith(API_PREFIX) and request.path not in allowed and not request.path.startswith(f"{API_PREFIX}/providers/"):
        return jsonify({"error": "Disabled in minimal Jarvis mode"}), 404
    return None


@app.route(f"{API_PREFIX}/chat", methods=["POST"])
@require_auth
async def chat():
    data = await request.get_json() or {}
    err = validate_chat_input(data)
    if err:
        return jsonify({"error": err}), 422
    user_input = data["message"]
    session_id = str(data.get("session_id", "default"))
    agent = get_agent(session_id)

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        def run_agent():
            try:
                for event in agent.run(user_input):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "done", "content": f"Error: {exc}", "final": True})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)
        executor.submit(run_agent)
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300)
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            executor.shutdown(wait=False)
    response = await make_response(generate())
    response.headers["Content-Type"] = "text/event-stream; charset=utf-8"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.timeout = None
    return response


@app.route(f"{API_PREFIX}/autopilot", methods=["POST"])
@require_auth
async def autopilot():
    data = await request.get_json() or {}
    goal = str(data.get("goal", "")).strip()
    if not goal:
        return jsonify({"error": "goal is required"}), 422
    workspace = data.get("workspace") or os.getenv("JARVIS_WORKSPACE") or os.getenv("FRIDAY_WORKSPACE")
    workspace_error = validate_workspace(workspace)
    if workspace_error:
        return jsonify({"error": workspace_error}), 422
    session_id = str(data.get("session_id", "default"))
    agent = get_agent(session_id)

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        import concurrent.futures
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        def run_agent():
            try:
                if is_self_coding_goal(goal):
                    if not workspace:
                        events = iter([{"type": "error", "content": "Self-coding requires an explicit workspace path.", "final": True}])
                    else:
                        events = run_coding_agent(workspace, goal)
                else:
                    events = agent.run_autopilot(goal, workspace)
                for event in events:
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "done", "content": f"Self-coding error: {exc}", "final": True})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)
        executor.submit(run_agent)
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=1200)
                if event is None:
                    break
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            executor.shutdown(wait=False)
    response = await make_response(generate())
    response.headers["Content-Type"] = "text/event-stream; charset=utf-8"
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.timeout = None
    return response


@app.route(f"{API_PREFIX}/providers", methods=["GET", "POST"])
@require_auth
async def providers():
    if request.method == "GET":
        return jsonify({"providers": public_status()})
    data = await request.get_json() or {}
    provider = str(data.get("provider", "")).strip()
    api_key = str(data.get("api_key", "")).strip()
    if provider not in PROVIDERS:
        return jsonify({"error": "Unsupported provider"}), 422
    if not api_key:
        return jsonify({"error": "API key cannot be empty"}), 422
    try:
        save_key(provider, api_key)
    except (OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"success": True, "provider": provider, "configured": True})


@app.route(f"{API_PREFIX}/providers/<provider>", methods=["DELETE"])
@require_auth
async def remove_provider(provider: str):
    provider = provider.strip()
    if provider not in PROVIDERS:
        return jsonify({"error": "Unsupported provider"}), 422
    try:
        delete_key(provider)
    except (OSError, RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"success": True, "provider": provider, "configured": False})


@app.route(f"{API_PREFIX}/providers/test", methods=["POST"])
@require_auth
async def test_providers():
    from providers import get_provider
    results = []
    for status in public_status():
        provider = status["id"]
        if not status["configured"]:
            results.append({"provider": provider, "configured": False, "ready": False})
            continue
        try:
            if provider == "elevenlabs":
                results.append({"provider": provider, "configured": True, "ready": True, "kind": "tts"})
            else:
                get_provider(str(provider))
                results.append({"provider": provider, "configured": True, "ready": True})
        except Exception as exc:
            results.append({"provider": provider, "configured": True, "ready": False, "error": str(exc)})
    return jsonify({"providers": results})


@app.route(f"{API_PREFIX}/voice/status")
@require_auth
async def voice_status():
    configured = bool(os.environ.get("ELEVENLABS_API_KEY", "").strip() or get_key("elevenlabs"))
    model_id = _tts_model_id()
    return jsonify({
        "provider": "elevenlabs",
        "configured": configured,
        "voice_id_configured": bool(_tts_voice_id()),
        "voice_id": _tts_voice_id(),
        "voice_name": "Eldrin - Crisp British Baritone",
        "model_id": model_id,
        "fallback_model_id": _TTS_FALLBACK_MODEL,
        "fallback": "browser-speech-synthesis",
        "voice_profile": "calm, precise, restrained British baritone",
    })


@app.route(f"{API_PREFIX}/voice/synthesize", methods=["POST"])
@require_auth
async def voice_synthesize():
    data = await request.get_json() or {}
    text = data.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text is required"}), 422

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip() or get_key("elevenlabs")
    if not api_key:
        return jsonify({"error": "ElevenLabs is not configured"}), 503

    import urllib.error
    import urllib.parse
    import urllib.request

    primary_model = _tts_model_id()
    models_to_try = [primary_model]
    if primary_model != _TTS_FALLBACK_MODEL:
        models_to_try.append(_TTS_FALLBACK_MODEL)

    last_detail = "ElevenLabs request failed"
    for index, model_id in enumerate(models_to_try):
        prepared_text = _prepare_tts_text(text, model_id)
        model_limit = 5_000 if model_id == "eleven_v3" else _MAX_TTS_LENGTH
        if len(prepared_text) > model_limit:
            return jsonify({"error": f"text exceeds {model_limit} characters for {model_id}"}), 422

        stability = _tts_float_env("JARVIS_TTS_STABILITY", 0.58, 0.0, 1.0)
        similarity = _tts_float_env("JARVIS_TTS_SIMILARITY", 0.88, 0.0, 1.0)
        style = _tts_float_env("JARVIS_TTS_STYLE", 0.06, 0.0, 1.0)
        speed = _tts_float_env("JARVIS_TTS_SPEED", 0.95, 0.7, 1.2)
        voice_settings = {
            "stability": stability,
            "similarity_boost": similarity,
            "style": style,
            "use_speaker_boost": True,
            "speed": speed,
        }
        payload = json.dumps({"text": prepared_text, "model_id": model_id, "voice_settings": voice_settings}).encode("utf-8")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{urllib.parse.quote(_tts_voice_id(), safe='')}?output_format=mp3_44100_128"
        req = urllib.request.Request(url, data=payload, method="POST", headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        try:
            with urllib.request.urlopen(req, timeout=30) as upstream:
                audio = upstream.read()
            if not audio:
                raise OSError("ElevenLabs returned empty audio")
            response = Response(audio, mimetype="audio/mpeg")
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Jarvis-TTS-Model"] = model_id
            response.headers["X-Jarvis-TTS-Profile"] = "expressive-realtime"
            if index > 0:
                response.headers["X-Jarvis-TTS-Fallback"] = "true"
            return response
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = "ElevenLabs request failed"
            last_detail = detail[:500]
            # A model/voice capability error should automatically recover to Flash 2.5.
            if index == 0 and exc.code not in {400, 404, 405, 415, 422}:
                return jsonify({"error": last_detail}), 502
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return jsonify({"error": f"ElevenLabs request failed: {exc}"}), 502

    return jsonify({"error": last_detail}), 502


@app.route(f"{API_PREFIX}/health")
async def health():
    from agent.openhands_runtime import openhands_available
    return jsonify({"status": "ok", "mode": "minimal", "features": ["conversation", "self_coding", "provider_settings", "voice", "openhands", "emrg_evolution"], "engines": {"openhands": openhands_available(), "opencode": True}, "name": "Jarvis"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port)