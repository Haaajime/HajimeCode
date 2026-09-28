# 已知问题清单（Hajime2Code）

> 发现即记，闭环后移到「已修复」并标注日期，不删除记录。
> 与 `开发进度与优先级.md` 的「已知风险」互补：那边记**战略层风险**（会不会被问穿、进度会不会崩），
> 这里记**具体可闭环的问题**（文档与实现对不上、未验证项、技术债）。

## 一、开放中

| # | 类别 | 问题 | 影响 | 计划 |
|---|---|---|---|---|
| 1 | 安全 | `tools/fs.py` 的 `write` / `edit` **尚未接入权限层**，当前可直接写盘 | README 曾称"默认被权限层拦截"，与实现不符（文档已修，代码待补） | W3 |
| 2 | **缺陷** | **`/task/{task_id}` 路由返回 404**：`app.py` 里 `StaticFiles` 挂在 `/`（L131），而 SPA 兜底路由注册在其后（L133），被挂载点遮蔽，永不生效 | SPA 深链接 / 刷新页面直接 404（返回 JSON `{"detail":"Not Found"}`）。curl 实测：`/` → 200，`/task/{id}`、`/tasks/{id}`、`/reports` → 全部 404 | 待定（见「修复选项」） |
| 3 | 工程 | **前端实际没有路由**：`web/package.json` 无 `react-router`，`App.tsx` 靠 `selectedId` 状态切换，任务详情不是独立页面 | 与方案 §4.4 规划的 `/`、`/tasks/:id`、`/reports` 三路由不符；任务无法分享链接、刷新即丢选择 | 待定（W8 报告页前需定） |
| 4 | 工程 | 前后端契约为**手写**（`web/src/api.ts`），未接 `openapi-typescript` 自动生成 | 契约漂移风险（后端改字段前端不报错） | W8 前 |
| 5 | 工程 | 任务记录**仅存内存**（`serve/store.py`），服务重启即丢 | 无法回看历史任务 | W4 |
| 6 | 口径 | 成本单价为**占位值**（`config.py` 的 `price_*`），未按 DeepSeek 官方定价校准 | 引用成本结论前必须校准，否则 E4 的绝对值不可信 | W5 |

### 修复选项（开放项 2 / 3 一并决定）

前端目前**没有任何路由**，所以后端那段 SPA 兜底路由即使修好顺序，深链接也只会打开一个"未选中任务"的空壳页。两条路：

- **A · 删掉死代码**（最小改动）：去掉 `app.py` 的 `/task/{task_id}` 路由，明确"当前不支持深链接"。前端保持单页状态机。
- **B · 真做深链接**（推荐，W8 报告页迟早要路由）：引入 `react-router`，把 `App.tsx` 的选择逻辑改为读 URL；同时**把 SPA 兜底路由移到 `StaticFiles` 挂载之前**。顺带满足方案 §4.4 的三路由规划。

## 二、已修复

| 日期 | 问题 | 修复 |
|---|---|---|
| 2026-09-28 | **主图在真实模型上根本跑不动**（原开放项 2）：`plan` / `reflect` 两个节点用 `with_structured_output` 的**默认** `method="json_schema"`，DeepSeek 的 OpenAI 兼容接口不支持该响应格式，返回 `400 This response_format type is unavailable now`。**修复前从未有一次真实模型端到端成功** | 实测三种方式：`json_schema`（默认）✗ / `json_mode` ✗ / **`function_calling` ✓**。在 `models.py` 收敛出 `structured_output()` helper 显式指定 `function_calling`，`plan.py`、`reflect.py` 改用它。**修复后真实端到端跑通**：状态 `done`、LLM 调用 5、tokens 6233/1462、缓存命中率 43.1%、成本 ¥0.0120；结论经独立核对正确（模型答 27 个 `.py`，`find` 实测 27）。提交 `ba02b0a` |
| 2026-09-28 | **「浏览器内前端渲染未验证」已闭环**：W2 只验证到事件流产生 54 条事件，未验证 DOM 真的渲染出来 | 用**系统已装的 Chrome + CDP**（零安装，见「验证方法」）实测桩图服务：时间线（节点/token 流/工具卡片/tool.finished）、任务列表、计划、缓存命中率 91% 均**正确渲染**。**同时发现开放项 2 的 404 缺陷** |
| 2026-09-28 | **周次编号误标**：`W4` 被同时用在两个不同阶段上——"权限审批"应属 **W3**、"机制层中间件"应属 **W5**。涉及 `src/hajime2code/tools/fs.py`、`README.md`、`项目方案/新项目方案_Hajime2Code.md`（§4.2 正文 + v4.1 变更记录） | 分别更正为 W3 / W5。**根因**：方案 v4 重排路线表后（W2 并入前端、W3 提为沙箱审批），`技术栈重规划_讨论稿.md`（已归档）的旧编号——那里 W4 =「机制层中间件化」——被误沿用到 v4.1 正文。归档稿按约定不改写，此处记录以免再被误导 |
| 2026-09-28 | `README.md` 架构图写作 `CLI / (W7 起) FastAPI + SSE`，但 SSE 已于 **W2** 落地 | 改为 `CLI / Web 控制台（FastAPI + SSE，W2 落地）` |
| 2026-09-28 | `cli.py` 注释称"流式输出与交互式 REPL 在 W2 落地"，实际 W2 只落地**服务端 SSE**，CLI 仍走 `graph.invoke` 一次性输出 | 注释改为与实现一致，并明示 CLI 无 token 级流式 |
| 2026-09-28 | `README.md` 安全说明称写工具"默认会被权限层拦截、需显式放行"，实际权限层未落地 | 改为明示"当前直接可写盘、W3 落地拦截" |

## 三、核对无误、无需改动

通读时怀疑但经核对**确认正确**的引用，记在此处避免重复排查：

- `serve/store.py` 注释「持久化留到 W4」→ 正确（路线表 W4 = 持久化 + time-travel）。
- `docs/开发日志.md` W1 条目「W5 策略改为复用官方 + 只自研官方没有的」→ 与路线表 W5 一致，正确。
- 进度表「文件工具（读 + 写 + 编辑）P0 ✅」→ 工具本身确已实现，判定成立（权限层另见开放项 1）。

## 四、验证方法：零安装的前端渲染检查

**结论：不需要安装 Chromium 或 Playwright。** 本机已有 Google Chrome，用 CDP 直接驱动它即可，零下载、零 npm 依赖。

为什么不直接用 `chrome --headless --screenshot`：它靠 `load` 事件决定截图时机，而本项目是 SPA（要等 React 挂载 + SSE 事件回放），加 `--virtual-time-budget` 又会在 SSE 长连接上**永远等不到空闲而挂住**。CDP 能显式"等 N 毫秒再截"，稳定可控。

步骤（假模型桩图，**零 API 消耗**）：

1. **起桩服务**：用 `create_app(settings=..., graph_factory=lambda _ws: StubGraph())` 注入假图（照 `tests/test_serve_api.py` 的 `StubGraph` 扩展），`uvicorn.run(app, port=8123)`。桩图产出覆盖全部事件类型的流（node.started/finished、llm.token、tool.started/finished、budget.updated、task.finished）。
2. **提交任务**：`curl -X POST /api/tasks` 拿 `task_id`（假图跑完即 `done`）。
3. **驱动浏览器**：`Chrome --headless=new --remote-debugging-port=9333 --user-data-dir=<临时目录> about:blank`，再用 Node 连 CDP（Node 22 自带全局 `WebSocket`，**无需任何 npm 包**）：
   - `Page.enable` → `Emulation.setDeviceMetricsOverride` → `Page.navigate` → `sleep(N)` → `Page.captureScreenshot`
   - 需要交互时加 `Runtime.evaluate` 执行 `document.querySelector(sel).click()`，即可点进任务详情看时间线。
4. **收尾**：`lsof -ti tcp:<port> | xargs kill` 关掉服务与 Chrome。

**踩坑记录**（血泪换的，别再踩）：

- 别用 `pkill -f <关键词>`：模式会匹配到**当前 shell 自己的命令行**，导致自杀（且拿不到任何输出）。一律按**端口 / PID** 精确杀。
- macOS 没有 GNU `timeout` 命令；要限时用后台启动 + 轮询产物文件。
- Chrome 必须用**独立的 `--user-data-dir`**，否则会和正在运行的 Chrome 实例冲突。
- 截图时用 `deviceScaleFactor: 2` 出图更清晰（便于人工核对渲染细节）。

