# Hajime2Code

基于 **LangGraph** 构建的**可编程、可评测、可消融**的编码 Agent 运行时。

> 定位：不做"另一个能跑的编码 Agent"，做"一个可编程、可评测、可消融的编码 Agent 运行时"。
> 用 LangGraph 图作为 Agent 的执行骨架，把每个机制做成可开关的一等公民，再用实验回答"哪种编排 / 上下文策略在什么任务上更好"。

## 与 HajimeCode 的关系

`HajimeCode`（手写 Agent Harness）是本项目的 **baseline 参考实现**，两者共用同一套评测任务集，用于 E3 范式对照实验：
`先自研一遍（懂底层）→ 再用框架重做（懂工程）→ 用量化数据对比（有洞察）`。

## 快速开始

```bash
uv sync                        # 安装依赖
cp .env.example .env           # 填入 DEEPSEEK_API_KEY（或复用 ../HajimeCode/.env）
uv run python -m pytest        # 离线单测，零 API 消耗
```

真实调用（消耗少量 token）：

```bash
uv run hajime2code -w . "统计 src 下的 Python 文件数量，并说明目录结构"
```

## 架构

```
CLI / (W7 起) FastAPI + SSE
        │
        ▼
LangGraph 主图（手写 StateGraph）
   intake → plan → act → reflect ─┬─→ act      未完成则继续
                                   └─→ finalize → END
        │
        ├── act 节点内部：create_agent + Middleware 的 ReAct 子图
        └── 预算护栏：steps / LLM 调用数 / token / 成本（含缓存命中）
```

- **主图管"下一步做什么"**：规划、反思、回退、并行、人工审批、预算裁剪。
- **子图管"这一步怎么做完"**：一次 ReAct 执行（模型调用 → 工具调用 → 重试）。

## 目录结构

```
src/hajime2code/
├── config.py        # pydantic-settings 配置（含成本单价）
├── models.py        # ChatOpenAI → DeepSeek
├── budget.py        # token / 成本 / 缓存命中统计
├── workspace.py     # 工作区路径边界
├── tools/fs.py      # read / glob / list_dir / write / edit
├── graph/
│   ├── state.py     # AgentState + reducers（add_messages / add_budget）
│   ├── builder.py   # StateGraph 装配与 compile
│   └── nodes/       # intake / plan / act / reflect / finalize
└── cli.py           # 命令行入口
```

## 工程约定

- 依赖用 **uv** 管理，依赖声明只写在 `pyproject.toml`。
- 每个功能必须有 **离线单测**（零 API 消耗）；真实模型调用仅用于极小 token 冒烟。
- 密钥只从 `.env` / 环境变量读取，严禁硬编码；只提交 `.env.example`。
- 提交前跑通：`uv run ruff check . && uv run mypy && uv run python -m pytest`。

## 安全说明

- 工具层所有文件访问都被 `Workspace` 限制在工作区内，越界路径直接拒绝。
- 有副作用的工具（`write` / `edit`，后续的沙箱 `bash`）默认会被权限层拦截，需显式放行（W4 落地）。
