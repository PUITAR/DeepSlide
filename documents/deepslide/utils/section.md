# section.py 说明

- 位置：`deepslide/utils/section.py`
- 类型：`class Section(str)`

## 职责
- 表示章节命令：`\section{}` / `\subsection{}` / `\subsubsection{}`。

## 工厂方法
- `Section.section(title: str)`
- `Section.subsection(title: str)`
- `Section.subsubsection(title: str)`

## 校验规则
- 正则匹配命令格式：`^\\(section|subsection|subsubsection)\{.*\}$`
- 花括号配对：`{}` 数量相等。

## 使用示例
```python
from deepslide.utils.section import Section

s1 = Section.section("Introduction")
s2 = Section.subsection("Motivation")
s3 = Section.subsubsection("Details")
for s in (s1, s2, s3):
    assert s.is_valid()
```

