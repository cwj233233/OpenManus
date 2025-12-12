from app.tool import BaseTool


class AskHuman(BaseTool):
    """Add a tool to ask human for help."""

    name: str = "ask_human"
    description: str = "当你需要向用户（真人）提问以获得额外信息时使用此工具。"
    parameters: str = {
        "type": "object",
        "properties": {
            "inquire": {
                "type": "string",
                "description": "你想向用户询问的问题。",
            }
        },
        "required": ["inquire"],
    }

    async def execute(self, inquire: str) -> str:
        return input(f"""Bot: {inquire}\n\nYou: """).strip()
