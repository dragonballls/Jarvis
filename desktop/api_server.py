"""Minimal local API for Jarvis: conversation and self-coding only."""

import argparse
import asyncio
import json
import os
import sys
from functools import wraps
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quart import Quart, jsonify, make_response, request
from quart_cors import cors

from agent.core import Agent
from agent.evolution import run_evolution_cycle
from agent.self_coding_runtime import is_self_coding_goal

API_PREFIX = "/api/v1"
MINIMAL_MODE = True
_API_SECRET = os.environ.get("API_SECRET", "")
_MAX_MESSAGE_LENGTH = 10_000


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


app = Quart(__name__)
app = cors(
    app,
    allow_origin={"http://localhost:5173", "http://127.0.0.1:5173"},
    allow_methods={"GET", "POST", "OPTIONS"},
    allow_headers={"Content-Type", "X-API-Key"},
    allow_credentials=True,
)

_agents: dict[str, Agent] = {}


def get_agent(session_id: str = "default") -> Agent:
    if session_id not in _agents:
        _agents[session_id] = Agent(persona="jarvis")
    return _agents[session_id]


@app.before_request
async def reject_non_core_api():
    if request.method == "OPTIONS":
        return None
    allowed = {
        f"{API_PREFIX}/chat",
        f"{API_PREFIX}/autopilot",
        f"{API_PREFIX}/health",
    }
    if request.path.startswith(API_PREFIX) and request.path not in allowed:
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
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "done", "content": f"Error: {exc}", "final": True},
                )
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
                        events = iter(
                            [
                                {
                                    "type": "error",
                                    "content": "Self-coding requires an explicit workspace path.",
                                    "final": True,
                                }
                            ]
                        )
                    else:
                        events = run_evolution_cycle(Path(workspace), goal)
                else:
                    events = agent.run_autopilot(goal, workspace)
                for event in events:
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as exc:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "done", "content": f"Self-coding error: {exc}", "final": True},
                )
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


@app.route(f"{API_PREFIX}/health")
async def health():
    from agent.openhands_runtime import openhands_available
    return jsonify(
        {
            "status": "ok",
            "mode": "minimal",
            "features": ["conversation", "self_coding", "openhands", "emrg_evolution"],
            "engines": {
                "openhands": openhands_available(),
                "opencode": True,
            },
            "name": "Jarvis",
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port)