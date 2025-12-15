import base64
import io
import json
import traceback
from typing import Optional  # Add this import for Optional

from PIL import Image
from pydantic import Field

from app.daytona.tool_base import (  # Ensure Sandbox is imported correctly
    Sandbox,
    SandboxToolsBase,
    ThreadMessage,
)
from app.tool.base import ToolResult
from app.utils.logger import logger

# Context = TypeVar("Context")
_BROWSER_DESCRIPTION = """\
一个基于沙箱的浏览器自动化工具，支持通过多种动作与网页交互。
* 在沙箱环境中控制浏览器会话
* 多次调用之间会保持状态，浏览器会话会持续存在，直到显式关闭
* 当你需要在安全沙箱里浏览网页、填写表单、点击按钮或提取内容时使用
* 每个 action 所需参数由 dependencies 定义
主要能力包括：
* 导航：打开指定 URL、返回历史
* 交互：按索引点击元素、输入文本、发送键盘按键
* 滚动：按像素滚动或滚动到指定文本
* 标签页管理：切换/关闭标签页
* 内容提取：获取/选择下拉框选项
"""


# noinspection PyArgumentList
class SandboxBrowserTool(SandboxToolsBase):
    """Tool for executing tasks in a Daytona sandbox with browser-use capabilities."""

    name: str = "sandbox_browser"
    description: str = _BROWSER_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "navigate_to",
                    "go_back",
                    "wait",
                    "click_element",
                    "input_text",
                    "send_keys",
                    "switch_tab",
                    "close_tab",
                    "scroll_down",
                    "scroll_up",
                    "scroll_to_text",
                    "get_dropdown_options",
                    "select_dropdown_option",
                    "click_coordinates",
                    "drag_drop",
                ],
                "description": "要执行的浏览器动作",
            },
            "url": {
                "type": "string",
                "description": "'navigate_to' 动作使用的 URL",
            },
            "index": {
                "type": "integer",
                "description": "交互动作使用的元素索引",
            },
            "text": {
                "type": "string",
                "description": "输入或滚动动作使用的文本",
            },
            "amount": {
                "type": "integer",
                "description": "滚动像素数量",
            },
            "page_id": {
                "type": "integer",
                "description": "标签页管理动作使用的 Tab ID",
            },
            "keys": {
                "type": "string",
                "description": "键盘动作要发送的按键",
            },
            "seconds": {
                "type": "integer",
                "description": "等待秒数",
            },
            "x": {
                "type": "integer",
                "description": "点击/拖拽动作的 X 坐标",
            },
            "y": {
                "type": "integer",
                "description": "点击/拖拽动作的 Y 坐标",
            },
            "element_source": {
                "type": "string",
                "description": "拖拽动作的源元素",
            },
            "element_target": {
                "type": "string",
                "description": "拖拽动作的目标元素",
            },
        },
        "required": ["action"],
        "dependencies": {
            "navigate_to": ["url"],
            "click_element": ["index"],
            "input_text": ["index", "text"],
            "send_keys": ["keys"],
            "switch_tab": ["page_id"],
            "close_tab": ["page_id"],
            "scroll_down": ["amount"],
            "scroll_up": ["amount"],
            "scroll_to_text": ["text"],
            "get_dropdown_options": ["index"],
            "select_dropdown_option": ["index", "text"],
            "click_coordinates": ["x", "y"],
            "drag_drop": ["element_source", "element_target"],
            "wait": ["seconds"],
        },
    }
    browser_message: Optional[ThreadMessage] = Field(default=None, exclude=True)

    def __init__(
        self, sandbox: Optional[Sandbox] = None, thread_id: Optional[str] = None, **data
    ):
        """Initialize with optional sandbox and thread_id."""
        super().__init__(**data)
        if sandbox is not None:
            self._sandbox = sandbox  # Directly set the base class private attribute

    def _validate_base64_image(
        self, base64_string: str, max_size_mb: int = 10
    ) -> tuple[bool, str]:
        """
        Validate base64 image data.
        Args:
            base64_string: The base64 encoded image data
            max_size_mb: Maximum allowed image size in megabytes
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not base64_string or len(base64_string) < 10:
                return False, "Base64 string is empty or too short"
            if base64_string.startswith("data:"):
                try:
                    base64_string = base64_string.split(",", 1)[1]
                except (IndexError, ValueError):
                    return False, "Invalid data URL format"
            import re

            if not re.match(r"^[A-Za-z0-9+/]*={0,2}$", base64_string):
                return False, "Invalid base64 characters detected"
            if len(base64_string) % 4 != 0:
                return False, "Invalid base64 string length"
            try:
                image_data = base64.b64decode(base64_string, validate=True)
            except Exception as e:
                return False, f"Base64 decoding failed: {str(e)}"
            max_size_bytes = max_size_mb * 1024 * 1024
            if len(image_data) > max_size_bytes:
                return False, f"Image size exceeds limit ({max_size_bytes} bytes)"
            try:
                image_stream = io.BytesIO(image_data)
                with Image.open(image_stream) as img:
                    img.verify()
                    supported_formats = {"JPEG", "PNG", "GIF", "BMP", "WEBP", "TIFF"}
                    if img.format not in supported_formats:
                        return False, f"Unsupported image format: {img.format}"
                    image_stream.seek(0)
                    with Image.open(image_stream) as img_check:
                        width, height = img_check.size
                        max_dimension = 8192
                        if width > max_dimension or height > max_dimension:
                            return (
                                False,
                                f"Image dimensions exceed limit ({max_dimension}x{max_dimension})",
                            )
                        if width < 1 or height < 1:
                            return False, f"Invalid image dimensions: {width}x{height}"
            except Exception as e:
                return False, f"Invalid image data: {str(e)}"
            return True, "Valid image"
        except Exception as e:
            logger.error(f"Unexpected error during base64 image validation: {e}")
            return False, f"Validation error: {str(e)}"

    async def _execute_browser_action(
        self, endpoint: str, params: dict = None, method: str = "POST"
    ) -> ToolResult:
        """Execute a browser automation action through the sandbox API."""
        try:
            await self._ensure_sandbox()
            url = f"http://localhost:8003/api/automation/{endpoint}"
            if method == "GET" and params:
                query_params = "&".join([f"{k}={v}" for k, v in params.items()])
                url = f"{url}?{query_params}"
                curl_cmd = (
                    f"curl -s -X {method} '{url}' -H 'Content-Type: application/json'"
                )
            else:
                curl_cmd = (
                    f"curl -s -X {method} '{url}' -H 'Content-Type: application/json'"
                )
                if params:
                    json_data = json.dumps(params)
                    curl_cmd += f" -d '{json_data}'"
            logger.debug(f"Executing curl command: {curl_cmd}")
            response = self.sandbox.process.exec(curl_cmd, timeout=30)
            if response.exit_code == 0:
                try:
                    result = json.loads(response.result)
                    result.setdefault("content", "")
                    result.setdefault("role", "assistant")
                    if "screenshot_base64" in result:
                        screenshot_data = result["screenshot_base64"]
                        is_valid, validation_message = self._validate_base64_image(
                            screenshot_data
                        )
                        if not is_valid:
                            logger.warning(
                                f"Screenshot validation failed: {validation_message}"
                            )
                            result["image_validation_error"] = validation_message
                            del result["screenshot_base64"]

                    # added_message = await self.thread_manager.add_message(
                    #     thread_id=self.thread_id,
                    #     type="browser_state",
                    #     content=result,
                    #     is_llm_message=False
                    # )
                    message = ThreadMessage(
                        type="browser_state", content=result, is_llm_message=False
                    )
                    self.browser_message = message
                    success_response = {
                        "success": result.get("success", False),
                        "message": result.get("message", "Browser action completed"),
                    }
                    #         if added_message and 'message_id' in added_message:
                    #             success_response['message_id'] = added_message['message_id']
                    for field in [
                        "url",
                        "title",
                        "element_count",
                        "pixels_below",
                        "ocr_text",
                        "image_url",
                    ]:
                        if field in result:
                            success_response[field] = result[field]
                    return (
                        self.success_response(success_response)
                        if success_response["success"]
                        else self.fail_response(success_response)
                    )
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse response JSON: {e}")
                    return self.fail_response(f"Failed to parse response JSON: {e}")
            else:
                logger.error(f"Browser automation request failed: {response}")
                return self.fail_response(
                    f"Browser automation request failed: {response}"
                )
        except Exception as e:
            logger.error(f"Error executing browser action: {e}")
            logger.debug(traceback.format_exc())
            return self.fail_response(f"Error executing browser action: {e}")

    async def execute(
        self,
        action: str,
        url: Optional[str] = None,
        index: Optional[int] = None,
        text: Optional[str] = None,
        amount: Optional[int] = None,
        page_id: Optional[int] = None,
        keys: Optional[str] = None,
        seconds: Optional[int] = None,
        x: Optional[int] = None,
        y: Optional[int] = None,
        element_source: Optional[str] = None,
        element_target: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a browser action in the sandbox environment.
        Args:
            action: The browser action to perform
            url: URL for navigation
            index: Element index for interaction
            text: Text for input or scroll actions
            amount: Pixel amount to scroll
            page_id: Tab ID for tab management
            keys: Keys to send for keyboard actions
            seconds: Seconds to wait
            x: X coordinate for click/drag
            y: Y coordinate for click/drag
            element_source: Source element for drag and drop
            element_target: Target element for drag and drop
        Returns:
            ToolResult with the action's output or error
        """
        # async with self.lock:
        try:
            # Navigation actions
            if action == "navigate_to":
                if not url:
                    return self.fail_response("URL is required for navigation")
                return await self._execute_browser_action("navigate_to", {"url": url})
            elif action == "go_back":
                return await self._execute_browser_action("go_back", {})
                # Interaction actions
            elif action == "click_element":
                if index is None:
                    return self.fail_response("Index is required for click_element")
                return await self._execute_browser_action(
                    "click_element", {"index": index}
                )
            elif action == "input_text":
                if index is None or not text:
                    return self.fail_response(
                        "Index and text are required for input_text"
                    )
                return await self._execute_browser_action(
                    "input_text", {"index": index, "text": text}
                )
            elif action == "send_keys":
                if not keys:
                    return self.fail_response("Keys are required for send_keys")
                return await self._execute_browser_action("send_keys", {"keys": keys})
                # Tab management
            elif action == "switch_tab":
                if page_id is None:
                    return self.fail_response("Page ID is required for switch_tab")
                return await self._execute_browser_action(
                    "switch_tab", {"page_id": page_id}
                )
            elif action == "close_tab":
                if page_id is None:
                    return self.fail_response("Page ID is required for close_tab")
                return await self._execute_browser_action(
                    "close_tab", {"page_id": page_id}
                )
                # Scrolling actions
            elif action == "scroll_down":
                params = {"amount": amount} if amount is not None else {}
                return await self._execute_browser_action("scroll_down", params)
            elif action == "scroll_up":
                params = {"amount": amount} if amount is not None else {}
                return await self._execute_browser_action("scroll_up", params)
            elif action == "scroll_to_text":
                if not text:
                    return self.fail_response("Text is required for scroll_to_text")
                return await self._execute_browser_action(
                    "scroll_to_text", {"text": text}
                )
            # 下拉操作
            elif action == "get_dropdown_options":
                if index is None:
                    return self.fail_response(
                        "Index is required for get_dropdown_options"
                    )
                return await self._execute_browser_action(
                    "get_dropdown_options", {"index": index}
                )
            elif action == "select_dropdown_option":
                if index is None or not text:
                    return self.fail_response(
                        "Index and text are required for select_dropdown_option"
                    )
                return await self._execute_browser_action(
                    "select_dropdown_option", {"index": index, "text": text}
                )
                # 基于坐标的操作
            elif action == "click_coordinates":
                if x is None or y is None:
                    return self.fail_response(
                        "X and Y coordinates are required for click_coordinates"
                    )
                return await self._execute_browser_action(
                    "click_coordinates", {"x": x, "y": y}
                )
            elif action == "drag_drop":
                if not element_source or not element_target:
                    return self.fail_response(
                        "Source and target elements are required for drag_drop"
                    )
                return await self._execute_browser_action(
                    "drag_drop",
                    {
                        "element_source": element_source,
                        "element_target": element_target,
                    },
                )
            # Utility actions
            elif action == "wait":
                seconds_to_wait = seconds if seconds is not None else 3
                return await self._execute_browser_action(
                    "wait", {"seconds": seconds_to_wait}
                )
            else:
                return self.fail_response(f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"Error executing browser action: {e}")
            return self.fail_response(f"Error executing browser action: {e}")

    async def get_current_state(
        self, message: Optional[ThreadMessage] = None
    ) -> ToolResult:
        """
        Get the current browser state as a ToolResult.
        If context is not provided, uses self.context.
        """
        try:
            # Use provided context or fall back to self.context
            message = message or self.browser_message
            if not message:
                return ToolResult(error="Browser context not initialized")
            state = message.content
            screenshot = state.get("screenshot_base64")
            # 使用所有必需字段构建状态信息
            state_info = {
                "url": state.get("url", ""),
                "title": state.get("title", ""),
                "tabs": [tab.model_dump() for tab in state.get("tabs", [])],
                "pixels_above": getattr(state, "pixels_above", 0),
                "pixels_below": getattr(state, "pixels_below", 0),
                "help": "[0], [1], [2], etc., represent clickable indices corresponding to the elements listed. Clicking on these indices will navigate to or interact with the respective content behind them.",
            }

            return ToolResult(
                output=json.dumps(state_info, indent=4, ensure_ascii=False),
                base64_image=screenshot,
            )
        except Exception as e:
            return ToolResult(error=f"Failed to get browser state: {str(e)}")

    @classmethod
    def create_with_sandbox(cls, sandbox: Sandbox) -> "SandboxBrowserTool":
        """Factory method to create a tool with sandbox."""
        return cls(sandbox=sandbox)
