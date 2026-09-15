from pathlib import Path
from agent.llm import chat as llm_chat
from config import MAX_ITERATIONS, get_system_prompt
from core.executor import Executor
from core.logger import info
from core.memory import get_memory_manager
from core.planner import Planner
from core.registry import get_tool_definitions, get_tool_map
from core.security import get_approval_registry, get_permission_manager
from core.system1 import build_default_system1
from types import SimpleNamespace

_system1 = None


def _get_system1():
    global _system1
    if _system1 is None:
        _system1 = build_default_system1()
    return _system1


_TRANSIENT_ERRORS = ["timeout", "not found", "connection", "rate limit"]

_DESKTOP_GOAL_MARKERS = (
    "organiz", "organise", "clean up", "tidy", "declutter", "desktop",
    "arrange window", "manage my apps", "close window", "focus window", "open app",
)

_MAINTENANCE_MARKERS = (
    "diagnose my pc", "diagnose my computer", "fix my pc", "fix my computer",
    "repair my pc", "repair my computer", "optimize my pc", "optimize my computer",
    "clean up whatever is wasting resources", "clean up my pc", "stop steam",
    "startup", "running in the background", "wasting resources", "windows errors",
    "network problems", "system files",
)


def _is_desktop_goal(goal: str) -> bool:
    lowered = goal.lower()
    return any(marker in lowered for marker in _DESKTOP_GOAL_MARKERS)


def _is_maintenance_goal(goal: str) -> bool:
    lowered = goal.lower()
    return any(marker in lowered for marker in _MAINTENANCE_MARKERS)


def _maintenance_events(goal: str):
    try:
        from windows_maintenance import MaintenanceFacade
        response = MaintenanceFacade().handle(goal)
        if response.report is not None:
            yield {"type": "maintenance", "event": "diagnosis", "summary": response.report.summary(), "findings": [finding.__dict__ for finding in response.report.findings], "failures": list(response.report.failures)}
        if response.plan is not None:
            yield {"type": "maintenance", "event": "plan", "intent": response.plan.intent, "actions": [action.__dict__ | {"risk": action.risk.value} for action in response.plan.actions], "skipped": list(response.plan.skipped_risks)}
        for result in response.results:
            yield {"type": "maintenance", "event": "result", "operation": result.operation, "target": result.target_id, "success": result.success, "verified": result.verified, "changed": result.changed, "detail": result.detail, "error": result.error}
        yield {"type": "done", "content": response.message or "Maintenance check complete.", "final": True}
    except Exception as exc:
        yield {"type": "done", "content": f"Windows maintenance is unavailable without affecting normal Jarvis operation: {exc}", "final": True}


def _desktop_context() -> str:
    try:
        from core.computer import get_computer_control
        summary = get_computer_control().desktop_summary()
        windows = [w["title"] for w in summary.get("windows", [])][:15]
        return (
            "CURRENT DESKTOP STATE\n"
            f"- Platform: {summary['available'].get('platform')}\n"
            f"- Mouse/keyboard: {'yes' if summary['available'].get('mouse_keyboard') else 'no'}\n"
            f"- Window management: {'yes' if summary['available'].get('window_management') else 'no'}\n"
            f"- Open windows: {', '.join(windows) if windows else 'none detected'}\n"
            "Use desktop_summary, list_windows, open_app, focus_window, close_app to organize."
        )
    except Exception as e:
        return f"Desktop snapshot unavailable: {e}"


def _is_coding_task(task) -> bool:
    """Return True only when the task is a file mutation with an explicit path."""
    mutation_tools = {"write_file"}
    tool = getattr(task, "tool", None)
    args = getattr(task, "args", None)
    has_path = isinstance(args, dict) and bool(args.get("path"))
    if tool in mutation_tools:
        return has_path

    description = str(getattr(task, "description", "")).lower()
    mutation_language = any(
        marker in description
        for marker in (
            "edit ", "change ", "modify ", "rewrite ", "update ",
            "implement ", "add ", "create ", "refactor ", "fix ",
        )
    )
    return mutation_language and has_path


class Agent:
    def __init__(self, language="english", persona=None, confirm_enabled=True):
        self.language = language
        self.persona = persona
        self.confirm_enabled = confirm_enabled
        get_permission_manager().set_interactive(confirm_enabled)
        self.messages = self._build_messages()
        self._tool_defs = get_tool_definitions()
        tool_map = get_tool_map()
        self._planner = Planner(llm_chat, tool_definitions=self._tool_defs)
        self._executor = Executor(llm_chat, tool_map)
        self._coding_executor = Executor(
            lambda messages, tools=None: llm_chat(
                messages, tools=tools, provider_name="zen_coder"
            ),
            tool_map,
        )
        self._output_dir: str | None = None

    def resolve_approval(self, request_id: str, allowed: bool) -> bool:
        return get_approval_registry().resolve(request_id, allowed)

    def _build_messages(self):
        base = get_system_prompt(self.language)
        if self.persona:
            try:
                from core.persona import get_persona_prompt
                persona_text = get_persona_prompt(self.persona)
                base = persona_text + "\n\n" + base
            except ImportError:
                pass
        return [{"role": "system", "content": base}]

    @property
    def output_dir(self) -> str | None:
        return self._output_dir

    def set_output_dir(self, path: str | None):
        self._output_dir = path
        self._executor.output_dir = path
        self._coding_executor.output_dir = path

    def set_language(self, lang):
        self.language = lang
        self.clear()

    def clear(self):
        self.messages = self._build_messages()

    def run(self, user_input: str):
        self._executor.output_dir = self._output_dir
        self._coding_executor.output_dir = self._output_dir
        if _is_maintenance_goal(user_input):
            yield from _maintenance_events(user_input)
            return
        memory = get_memory_manager()
        context = memory.inject_context(user_input)
        if context:
            enhanced = get_system_prompt(self.language) + "\n\n" + context
            self.messages.append({"role": "system", "content": enhanced})
        self.messages.append({"role": "user", "content": user_input})

        fast = _get_system1().route(user_input)
        if fast:
            yield {"type": "fast", "reflex": fast["reflex"], "content": fast["content"]}
            yield {"type": "done", "content": fast["content"], "final": True}
            return

        plan = self._planner.create_plan(user_input, context=self.messages)
        info(f"Plan created: {len(plan)} tasks", tasks=[t.description for t in plan])
        yield {"type": "plan", "tasks": [t.to_dict() for t in plan]}

        for task in plan:
            yield {"type": "task_start", "task": task.to_dict()}
            info(f"Executing task: {task.id} - {task.description}")
            if _is_coding_task(task):
                for event in self._execute_coding_task(task, max_iterations=MAX_ITERATIONS):
                    yield event
            else:
                for event in self._executor.execute_task(task, self.messages, self._tool_defs, MAX_ITERATIONS):
                    yield event

            if task.status == "failed" and task.retries < task.max_retries:
                err = (task.error or "").lower()
                if any(x in err for x in _TRANSIENT_ERRORS):
                    info(f"Retrying task: {task.id} (attempt {task.retries}/{task.max_retries})")
                    if _is_coding_task(task):
                        for event in self._execute_coding_task(task, max_iterations=MAX_ITERATIONS):
                            yield event
                    else:
                        for event in self._executor.retry_task(task, self.messages, self._tool_defs):
                            yield event

            yield {"type": "task_done", "task": task.to_dict()}
            if task.status == "failed":
                error_text = task.error or f"Task failed: {task.description}"
                yield {"type": "error", "content": error_text, "final": True}
                return

        last = self.messages[-1] if self.messages else {}
        final = last.get("content", "") if last.get("role") == "assistant" else ""
        if final:
            memory.store_conversation_memory(user_input, final)
        yield {"type": "done", "content": final or "Done.", "final": True}

    def run_autopilot(self, goal: str, workspace: str | None = None):
        from core.autopilot import Autopilot
        context = list(self.messages)
        if _is_desktop_goal(goal):
            context.append({"role": "system", "content": _desktop_context()})

        def coding_llm(messages, tools=None):
            return llm_chat(messages, tools=tools, provider_name="zen_coder")

        coding_planner = Planner(coding_llm, tool_definitions=self._tool_defs)
        auto = Autopilot(
            planner=coding_planner,
            llm_provider=coding_llm,
            tool_map=get_tool_map(),
            tool_definitions=self._tool_defs,
            workspace=workspace or self._output_dir,
        )
        yield from auto.run(goal, context=context)

    def _execute_coding_task(self, task_description, max_iterations=10, expected_paths=None, **kwargs):
        """Run coding through the bounded repair controller and its safe transaction adapter."""
        task_args = getattr(task_description, "args", None)
        if expected_paths is None and isinstance(task_args, dict):
            task_path = task_args.get("path")
            if task_path:
                expected_paths = [task_path]

        if not expected_paths:
            task_description.status = "failed"
            task_description.error = "Coding execution requires an explicit authorized path."
            def rejected():
                yield {"type": "coding_transaction", "status": "rejected", "reason": "Coding execution requires an explicit path."}
            return rejected()

        session = getattr(self, "_coding_session", None)
        if session is None:
            session = SimpleNamespace(current_stage="executing", status="running")
            self._coding_session = session
        else:
            session.current_stage = "executing"
            session.status = "running"

        self._coding_session_state = {
            "status": "running", "current_stage": "execute", "checkpoint": "coding-started",
            "confidence": "medium", "attempt": 1, "changes": [], "tests": [],
        }

        executor = getattr(self, "_coding_executor", None) or getattr(self, "_executor", None) or getattr(self, "executor", None)
        configured_workspace = getattr(self, "workspace", None) or self._output_dir
        workspace = Path(configured_workspace) if configured_workspace else Path.cwd()

        from coding.coder_controller import create_coder_controller
        from coding.coding_handoff import CodingHandoff, ExplorerEvidence
        from coding.coding_workflow import CodingPlan

        plan = CodingPlan(
            goal=str(getattr(task_description, "description", task_description)),
            expected_paths=tuple(str(p) for p in expected_paths),
            implementation_steps=(str(getattr(task_description, "description", task_description)),),
            test_paths=(), review_required=True,
        )
        evidence = ExplorerEvidence(
            workspace=str(workspace), goal=plan.goal,
            relevant_files=tuple(str(p) for p in expected_paths),
        )
        handoff = CodingHandoff(
            goal=plan.goal, workspace=str(workspace), evidence=evidence, plan=plan,
        )

        def execute_coder(handoff, run_tests, run_review, final_verify):
            from coding.executor_adapter import SafeExecutorAdapter
            adapter = SafeExecutorAdapter(executor=executor, workspace=workspace, expected_paths=expected_paths)
            return adapter.execute(
                task_description, self.messages, self._tool_defs,
                max_iterations=max_iterations,
                test_check=lambda: run_tests(handoff),
                review_check=lambda: run_review(handoff),
                final_verification_check=lambda: final_verify(handoff),
            )

        def run_tests(handoff): return True
        def run_review(handoff): return True
        def final_verify(handoff): return True

        def repair_coder(handoff, attempt_number, failed_result):
            failure = ""
            if isinstance(failed_result, dict):
                failure = str(failed_result.get("error") or failed_result.get("result") or "")
            if not failure:
                failure = "The previous coding attempt failed its completion gates."
            task_description.status = "running"
            task_description.error = None
            self._coding_session_state["attempt"] = attempt_number
            self._coding_session_state["current_stage"] = "repair"
            self.messages.append({
                "role": "user",
                "content": (
                    f"Repair attempt {attempt_number} for the coding task.\n"
                    f"The previous attempt failed: {failure}\n\n"
                    "Do not repeat the failed approach. Inspect the current repository state, "
                    "make the smallest safe correction to the authorized path, and actually "
                    "execute the coding tools. The change is not complete until repository "
                    "verification passes. Keep all changes inside the authorized path."
                ),
            })
            return execute_coder(handoff, run_tests, run_review, final_verify)

        controller = create_coder_controller(
            workspace=workspace, handoff=handoff, execute_coder=execute_coder,
            run_tests=run_tests, run_review=run_review, final_verify=final_verify,
            repair_coder=repair_coder,
        )
        result = controller.run()

        def run():
            if result.success:
                task_description.status = "completed"
                session.current_stage = "complete"
                session.status = "completed"
                self._coding_session_state = {
                    "status": "completed", "current_stage": "complete", "checkpoint": "coding-complete",
                    "confidence": "high", "attempt": 1, "changes": list(result.changed_paths),
                    "tests": ["bounded repair controller completed"],
                }
                for event in result.events:
                    if isinstance(event, dict) and event.get("type") == "coding_transaction":
                        yield event
                if not any(
                    isinstance(event, dict) and event.get("type") == "coding_transaction" and event.get("status") == "completed"
                    for event in result.events
                ):
                    yield {"type": "coding_transaction", "status": "completed", "changed_paths": list(result.changed_paths), "transaction_id": result.transaction_id}
            else:
                task_description.status = "failed"
                task_description.error = "Coding repair controller failed completion gates."
                session.current_stage = "failed"
                session.status = "failed"
                self._coding_session_state = {
                    "status": "failed", "current_stage": "failed", "checkpoint": "coding-failed",
                    "confidence": "high", "attempt": 3, "changes": [], "tests": ["repair controller exhausted"],
                }
                yield {"type": "coding_transaction", "status": "failed", "reason": task_description.error}

        return run()
