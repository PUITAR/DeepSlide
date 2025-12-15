# content.py 说明

- 位置：`deepslide/utils/content.py`
- 类型：`class Content(list[Section | Frame])`

## 职责
- 维护一组按顺序排列的 LaTeX 片段（章节和页面）。
- 提供从 `content.tex` 解析到对象列表，以及将对象列表回写为 `content.tex`。
- 对各个元素执行基本有效性校验。

## 关键方法
- `from_file(file_path: str) -> None`
  - 逐行读取 `content.tex`；跳过前导标记 `%% ITEM ...` 行；
  - 当遇到 `\begin{frame}` 进入帧收集，直到匹配到 `\end{frame}`；期间的文本组装为一个 `Frame` 对象。
  - 单行包含 `\section` / `\subsection` / `\subsubsection` 则生成 `Section` 对象。
- `to_file(file_path: str) -> list[tuple[int,int,str]]`
  - 为每个元素写入前导标记 `%% ITEM {idx} TYPE {type}`，紧随其后写入元素文本；
  - 返回映射 `[(start_line, end_line, type), ...]`，用于将 `.log` 的报错行号映射到具体元素下标。
- `is_valid() -> bool`
  - 逐项调用 `is_valid()`，发现无效项时打印并返回 False。

## 使用示例
```python
from deepslide.utils.content import Content
from deepslide.utils.section import Section
from deepslide.utils.frame import Frame

c = Content(); c.from_file("template/base/content.tex")
assert c.is_valid()

c.append(Section("\\section{New Section}"))
c.append(Frame.from_figure("picture/mindmap.jpg", "Mindmap", 0.9))

mapping = c.to_file("template/base/content.tex")
# mapping: [(start_line, end_line, type), ...]
```
