# Transformer Agents

## 概述
`Transformer` 模块负责将 LaTeX 论文源码转换为适合 PPT 演示的结构化内容。核心包含两个 Agent：
- **Divider**: 负责将长文本划分为演讲板块（Section）。
- **Compressor**: 负责将板块内容压缩为具体的演讲稿与 PPT 帧（Frame）。

## Divider Agent
位于 `deepslide/agents/transformer/divider.py`。

### 设计思路
不同于简单的按行号切割，Divider 采用**两阶段逻辑**：
1. **对象提取 (Object Extraction)**：识别具有独立语义的单元（文本块、图片、表格、公式）。
2. **板块映射 (Section Mapping)**：根据演讲逻辑（如 Intro -> Method -> Exp），将对象归类到对应板块。

### 模型与配置
- **模型**: `deepseek-reasoner` (OpenAI Compatible)
- **输入**: 完整 `.tex` 源码 + 可选的 `schema`（建议板块结构）。
- **输出**: JSON 列表，每个元素包含 `title`、`rationale` 和 `objects` 列表。
- **回退机制**: 若无 API Key 或模型解析失败，自动降级为基于 `\section` 命令的启发式划分。

### 用法
```python
from deepslide.agents.transformer.divider import Divider

divider = Divider()
# schema 可选，提示模型按此结构组织
sections = divider.divide("path/to/paper.tex", schema=["Introduction", "Method", "Results"])

for sec in sections:
    print(f"板块: {sec['title']}")
    for obj in sec['objects']:
        print(f" - [{obj['type']}] {obj['content'][:50]}...")
```

## Compressor Agent
位于 `deepslide/agents/transformer/compressor.py`。

### 功能
将 Divider 输出的 `sections` 转换为具体的幻灯片内容帧。
- 为每个板块生成 1-3 个 PPT 页。
- 每页包含：
  - `speech`: 第一人称演讲台词。
  - `ppt`: 符合 Beamer 语法的 `frame` 代码。
  - `section`: 若为板块首个帧，附带 `\section{...}`。

## 测试
测试用例位于 `test/test_divider/`。

运行测试：
```bash
python3 -m pytest test/test_divider/test_divider.py
```
- `test_divider_fallback`: 验证无 API Key 时的回退逻辑是否正确提取了章节。
- `test_divider_with_mock_model`: 验证模型接口调用（需配置 API Key）。
