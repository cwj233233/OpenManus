from app.config import config
from app.tool.python_execute import PythonExecute


class NormalPythonExecute(PythonExecute):
    """A tool for executing Python code with timeout and safety restrictions."""

    name: str = "python_execute"
    description: str = (
        """执行 Python 代码，用于深入数据分析 / 数据报告（任务结论）/ 其他不直接做可视化的常规任务。"""
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "code_type": {
                "description": "代码类型：process（数据处理）/ report（数据报告）/ others（其它）",
                "type": "string",
                "default": "process",
                "enum": ["process", "report", "others"],
            },
            "code": {
                "type": "string",
                "description": """要执行的 Python 代码。
# Note
1. 代码应生成一份内容丰富的文本报告，包含：数据集概览、字段说明、基础统计、衍生指标、时间序列对比、异常值与关键洞察等。
2. 所有输出请使用 print()，确保分析过程（如 “Dataset Overview”“Preprocessing Results” 等章节）清晰可见，并且也要保存。
3. 任何报告/处理后的文件/每次分析结果，都请保存到 workspace 目录：{directory}
4. 数据报告需要内容充分，包含你的整体分析过程以及相应的数据可视化。
5. 你可以分步骤多次调用该工具，从概要到深入分析，并把数据报告保存下来。""".format(
                    directory=config.workspace_root
                ),
            },
        },
        "required": ["code"],
    }

    async def execute(self, code: str, code_type: str | None = None, timeout=5):
        return await super().execute(code, timeout)
