# frame.py 说明

- 位置：`deepslide/utils/frame.py`
- 类型：`class Frame(str)`（字符串子类）

## 职责
- 表示一个完整的 Beamer `frame`（`\begin{frame}...\end{frame}`）。
- 提供基本合法性校验，以降低编译错误概率。

## 校验规则
- 必须包含且仅一次 `\begin{frame}` 与 `\end{frame}`。
- 常见环境成对出现：`figure`、`itemize`、`columns`、`column`、`table`、`block`。
- 花括号 `{` 与 `}` 数量相等。

## 工厂方法
- `Frame.from_figure(path: str, caption: str | None = None, width: float = 1.0) -> Frame`
  - 快速生成一个含图片的帧。

## 使用示例
```python
from deepslide.utils.frame import Frame

f = Frame.from_figure("picture/mindmap.jpg", "Mindmap", 0.9)
assert f.is_valid()
```

