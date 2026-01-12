## 1. analyze_alignment.py
*   **输入**：
    *   `content.tex`: 包含 `\begin{frame}...\end{frame}` 的 Latex 源码。
    *   `speech_script.txt`: 包含 `<next>` 分隔符的演讲稿文本。
*   **处理逻辑**：
    *   调用 DeepSeek 大模型，分析每页 Slide 与每段 Speech 的语义相关性，进行最佳匹配。
    *   自动识别并标记无对应 Slide 的 Speech 段落（如开场白、结束语），添加 `<add>` 标签。
*   **输出**：
    *   `alignment.json`: 包含匹配好的 `(Slide Content, Speech Content)` 二元组列表。
    *   更新后的 `speech_script.txt`。

**用法**
```bash
python3 analyze_alignment.py --content content.tex --speech speech_script.txt
```

---

## 2. generate_slide_graph.py
*   **输入**：
    *   `alignment.json`: 对齐后的二元组数据。
    *   `logic_chain.json`: 宏观的 Section 级别逻辑引用关系（如 "Conclusion" -> "Methods"）。
    *   `content.tex`: 用于解析 Section 结构。
*   **默认模式 (无 LLM)**：基于逻辑链规则进行全连接推导。如果 Section A 引用 Section B，则生成从 A 中所有 Slide 指向 B 中所有 Slide 的边。
*   **LLM 模式 (`--use_llm`)**：调用 DeepSeek API 进行深度语义分析，识别具体的 Slide 到 Slide 的精准引用。
*   **输出**：
    *   `slide_relationships.json`: 包含节点（Slide信息）和边（引用关系）的图结构数据。

**用法**
```bash
# 默认模式（基于规则）
python3 generate_slide_graph.py

# LLM 增强模式（基于语义）
python3 generate_slide_graph.py --use_llm
```

---

## 3. generate_slide_graph_with_metrics.py
*   利用 LLM 综合分析 Slide 视觉内容和 Speech 口语内容，提取以下关键指标属性：
    *   `is_hook`: 是否包含吸引注意力的“钩子”（用于 OHS 指标）。
    *   `is_stimulus`: 是否包含提问、个人观点等“刺激源”（用于 RS 指标）。
    *   `key_concepts`: 提取核心知识点（用于 CLC 指标的知识图谱构建）。
*   **输入/输出**：与标准版类似，但输出的 JSON 文件包含 `metric_attributes` 字段。
*   **输出文件**：
    *   `slide_graph_with_metrics.json`

**用法**
```bash
python3 generate_slide_graph_with_metrics.py --use_llm
```


