import asyncio
import time
from typing import Any, Dict, Optional, TypeVar
from uuid import uuid4

from app.daytona.tool_base import Sandbox, SandboxToolsBase
from app.tool.base import ToolResult
from app.utils.logger import logger

Context = TypeVar("Context")
_SHELL_DESCRIPTION = """\
在 workspace 目录中执行 shell 命令。
重要：默认以非阻塞方式运行，并在 tmux 会话中执行。
这非常适合启动服务、构建等长时间运行的操作。
通过 session 保持多次命令之间的状态。
该工具适用于运行 CLI 工具、安装依赖、进行系统级操作等。
"""


class SandboxShellTool(SandboxToolsBase):
    """Tool for executing tasks in a Daytona sandbox with browser-use capabilities.
    Uses sessions for maintaining state between commands and provides comprehensive process management.
    """

    name: str = "sandbox_shell"
    description: str = _SHELL_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "execute_command",
                    "check_command_output",
                    "terminate_command",
                    "list_commands",
                ],
                "description": "要执行的 shell 动作",
            },
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令。用于运行 CLI 工具、安装依赖或系统操作。可使用 &&、||、| 进行链式命令。",
            },
            "folder": {
                "type": "string",
                "description": "（可选）/workspace 下的相对路径子目录，命令将在该目录中执行。例如：'data/pdfs'。",
            },
            "session_name": {
                "type": "string",
                "description": "（可选）tmux 会话名。对需要保持状态的相关命令建议使用固定 session；默认会随机生成。",
            },
            "blocking": {
                "type": "boolean",
                "description": "是否阻塞等待命令完成。默认 false（非阻塞）。",
                "default": False,
            },
            "timeout": {
                "type": "integer",
                "description": "（可选）阻塞执行的超时时间（秒），默认 60；非阻塞时忽略。",
                "default": 60,
            },
            "kill_session": {
                "type": "boolean",
                "description": "在查看输出后是否终止 tmux 会话。命令执行完成且不再需要该会话时设为 true。",
                "default": False,
            },
        },
        "required": ["action"],
        "dependencies": {
            "execute_command": ["command"],
            "check_command_output": ["session_name"],
            "terminate_command": ["session_name"],
            "list_commands": [],
        },
    }

    def __init__(
        self, sandbox: Optional[Sandbox] = None, thread_id: Optional[str] = None, **data
    ):
        """Initialize with optional sandbox and thread_id."""
        super().__init__(**data)
        if sandbox is not None:
            self._sandbox = sandbox

    async def _ensure_session(self, session_name: str = "default") -> str:
        """Ensure a session exists and return its ID."""
        if session_name not in self._sessions:
            session_id = str(uuid4())
            try:
                await self._ensure_sandbox()  # Ensure sandbox is initialized
                self.sandbox.process.create_session(session_id)
                self._sessions[session_name] = session_id
            except Exception as e:
                raise RuntimeError(f"Failed to create session: {str(e)}")
        return self._sessions[session_name]

    async def _cleanup_session(self, session_name: str):
        """Clean up a session if it exists."""
        if session_name in self._sessions:
            try:
                await self._ensure_sandbox()  # Ensure sandbox is initialized
                self.sandbox.process.delete_session(self._sessions[session_name])
                del self._sessions[session_name]
            except Exception as e:
                print(f"Warning: Failed to cleanup session {session_name}: {str(e)}")

    async def _execute_raw_command(self, command: str) -> Dict[str, Any]:
        """Execute a raw command directly in the sandbox."""
        # Ensure session exists for raw commands
        session_id = await self._ensure_session("raw_commands")

        # Execute command in session
        from app.daytona.sandbox import SessionExecuteRequest

        req = SessionExecuteRequest(
            command=command, run_async=False, cwd=self.workspace_path
        )

        response = self.sandbox.process.execute_session_command(
            session_id=session_id,
            req=req,
            timeout=30,  # Short timeout for utility commands
        )

        logs = self.sandbox.process.get_session_command_logs(
            session_id=session_id, command_id=response.cmd_id
        )

        return {"output": logs, "exit_code": response.exit_code}

    async def _execute_command(
        self,
        command: str,
        folder: Optional[str] = None,
        session_name: Optional[str] = None,
        blocking: bool = False,
        timeout: int = 60,
    ) -> ToolResult:
        try:
            # Ensure sandbox is initialized
            await self._ensure_sandbox()

            # Set up working directory
            cwd = self.workspace_path
            if folder:
                folder = folder.strip("/")
                cwd = f"{self.workspace_path}/{folder}"

            # Generate a session name if not provided
            if not session_name:
                session_name = f"session_{str(uuid4())[:8]}"

            # Check if tmux session already exists
            check_session = await self._execute_raw_command(
                f"tmux has-session -t {session_name} 2>/dev/null || echo 'not_exists'"
            )
            session_exists = "not_exists" not in check_session.get("output", "")

            if not session_exists:
                # Create a new tmux session
                await self._execute_raw_command(
                    f"tmux new-session -d -s {session_name}"
                )

            # Ensure we're in the correct directory and send command to tmux
            full_command = f"cd {cwd} && {command}"
            wrapped_command = full_command.replace('"', '\\"')  # Escape double quotes

            # Send command to tmux session
            await self._execute_raw_command(
                f'tmux send-keys -t {session_name} "{wrapped_command}" Enter'
            )

            if blocking:
                # For blocking execution, wait and capture output
                start_time = time.time()
                while (time.time() - start_time) < timeout:
                    # Wait a bit before checking
                    time.sleep(2)

                    # Check if session still exists (command might have exited)
                    check_result = await self._execute_raw_command(
                        f"tmux has-session -t {session_name} 2>/dev/null || echo 'ended'"
                    )
                    if "ended" in check_result.get("output", ""):
                        break

                    # Get current output and check for common completion indicators
                    output_result = await self._execute_raw_command(
                        f"tmux capture-pane -t {session_name} -p -S - -E -"
                    )
                    current_output = output_result.get("output", "")

                    # Check for prompt indicators that suggest command completion
                    last_lines = current_output.split("\n")[-3:]
                    completion_indicators = [
                        "$",
                        "#",
                        ">",
                        "Done",
                        "Completed",
                        "Finished",
                        "✓",
                    ]
                    if any(
                        indicator in line
                        for indicator in completion_indicators
                        for line in last_lines
                    ):
                        break

                # Capture final output
                output_result = await self._execute_raw_command(
                    f"tmux capture-pane -t {session_name} -p -S - -E -"
                )
                final_output = output_result.get("output", "")

                # Kill the session after capture
                await self._execute_raw_command(f"tmux kill-session -t {session_name}")

                return self.success_response(
                    {
                        "output": final_output,
                        "session_name": session_name,
                        "cwd": cwd,
                        "completed": True,
                    }
                )
            else:
                # For non-blocking, just return immediately
                return self.success_response(
                    {
                        "session_name": session_name,
                        "cwd": cwd,
                        "message": f"Command sent to tmux session '{session_name}'. Use check_command_output to view results.",
                        "completed": False,
                    }
                )

        except Exception as e:
            # Attempt to clean up session in case of error
            if session_name:
                try:
                    await self._execute_raw_command(
                        f"tmux kill-session -t {session_name}"
                    )
                except:
                    pass
            return self.fail_response(f"Error executing command: {str(e)}")

    async def _check_command_output(
        self, session_name: str, kill_session: bool = False
    ) -> ToolResult:
        try:
            # Ensure sandbox is initialized
            await self._ensure_sandbox()

            # Check if session exists
            check_result = await self._execute_raw_command(
                f"tmux has-session -t {session_name} 2>/dev/null || echo 'not_exists'"
            )
            if "not_exists" in check_result.get("output", ""):
                return self.fail_response(
                    f"Tmux session '{session_name}' does not exist."
                )

            # Get output from tmux pane
            output_result = await self._execute_raw_command(
                f"tmux capture-pane -t {session_name} -p -S - -E -"
            )
            output = output_result.get("output", "")

            # Kill session if requested
            if kill_session:
                await self._execute_raw_command(f"tmux kill-session -t {session_name}")
                termination_status = "Session terminated."
            else:
                termination_status = "Session still running."

            return self.success_response(
                {
                    "output": output,
                    "session_name": session_name,
                    "status": termination_status,
                }
            )

        except Exception as e:
            return self.fail_response(f"Error checking command output: {str(e)}")

    async def _terminate_command(self, session_name: str) -> ToolResult:
        try:
            # Ensure sandbox is initialized
            await self._ensure_sandbox()

            # Check if session exists
            check_result = await self._execute_raw_command(
                f"tmux has-session -t {session_name} 2>/dev/null || echo 'not_exists'"
            )
            if "not_exists" in check_result.get("output", ""):
                return self.fail_response(
                    f"Tmux session '{session_name}' does not exist."
                )

            # Kill the session
            await self._execute_raw_command(f"tmux kill-session -t {session_name}")

            return self.success_response(
                {"message": f"Tmux session '{session_name}' terminated successfully."}
            )

        except Exception as e:
            return self.fail_response(f"Error terminating command: {str(e)}")

    async def _list_commands(self) -> ToolResult:
        try:
            # Ensure sandbox is initialized
            await self._ensure_sandbox()

            # List all tmux sessions
            result = await self._execute_raw_command(
                "tmux list-sessions 2>/dev/null || echo 'No sessions'"
            )
            output = result.get("output", "")

            if "No sessions" in output or not output.strip():
                return self.success_response(
                    {"message": "No active tmux sessions found.", "sessions": []}
                )

            # Parse session list
            sessions = []
            for line in output.split("\n"):
                if line.strip():
                    parts = line.split(":")
                    if parts:
                        session_name = parts[0].strip()
                        sessions.append(session_name)

            return self.success_response(
                {
                    "message": f"Found {len(sessions)} active sessions.",
                    "sessions": sessions,
                }
            )

        except Exception as e:
            return self.fail_response(f"Error listing commands: {str(e)}")

    async def execute(
        self,
        action: str,
        command: str,
        folder: Optional[str] = None,
        session_name: Optional[str] = None,
        blocking: bool = False,
        timeout: int = 60,
        kill_session: bool = False,
    ) -> ToolResult:
        """
        Execute a browser action in the sandbox environment.
        Args:
            timeout:
            blocking:
            session_name:
            folder:
            command:
            kill_session:
            action: The browser action to perform
        Returns:
            ToolResult with the action's output or error
        """
        async with asyncio.Lock():
            try:
                # Navigation actions
                if action == "execute_command":
                    if not command:
                        return self.fail_response("command is required for navigation")
                    return await self._execute_command(
                        command, folder, session_name, blocking, timeout
                    )
                elif action == "check_command_output":
                    if session_name is None:
                        return self.fail_response(
                            "session_name is required for navigation"
                        )
                    return await self._check_command_output(session_name, kill_session)
                elif action == "terminate_command":
                    if session_name is None:
                        return self.fail_response(
                            "session_name is required for click_element"
                        )
                    return await self._terminate_command(session_name)
                elif action == "list_commands":
                    return await self._list_commands()
                else:
                    return self.fail_response(f"Unknown action: {action}")
            except Exception as e:
                logger.error(f"Error executing shell action: {e}")
                return self.fail_response(f"Error executing shell action: {e}")

    async def cleanup(self):
        """Clean up all sessions."""
        for session_name in list(self._sessions.keys()):
            await self._cleanup_session(session_name)

        # Also clean up any tmux sessions
        try:
            await self._ensure_sandbox()
            await self._execute_raw_command("tmux kill-server 2>/dev/null || true")
        except Exception as e:
            logger.error(f"Error shell box cleanup action: {e}")
