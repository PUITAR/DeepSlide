# agents/compiler.py 说明

- 位置：`deepslide/agents/compiler.py`
- 作用：驱动 LaTeX 编译，失败时收集错误并打印上下文，后续可接入模型进行自动修复。

## 核心流程
- 初始化：
  - 读取 `.env`，从环境变量加载 `DEEPSEEK_API_KEY`
  - 初始化模型（目前仅保留引擎，未进行自动修复调用）
- 运行：
  - 从 `base_dir/content.tex` 解析 `Content`
  - 调用 `utils.tex_compile.compile_content(base_dir)` 执行编译
  - 成功则返回结果，否则打印错误信息（`message`、`line`）
  - 支持 `max_try` 重试次数

## 错误上下文
- 当出现错误时，从 `content.tex` 中基于报错行号提取前后若干行作为片段 `snippet`，便于阅读与定位。
- 片段与错误消息可用于后续的模型提示词。

## 与编译工具接口
- `utils.tex_compile.compile_content(base_dir)` 返回：
  - `success: bool`
  - `errors: list[dict]`（`message`, `line`）
- 若需要将错误映射到 `Content` 下标，可使用 `Content.to_file` 返回的行映射进行二次定位。

## 使用示例
```python
from deepslide.agents.compiler import Compiler

compiler = Compiler(config_dir="deepslide/config")
res = compiler.run(base_dir="template/base")
print(res["success"], res.get("errors"))
```

