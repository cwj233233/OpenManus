import asyncio
from typing import Optional, TypeVar

from pydantic import Field

from app.daytona.tool_base import Sandbox, SandboxToolsBase
from app.tool.base import ToolResult
from app.utils.files_utils import clean_path, should_exclude_file
from app.utils.logger import logger

Context = TypeVar("Context")

_FILES_DESCRIPTION = """\
一个基于沙箱的文件系统工具，用于在安全隔离环境中对 workspace 进行文件操作。
* 支持在 workspace 中创建/读取/更新/删除文件
* 出于安全考虑，所有操作均相对于 /workspace 目录执行
* 当你需要在沙箱中管理文件、编辑代码或修改文件内容时使用
* 每个 action 所需参数由 dependencies 定义
主要能力包括：
* 创建文件：按指定内容与权限创建新文件
* 修改文件：字符串替换或整文件重写
* 删除文件：从 workspace 删除文件
* 读取文件：支持按行范围读取文件内容
"""


class SandboxFilesTool(SandboxToolsBase):
    name: str = "sandbox_files"
    description: str = _FILES_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create_file",
                    "str_replace",
                    "full_file_rewrite",
                    "delete_file",
                ],
                "description": "要执行的文件操作",
            },
            "file_path": {
                "type": "string",
                "description": "文件路径，相对于 /workspace（例如：'src/main.py'）",
            },
            "file_contents": {
                "type": "string",
                "description": "要写入文件的内容",
            },
            "old_str": {
                "type": "string",
                "description": "要被替换的文本（必须且只能出现一次）",
            },
            "new_str": {
                "type": "string",
                "description": "替换后的文本",
            },
            "permissions": {
                "type": "string",
                "description": "文件权限（八进制字符串，例如 '644'）",
                "default": "644",
            },
        },
        "required": ["action"],
        "dependencies": {
            "create_file": ["file_path", "file_contents"],
            "str_replace": ["file_path", "old_str", "new_str"],
            "full_file_rewrite": ["file_path", "file_contents"],
            "delete_file": ["file_path"],
        },
    }
    SNIPPET_LINES: int = Field(default=4, exclude=True)
    # workspace_path: str = Field(default="/workspace", exclude=True)
    # sandbox: Optional[Sandbox] = Field(default=None, exclude=True)

    def __init__(
        self, sandbox: Optional[Sandbox] = None, thread_id: Optional[str] = None, **data
    ):
        """Initialize with optional sandbox and thread_id."""
        super().__init__(**data)
        if sandbox is not None:
            self._sandbox = sandbox

    def clean_path(self, path: str) -> str:
        """Clean and normalize a path to be relative to /workspace"""
        return clean_path(path, self.workspace_path)

    def _should_exclude_file(self, rel_path: str) -> bool:
        """Check if a file should be excluded based on path, name, or extension"""
        return should_exclude_file(rel_path)

    def _file_exists(self, path: str) -> bool:
        """Check if a file exists in the sandbox"""
        try:
            self.sandbox.fs.get_file_info(path)
            return True
        except Exception:
            return False

    async def get_workspace_state(self) -> dict:
        """Get the current workspace state by reading all files"""
        files_state = {}
        try:
            # 确保sandbox is initialized
            await self._ensure_sandbox()

            files = self.sandbox.fs.list_files(self.workspace_path)
            for file_info in files:
                rel_path = file_info.name

                # 跳过excluded files and directories
                if self._should_exclude_file(rel_path) or file_info.is_dir:
                    continue

                try:
                    full_path = f"{self.workspace_path}/{rel_path}"
                    content = self.sandbox.fs.download_file(full_path).decode()
                    files_state[rel_path] = {
                        "content": content,
                        "is_dir": file_info.is_dir,
                        "size": file_info.size,
                        "modified": file_info.mod_time,
                    }
                except Exception as e:
                    print(f"Error reading file {rel_path}: {e}")
                except UnicodeDecodeError:
                    print(f"Skipping binary file: {rel_path}")

            return files_state

        except Exception as e:
            print(f"Error getting workspace state: {str(e)}")
            return {}

    async def execute(
        self,
        action: str,
        file_path: Optional[str] = None,
        file_contents: Optional[str] = None,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        permissions: Optional[str] = "644",
        **kwargs,
    ) -> ToolResult:
        """
        Execute a file operation in the sandbox environment.
        Args:
            action: The file operation to perform
            file_path: Path to the file relative to /workspace
            file_contents: Content to write to the file
            old_str: Text to be replaced (for str_replace)
            new_str: Replacement text (for str_replace)
            permissions: File permissions in octal format
        Returns:
            ToolResult with the operation's output or error
        """
        async with asyncio.Lock():
            try:
                # 文件创建
                if action == "create_file":
                    if not file_path or not file_contents:
                        return self.fail_response(
                            "file_path and file_contents are required for create_file"
                        )
                    return await self._create_file(
                        file_path, file_contents, permissions
                    )

                # String replacement
                elif action == "str_replace":
                    if not file_path or not old_str or not new_str:
                        return self.fail_response(
                            "file_path, old_str, and new_str are required for str_replace"
                        )
                    return await self._str_replace(file_path, old_str, new_str)

                # 完整文件重写
                elif action == "full_file_rewrite":
                    if not file_path or not file_contents:
                        return self.fail_response(
                            "file_path and file_contents are required for full_file_rewrite"
                        )
                    return await self._full_file_rewrite(
                        file_path, file_contents, permissions
                    )

                # 文件删除
                elif action == "delete_file":
                    if not file_path:
                        return self.fail_response(
                            "file_path is required for delete_file"
                        )
                    return await self._delete_file(file_path)

                else:
                    return self.fail_response(f"Unknown action: {action}")

            except Exception as e:
                logger.error(f"Error executing file action: {e}")
                return self.fail_response(f"Error executing file action: {e}")

    async def _create_file(
        self, file_path: str, file_contents: str, permissions: str = "644"
    ) -> ToolResult:
        """Create a new file with the provided contents"""
        try:
            # 确保sandbox is initialized
            await self._ensure_sandbox()

            file_path = self.clean_path(file_path)
            full_path = f"{self.workspace_path}/{file_path}"
            if self._file_exists(full_path):
                return self.fail_response(
                    f"File '{file_path}' already exists. Use full_file_rewrite to modify existing files."
                )

            # 创建parent directories if needed
            parent_dir = "/".join(full_path.split("/")[:-1])
            if parent_dir:
                self.sandbox.fs.create_folder(parent_dir, "755")

            # Write the file content
            self.sandbox.fs.upload_file(file_contents.encode(), full_path)
            self.sandbox.fs.set_file_permissions(full_path, permissions)

            message = f"File '{file_path}' created successfully."

            # 检查是否创建了 index.html 并添加 8080 服务器信息（仅在根工作区）
            if file_path.lower() == "index.html":
                try:
                    website_link = self.sandbox.get_preview_link(8080)
                    website_url = (
                        website_link.url
                        if hasattr(website_link, "url")
                        else str(website_link).split("url='")[1].split("'")[0]
                    )
                    message += f"\n\n[Auto-detected index.html - HTTP server available at: {website_url}]"
                    message += "\n[Note: Use the provided HTTP server URL above instead of starting a new server]"
                except Exception as e:
                    logger.warning(
                        f"Failed to get website URL for index.html: {str(e)}"
                    )

            return self.success_response(message)
        except Exception as e:
            return self.fail_response(f"Error creating file: {str(e)}")

    async def _str_replace(
        self, file_path: str, old_str: str, new_str: str
    ) -> ToolResult:
        """Replace specific text in a file"""
        try:
            # 确保sandbox is initialized
            await self._ensure_sandbox()

            file_path = self.clean_path(file_path)
            full_path = f"{self.workspace_path}/{file_path}"
            if not self._file_exists(full_path):
                return self.fail_response(f"File '{file_path}' does not exist")

            content = self.sandbox.fs.download_file(full_path).decode()
            old_str = old_str.expandtabs()
            new_str = new_str.expandtabs()

            occurrences = content.count(old_str)
            if occurrences == 0:
                return self.fail_response(f"String '{old_str}' not found in file")
            if occurrences > 1:
                lines = [
                    i + 1
                    for i, line in enumerate(content.split("\n"))
                    if old_str in line
                ]
                return self.fail_response(
                    f"Multiple occurrences found in lines {lines}. Please ensure string is unique"
                )

            # Perform replacement
            new_content = content.replace(old_str, new_str)
            self.sandbox.fs.upload_file(new_content.encode(), full_path)

            # Show snippet around the edit
            replacement_line = content.split(old_str)[0].count("\n")
            start_line = max(0, replacement_line - self.SNIPPET_LINES)
            end_line = replacement_line + self.SNIPPET_LINES + new_str.count("\n")
            snippet = "\n".join(new_content.split("\n")[start_line : end_line + 1])

            message = f"Replacement successful."

            return self.success_response(message)

        except Exception as e:
            return self.fail_response(f"Error replacing string: {str(e)}")

    async def _full_file_rewrite(
        self, file_path: str, file_contents: str, permissions: str = "644"
    ) -> ToolResult:
        """Completely rewrite an existing file with new content"""
        try:
            # 确保sandbox is initialized
            await self._ensure_sandbox()

            file_path = self.clean_path(file_path)
            full_path = f"{self.workspace_path}/{file_path}"
            if not self._file_exists(full_path):
                return self.fail_response(
                    f"File '{file_path}' does not exist. Use create_file to create a new file."
                )

            self.sandbox.fs.upload_file(file_contents.encode(), full_path)
            self.sandbox.fs.set_file_permissions(full_path, permissions)

            message = f"File '{file_path}' completely rewritten successfully."

            # 检查是否重写了 index.html 并添加 8080 服务器信息（仅在根工作区）
            if file_path.lower() == "index.html":
                try:
                    website_link = self.sandbox.get_preview_link(8080)
                    website_url = (
                        website_link.url
                        if hasattr(website_link, "url")
                        else str(website_link).split("url='")[1].split("'")[0]
                    )
                    message += f"\n\n[Auto-detected index.html - HTTP server available at: {website_url}]"
                    message += "\n[Note: Use the provided HTTP server URL above instead of starting a new server]"
                except Exception as e:
                    logger.warning(
                        f"Failed to get website URL for index.html: {str(e)}"
                    )

            return self.success_response(message)
        except Exception as e:
            return self.fail_response(f"Error rewriting file: {str(e)}")

    async def _delete_file(self, file_path: str) -> ToolResult:
        """Delete a file at the given path"""
        try:
            # 确保sandbox is initialized
            await self._ensure_sandbox()

            file_path = self.clean_path(file_path)
            full_path = f"{self.workspace_path}/{file_path}"
            if not self._file_exists(full_path):
                return self.fail_response(f"File '{file_path}' does not exist")

            self.sandbox.fs.delete_file(full_path)
            return self.success_response(f"File '{file_path}' deleted successfully.")
        except Exception as e:
            return self.fail_response(f"Error deleting file: {str(e)}")

    async def cleanup(self):
        """Clean up sandbox resources."""

    @classmethod
    def create_with_context(cls, context: Context) -> "SandboxFilesTool[Context]":
        """Factory method to create a SandboxFilesTool with a specific context."""
        raise NotImplementedError(
            "create_with_context not implemented for SandboxFilesTool"
        )
