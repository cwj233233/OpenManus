from app.tool.chart_visualization.python_execute import NormalPythonExecute


class VisualizationPrepare(NormalPythonExecute):
    """A tool for Chart Generation Preparation"""

    name: str = "visualization_preparation"
    description: str = (
        "使用 Python 代码生成 `data_visualization` 工具所需的元数据。输出：1）JSON 信息；2）清洗后的 CSV 数据文件（可选）。"
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "code_type": {
                "description": "代码类型：visualization（csv -> chart）；insight（选择要写入图表的洞察）",
                "type": "string",
                "default": "visualization",
                "enum": ["visualization", "insight"],
            },
            "code": {
                "type": "string",
                "description": """用于 data_visualization 准备阶段的 Python 代码。
## Visualization Type
1. 数据加载逻辑
2. 生成 CSV 数据与图表描述
2.1 CSV 数据（你要可视化的数据：从原始数据清洗/转换后保存为 .csv）
2.2 CSV 数据对应的图表描述（图表标题/描述应简洁清晰，例如：'产品销量分布'、'月度营收趋势'）
3. 将信息保存为 json 文件（格式：{"csvFilePath": string, "chartTitle": string}[]）
## Insight Type
1. 从 data_visualization 的结果中选择你希望写入图表的洞察点。
2. 将信息保存为 json 文件（格式：{"chartPath": string, "insights_id": number[]}[]）
# Note
1. 你可以按不同的可视化需求生成一个或多个 CSV。
2. 保持每个图表数据简单、干净且彼此区分。
3. JSON 文件请以 UTF-8 保存，并打印路径：print(json_path)
""",
            },
        },
        "required": ["code", "code_type"],
    }
