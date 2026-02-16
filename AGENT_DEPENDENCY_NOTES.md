# OpenManus Agent 依赖关系笔记

## 核心类继承链
- **BaseAgent**（`app/agent/base.py`）：定义通用状态机、记忆与步进循环，并依赖 `LLM`、`Memory`、`AgentState`、`Message` 等基础组件；在 `run` 中使用 `state_context` 控制状态并调度抽象的 `step`。【F:app/agent/base.py†L7-L155】
- **ReActAgent**（`app/agent/react.py`）：继承 `BaseAgent`，拆分 `step` 为 `think`/`act` 两阶段，提供 ReAct 风格的扩展点。【F:app/agent/react.py†L6-L38】
- **ToolCallAgent**（`app/agent/toolcall.py`）：在 ReAct 基础上增加工具调用能力，加载默认工具集合，利用 `ask_tool` 生成工具调用，`act` 中顺序执行工具并处理终止工具，同时覆盖 `run` 增加资源清理逻辑。【F:app/agent/toolcall.py†L7-L259】
- **Manus**（`app/agent/manus.py`）：具体业务代理，设置系统/下一步提示词、步数限制，内置 Python 执行、浏览器、字符串编辑、人工求助与终止工具，并可通过 MCP 客户端动态注册远程工具；在 `think` 中检测浏览器上下文并注入提示，提供工厂方法 `create` 初始化 MCP 连接及后续清理。【F:app/agent/manus.py†L5-L165】

## 运行入口
- CLI 入口位于 `main.py`：解析 `--prompt` 参数，创建并初始化 `Manus` 实例，调用 `run` 执行任务并在退出时确保 `cleanup`，是框架的默认启动方式。【F:main.py†L1-L36】【F:app/agent/manus.py†L59-L165】

### 运行 `python main.py` 时会触达的关键文件
- `main.py`：解析命令行入参后调用 `Manus.create()`，并在终止前确保 `cleanup`。【F:main.py†L1-L36】
- `app/config.py`：`Manus` 导入时读取配置文件（`config/config.toml` 或示例），构建 LLM、浏览器、MCP 等设置并暴露全局 `config`。【F:app/config.py†L10-L217】【F:app/config.py†L219-L290】
- `app/agent/manus.py`：定义 `Manus.create`、MCP 连接、浏览器上下文注入及工具集合，创建实例时会初始化 MCP 客户端与浏览器助手。【F:app/agent/manus.py†L5-L165】
- `app/agent/toolcall.py` 与 `app/agent/react.py`：`Manus` 在执行 `run` 时复用工具调用/ReAct 的 `step→think/act` 流程与工具执行逻辑。【F:app/agent/toolcall.py†L7-L259】【F:app/agent/react.py†L6-L38】
- `app/agent/base.py`：`run` 的状态机、记忆写入、步进循环与 stuck 处理来自基类；`Manus.run` 间接调用这里的实现。【F:app/agent/base.py†L7-L155】

