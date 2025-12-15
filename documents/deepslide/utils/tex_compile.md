# tex_compile.py 说明

- 位置：`deepslide/utils/tex_compile.py`
- 作用：编译 `base.tex` + `content.tex` 并解析错误信息。

## 核心函数
- `compile_content(content: Content, base_dir: str) -> dict`
  - 行为：写入 `content.tex`，选择引擎，执行两次编译，解析 `.log`。
  - 返回：
    - `success: bool`：是否编译成功
    - `errors: list[dict]`：每条错误包含：
      - `message: str`
      - `line: int | None`（若能从 `.log` 的 `l.<n>` 提取）

## 错误解析策略
- 函数：`_parse_log_for_errors(log_path)`
  - 规则：当遇到以 `!` 开头或含 `LaTeX Error` 的行视为错误；向下最多 10 行查找 `l.<行号>` 并提取数字作为报错行号。

## 引擎检测
- 函数：`_detect_engine(base_dir, ["xelatex", "pdflatex"])`
  - 优先读取 `base.tex` 的魔法注释 `TeX program = xelatex`，否则回退到系统可用的 `xelatex/pdflatex`。

## 使用示例
```python
from deepslide.utils.content import Content
from deepslide.utils.tex_compile import compile_content

c = Content(); c.from_file("template/base/content.tex")
res = compile_content(c, "template/base")
print(res["success"], res["errors"])  # 错误含 message 与行号
```

