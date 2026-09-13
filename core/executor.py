import json
import os
from collections.abc import Generator
from typing import Any

from core.logger import Timer, error, warn
from core.planner import Task
from core.security import get_approval_registry, get_permission_manager


class Executor:
    def __init__(self, llm_provider, tool_map: dict[str, Any], confirm_timeout: float = 120.0):
        self._llm = llm_provider
        self._tool_map = tool_map
        self.output_dir: str | None = None
        self.confirm_timeout = confirm_timeout

    def execute_task(
        self,
        task: Task,
        messages: list[dict],
        tool_definitions: list[dict],
        max_iterations: int = 10,
    ) -> Generator[dict, None, None]:
        task.status = "running"
        task_messages = list(messages)
        task_instruction = str(getattr(task, "description", "")).strip()
        task_args = getattr(task, "args", {})
        if task_args:
            task_instruction += "\n\nRequired tool arguments:\n" + json.dumps(task_args, ensure_ascii=False)
        if task_instruction:
            task_messages.append({"role": "user", "content": task_instruction})
        elif not any(isinstance(m, dict) and m.get("role") == "user" for m in task_messages):
            task_messages.append({"role": "user", "content": "Execute this task now."})
        yield from self._react_loop(task_messages, tool_definitions, max_iterations, task)

    def _react_loop(
        self,
        messages: list[dict],
        tool_definitions: list[dict],
        max_iterations: int,
        task: Task,
    ) -> Generator[dict, None, None]:
        try:
            yield from self._react_loop_impl(messages, tool_definitions, max_iterations, task)
        except Exception as e:
            error(f"Unhandled exception in _react_loop: {e}", exc_info=True)
            task.status = "failed"
            task.error = str(e)
            yield {"type": "done", "content": f"Error: {e}"}

    def _react_loop_impl(
        self,
        messages: list[dict],
        tool_definitions: list[dict],
        max_iterations: int,
        task: Task,
    ) -> Generator[dict, None, None]:
        coding_tools = {
            "write_file",
            "run_tests",
            "review_code_change",
            "app_coding_checkpoint",
            "run_format",
            "run_lint",
            "verify_coding_change",
        }
        implementation_tools = {"write_file"}
        description = str(getattr(task, "description", "")).lower()
        is_coding_task = (
            getattr(task, "tool", None) in coding_tools
            or "coding" in description
            or "edit " in description
            or "change " in description
            or "modify " in description
            or "rewrite " in description
            or "update " in description
            or "implement " in description
            or "add " in description
            or "create " in description
            or "refactor " in description
            or "fix " in description
        )
        coding_tool_executed = False
        implementation_executed = False
        verification_passed = False

        for iteration in range(max_iterations):
            collected = ""
            tool_calls = None

            provider_error = None

            for event in self._llm(messages, tools=tool_definitions):
                event_type = event.get("type")

                if event_type == "tokens":
                    collected += event.get("content", "")
                    yield event

                elif event_type == "error":
                    provider_error = event.get("error") or event.get("content") or "Provider error"
                    yield event

                elif event_type == "done":
                    collected = event.get("content", "")
                    tool_calls = event.get("tool_calls") or []

                    if not tool_calls and isinstance(collected, str) and collected.startswith("Error:"):
                        provider_error = collected

            if provider_error:
                task.status = "failed"
                task.error = str(provider_error)
                yield {
                    "type": "done",
                    "content": str(provider_error),
                    "final": True,
                }
                return

            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": collected,
                        "tool_calls": tool_calls,
                    }
                )

                tool_summary = []
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        result = {"error": "Invalid tool call: expected an object"}
                        tool_summary.append({"name": "unknown", "args": "", "result": json.dumps(result)})
                        continue

                    function = tc.get("function")
                    if not isinstance(function, dict):
                        result = {"error": "Invalid tool call: missing function object"}
                        tool_summary.append({"name": "unknown", "args": "", "result": json.dumps(result)})
                        continue

                    func_name = function.get("name")
                    if not isinstance(func_name, str) or not func_name:
                        result = {"error": "Invalid tool call: missing function name"}
                        tool_summary.append({"name": "unknown", "args": "", "result": json.dumps(result)})
                        continue

                    tc_id = tc.get("id", "")
                    raw_args = function.get("arguments", {})
                    try:
                        if isinstance(raw_args, str):
                            args = json.loads(raw_args)
                        else:
                            args = raw_args
                    except json.JSONDecodeError as e:
                        warn(f"Failed to parse args for {func_name}: {e}")
                        result = {"error": f"Invalid tool arguments: {e}"}
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )
                        tool_summary.append(
                            {"name": func_name, "args": "", "result": json.dumps(result, ensure_ascii=False)[:300]}
                        )
                        continue

                    if not isinstance(args, dict):
                        result = {"error": "Invalid tool arguments: expected a JSON object"}
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": json.dumps(result, ensure_ascii=False),
                            }
                        )
                        tool_summary.append(
                            {"name": func_name, "args": "", "result": json.dumps(result, ensure_ascii=False)[:300]}
                        )
                        continue

                    if self.output_dir and func_name == "write_file" and "path" in args:
                        p = args["path"]
                        if isinstance(p, str) and not os.path.isabs(p):
                            args["path"] = os.path.join(self.output_dir, p)

                    handler = self._tool_map.get(func_name)
                    if handler:
                        try:
                            with Timer(f"tool:{func_name}"):
                                result = yield from self._execute_with_confirmation(func_name, args, handler)
                            if is_coding_task and func_name in coding_tools and not result.get("error"):
                                coding_tool_executed = True
                            if (
                                is_coding_task
                                and func_name in implementation_tools
                                and not result.get("error")
                                and result.get("success", True) is not False
                            ):
                                implementation_executed = True
                            if (
                                is_coding_task
                                and func_name == "verify_coding_change"
                                and result.get("success")
                                and result.get("all_gates_passed")
                            ):
                                verification_passed = True
                        except Exception as e:
                            result = {"error": str(e)}
                    else:
                        result = {"error": f"Unknown tool: {func_name}"}

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )

                    args_str = ", ".join(f"{k}={v}" for k, v in args.items())
                    tool_summary.append(
                        {
                            "name": func_name,
                            "args": args_str,
                            "result": json.dumps(result, ensure_ascii=False)[:300],
                        }
                    )

                    if result.get("error"):
                        task.error = str(result["error"])
                        task.retries += 1

                yield {"type": "tool_result", "tools": tool_summary}
            else:
                if is_coding_task and not coding_tool_executed:
                    messages.append({"role": "assistant", "content": collected})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Do not finish this coding task with a text response. "
                                "You must actually execute the required coding tool and "
                                "make the requested change before reporting completion. "
                                "Use the available coding tools now."
                            ),
                        }
                    )
                    task.error = "Coding task attempted to finish without executing a coding tool."
                    yield {
                        "type": "verification",
                        "content": "Coding task did not execute a coding tool; continuing.",
                    }
                    continue

                if is_coding_task and (not implementation_executed or not verification_passed):
                    missing = []
                    if not implementation_executed:
                        missing.append("implementation")
                    if not verification_passed:
                        missing.append("verification")
                    task.status = "failed"
                    task.error = "Required coding gates did not pass: " + ", ".join(missing)
                    yield {
                        "type": "done",
                        "content": "Coding task failed closed: required gates did not pass ("
                        + ", ".join(missing)
                        + ").",
                        "final": True,
                    }
                    return

                messages.append({"role": "assistant", "content": collected})
                task.status = "completed"
                task.result = collected
                yield {"type": "done", "content": collected}
                return

        task.status = "failed"
        task.error = "Max iterations reached"
        yield {"type": "done", "content": "Max iterations reached."}

    def _execute_with_confirmation(self, func_name: str, args: dict, handler) -> "Generator[dict, None, dict]":
        """Run permission checks and, if required, a confirmation gate before the handler."""
        try:
            from core.blackout import is_tool_blocked

            if is_tool_blocked(func_name):
                return {"error": f"Blocked by blackout mode — '{func_name}' needs network access"}
        except ImportError:
            pass

        perm = get_permission_manager().check_tool(func_name, args)
        if not perm.get("allowed"):
            return {"error": f"Blocked by security policy: {perm.get('reason', 'denied')}"}

        if not perm.get("requires_confirmation"):
            with Timer(f"tool:{func_name}"):
                return handler(**args)

        registry = get_approval_registry()
        request_id = registry.request(func_name, args)
        yield {"type": "requires_confirmation", "request_id": request_id, "tool": func_name, "args": args}

        if registry.wait(request_id, timeout=self.confirm_timeout):
            with Timer(f"tool:{func_name}"):
                return handler(**args)
        return {"error": f"Tool call '{func_name}' cancelled by user"}

    def retry_task(
        self,
        task: Task,
        messages: list[dict],
        tool_definitions: list[dict],
    ) -> Generator[dict, None, None]:
        if task.retries >= task.max_retries:
            yield {
                "type": "tool_result",
                "tools": [
                    {
                        "name": "retry",
                        "args": f"task={task.id}",
                        "result": f"Max retries ({task.max_retries}) exceeded",
                    }
                ],
            }
            return

        previous_error = task.error or "Unknown failure"
        task.retries += 1
        task.status = "running"
        task.error = None

        messages.append(
            {
                "role": "user",
                "content": f"The previous attempt failed: {previous_error}\n\nPlease try again with a different approach.",
            }
        )
        yield from self._react_loop(messages, tool_definitions, 10, task)
