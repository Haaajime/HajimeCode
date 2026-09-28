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
| 7 | 能力 | `glob` 输出**不区分符号链接**（`escape_link` 与普通文件看不出差别） | 真实模型实测时明确抱怨："工具未暴露链接信息，无法证实是否为符号链接"。影响对结构的判断 | 待排 |
| 8 | 性能/安全 | `search` **每次全量扫描**（无索引），且正则无超时保护 | 大仓库上单次搜索可能数秒；恶意/失控的灾难性回溯正则（ReDoS）可长时间占用。当前有 `max_results` 早停与控制台步数护栏，风险可接受，但 W6 引入索引前不宜用于超大仓库 | W6 |
| — | 已调研·不做 | ~~"带大小/行数/类型的目录树概览工具"~~ | **经调研判定不是公认最佳方案**：信息密度低、在真实仓库规模（SWE-bench 平均 438K 行 / 3010 文件）不可用、有结构无语义；且**不解决我们实测的失败**（模型已 39/39 列对，错在元数据与计数推理）。降级为"有界 + 诚实截断"的可选导航辅助。详见 `调研_代码库结构如何进上下文.md` | 降级 |

### 修复选项（开放项 2 / 3 一并决定）

前端目前**没有任何路由**，所以后端那段 SPA 兜底路由即使修好顺序，深链接也只会打开一个"未选中任务"的空壳页。两条路：

- **A · 删掉死代码**（最小改动）：去掉 `app.py` 的 `/task/{task_id}` 路由，明确"当前不支持深链接"。前端保持单页状态机。
- **B · 真做深链接**（推荐，W8 报告页迟早要路由）：引入 `react-router`，把 `App.tsx` 的选择逻辑改为读 URL；同时**把 SPA 兜底路由移到 `StaticFiles` 挂载之前**。顺带满足方案 §4.4 的三路由规划。

## 二、已修复

| 日期 | 问题 | 修复 |
|---|---|---|
| 2026-09-28 | **无内容搜索工具**（原开放项 8，调研定位的最大缺口）：工具集只有 `read`/`list_dir`/`glob`，**无法"先定位再读"**，在真实仓库里只能靠猜文件名 | 新增 `search`（正则内容检索）：支持 `path` 起点 / `file_pattern` 过滤 / `ignore_case` / `context_lines`；复用工作区边界、忽略目录与二进制嗅探；单行超长自动裁剪。**返回诚实元数据**（`returned`/`total_matched`/`truncated`/`files_scanned`/`files_with_matches`/`files_skipped_binary`/`files_skipped_large`），并声明"无命中"只对已扫描范围成立。提交 `47bb914` |
| 2026-09-28 | **无方向性文档加载**（原开放项 9）：`intake` 不载入 `AGENTS.md`/`CLAUDE.md`/`README.md`，模型每进一个仓库都要从零摸索结构 | 新增 `project_doc.py`：`intake` 按 `AGENTS.md` → `CLAUDE.md` → `README.md` 取首个命中，上限 **200 行 / 8000 字符**（官方经验：同类文件超 200 行会降低遵循度），超出截断并显式标注；同时写入 `state.project_brief` 供 `plan` 节点使用。无文档时首条消息原样是任务。**真实模型实测**：模型答出"零引用、零测试覆盖"，并主动报告 "未截断，扫描 24 个文件" —— 证明它读懂了诚实元数据契约。提交 `47bb914` |
| 2026-09-28 | **文件读取的两处静默失败**（排查"Agent 读不全文件"时用磁盘真相比对发现）：① `Workspace.is_ignored` 比较**绝对路径** parts，工作区自身路径含 `build`/`dist`/`node_modules` 时**整个工作区被判为忽略** —— `glob` 返回 `[]`、`list_dir` 返回 0 项，而文件确实存在。② `glob`/`list_dir` 的 200 条上限是**静默截断** —— 350 个文件时 `glob` 只给 200 条且无提示，`list_dir` 表头写"共 350 项"却只列 200 | ① 改为只比较**工作区内相对部分**；② `glob` 改返回 JSON 对象（`pattern`/`returned`/`total_matched`/`truncated`/`paths`/`hint?`），`list_dir` 表头显式标注截断；`read` 遇二进制直接说明而非灌乱码。新增 `tests/fixtures/sample_repo/` 与 19 条覆盖度测试（判据为"与磁盘真相逐条比对"）。提交 `610d4b6` |
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

## 五、验证方法：文件读取覆盖度

**为什么需要专门验证**：读取层的失败是**静默**的 —— 不报错、不提示，模型照常给出结论，
只是结论基于残缺的信息。这类 bug 用"看一眼没崩"永远发现不了，必须**与磁盘真相逐条比对**。

**样例仓库**：`tests/fixtures/sample_repo/`（39 个条目 = 14 目录 + 25 文件/链接），刻意覆盖：

| 陷阱 | 样本 |
|---|---|
| 多级子包 | `src/core/`、`src/utils/` |
| 4 层深嵌套 | `docs/deep/nested/more/level3.md` |
| 隐藏文件 | `.gitignore`、`.env.example`、`empty_dir/.gitkeep` |
| 非 ASCII 名 | `中文目录/说明.md`、`src/中文模块/常量.py` |
| 含空格名 | `dir with spaces/note file.txt` |
| 空目录 / 空文件 | `empty_dir/`、`empty_dir/.gitkeep` |
| 二进制 | `assets/logo.bin` |
| 仓库内符号链接 | `linked_readme.md` → `README.md`（可读） |
| 越界符号链接 | `escape_link` → 工作区外（应列出但读取须被拒） |
| 被忽略目录 | 测试运行时在临时目录创建 `node_modules/`、`__pycache__/`，须排除且不牵连同级 |

**两类判据**（`tests/test_fs_coverage.py`，19 条）：

1. **覆盖率**：`glob("**/*")` 的结果与 `os.walk` 得到的磁盘真相**逐条比对**（不漏、不多、`truncated` 为 false）。
2. **诚实性**：制造超过上限的文件数，断言 `truncated=true`、`total_matched` 等于真实总数、并给出可操作 `hint` —— 而不是"返回非空就算过"。

**真实模型侧的对齐检查**：把工作区指到样例仓库跑一次，核对模型给出的**总数与分类计数**
是否与 `find` 一致。实测（2026-09-28）：总条目 39 ✓、`.py` 10 ✓、隐藏文件 3 ✓；
分类明细（目录/文件/`.md`）有 off-by-one —— 说明**工具层已正确，偏差出在模型推理层**。


