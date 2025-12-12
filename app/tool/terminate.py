from app.tool.base import BaseTool

_TERMINATE_DESCRIPTION = """当请求已满足，或你无法继续推进任务时，用于终止本次交互。
当你完成了所有任务后，请调用此工具结束工作。

重要：
- 终止时必须提供简洁的 `final_answer`，它会作为最终答复展示给用户。
"""


class Terminate(BaseTool):
    name: str = "terminate"
    description: str = _TERMINATE_DESCRIPTION
    parameters: dict = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "The finish status of the interaction.",
                "enum": ["success", "failure"],
            },
            "final_answer": {
                "type": "string",
                "description": "Final answer to present to the user when terminating.",
            },
        },
        "required": ["status", "final_answer"],
    }

    async def execute(self, status: str, final_answer: str) -> str:
        """Finish the current execution"""
        return (
            final_answer.strip()
            or f"The interaction has been completed with status: {status}"
        )
