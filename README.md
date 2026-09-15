# Agent Harness 框架

自研的类 Claude Code 通用 Agent「载体」（Harness）：复现 **模型决定、载体执行** 的工程范式，统一封装循环、工具、上下文与权限，作为上层 Agent 应用（如 RepoPilot）的底层。

> 当前为 **核心层起步版**：Agent 主循环 + 工具分发注册表 + 模型 provider 抽象已可用；上下文压缩、记忆、权限、子代理、MCP 等在后续里程碑逐步加入（见 `../项目方案/实现方案_AgentHarness框架.md`）。

## 现状能力

- **Agent 主循环**：`messages→LLM→tool_use→工具执行→tool_result 回填→继续`，无工具调用时结束；带最大步数保护。
- **工具分发注册表**：`ToolRegistry` 注册/列 schema/分发；新工具注册即可用，**不动主循环**；工具执行异常回传给模型自纠，不中断。
- **Provider 抽象**：OpenAI 兼容协议实现，当前默认对接 **DeepSeek**；后续加 Anthropic 只需新增 Provider 子类。

## 环境

- Python **3.10**（本机 uv 行列可离线获得，规避网络下载 3.11）
- 依赖由 `uv` 管理：`openai`、`python-dotenv`、`pytest`(dev)

## 快速开始

```bash
cd agent-harness
uv sync
cp .env.example .env      # 填入 DEEPSEEK_API_KEY 后运行
uv run pytest -q          # 全部 mock 单测,不耗 API
# 真实跑一个带工具的任务(会消耗极少 token)
uv run agent-harness "请用 add 工具计算 42+99 的和"
```

## 目录结构

```
src/agent_harness/
├── config.py      # .env 加载(密钥不硬编码)
├── providers.py   # 模型 Provider 抽象(DeepSeek OpenAI 兼容)
├── tools.py       # Tool + ToolRegistry + 内置工具
├── loop.py        # Agent 主循环
└── cli.py         # 命令行入口
tests/test_loop.py # 核心循环/分发/异常/步数上限单测(零 API 消耗)
```

## 安全说明

- `.env` 含真实密钥，已加入 `.gitignore`，**禁止提交**；只提交 `.env.example` 占位。
- 当前内置工具（`add`/`echo`）安全无副作用；后续引入 `bash` 等工具时必须配合权限白名单（见方案 s03）。