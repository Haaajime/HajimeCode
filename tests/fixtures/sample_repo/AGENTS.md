# 样例仓库 · 开发指引

面向 Agent 的项目自述。**本文件存在的意义**：让读取者在动手前先知道结构，
不必靠逐层列举去猜。

## 目录结构

- `src/` —— 全部产品代码，标准 src layout
  - `src/main.py` —— **程序入口**，只在 `__main__` 下调用 `run()`
  - `src/core/` —— 核心引擎：`engine.py` 提供 `run()`，`models.py` 定义 `Config`
  - `src/utils/` —— 通用工具：`helpers.py` 目前只有 `slugify()`
  - `src/中文模块/` —— 非 ASCII 包名示例（`常量.py` 里是 `VALUE = 42`）
- `tests/` —— 测试；`tests/fixtures/` 放测试数据
- `docs/` —— 文档，`docs/deep/` 起是深度嵌套示例
- `assets/logo.bin` —— 二进制文件，不要尝试按文本读取
- `empty_dir/` —— 空目录（仅 `.gitkeep`）
- `中文目录/`、`dir with spaces/` —— 非 ASCII 与含空格路径的示例

## 约定

- 改代码优先改 `src/` 下的文件，不要动 `tests/fixtures/`（那是测试数据）。
- `node_modules/` 与 `__pycache__/` 是构建产物，不参与评审。
- 结论里请标明依据的**文件路径**，不要只给文件名。
