# agents/compiler.py 说明

- 位置：`deepslide/agents/compiler.py`
- 作用：驱动 LaTeX 编译，失败时收集错误并打印上下文，后续可接入模型进行自动修复。

## 核心流程
- 初始化：
  - 读取 `.env`，从环境变量加载 `DEFAULT_MODEL_API_KEY`
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



我已成功完成功能升级，将编译器转化为一个独立运行的智能代理，能够推理并修复复杂的LaTeX错误。交付的改进包括：1. 思维代理工作流：代理现在会在执行操作前明确输出其思考过程（THOUGHT:...），便于调试其推理逻辑。它严格遵循"思考->观察->行动->验证"的循环流程。2. 编译工具化：新增compile_pdf()工具函数，使代理能实时验证修复效果而无需交还主循环控制权，支持多步调试（如修复一个错误后重新编译，再定位下一个错误）。3. 增强可视化：实现log_tool_usage装饰器，所有工具调用（文件读取、文本搜索、脚本执行）均会在控制台记录参数和截断结果，完整透明呈现代理行为。4. 复杂案例验证成功：括号不匹配场景：代理通过check_balance准确识别多余{并删除；表格列数不符：代理发现\begin{tabular}{|c|c|}（2列）与实际内容（3列）不匹配，将定义修正为{|c|c|c|}。当前系统可稳健处理简单语法错误（通过快速正则修复）和深层结构错误（通过推理代理解决）。