# 上游数据集成功能文档

本文档详细说明了引入 `combine124_output.json` 上游数据后，Presenter Agent 所新增的功能特性与改动细节。

## 1. 核心功能更新

### 1.1 上游数据加载与模版选择
*   **功能描述**：系统现在会自动检测 `deepslide/agents/presenter/combine124_output.json` 文件。
*   **交互变化**：
    *   在侧边栏新增了“选择逻辑链条模版”下拉菜单。
    *   用户可以选择 `pipeline`（流水线）、`case_study`（案例驱动）等预设的逻辑链条结构。
    *   保留了“自定义”模式，兼容原有的手动输入功能。

### 1.2 需求摘要展示
*   **功能描述**：当选择上游模版时，系统会解析 JSON 中的 `requirements` 字段。
*   **界面展示**：
    *   侧边栏会显示受众（Audience）、时长（Duration）、风格（Style）等关键需求信息，帮助演讲者保持与上游规划的一致性。
    *   显示该链条模版的推荐理由（Reasons），辅助用户理解为何选择该结构。

### 1.3 智能节点概括 (Smart Summarization)
*   **背景**：上游数据中的节点通常包含较长的文本（如完整段落），直接在矩阵编辑器中显示会导致界面拥挤，难以操作。
*   **解决方案**：
    *   引入了 `MatrixGenerator.summarize_nodes` 方法。
    *   在加载链条时，**实时调用 LLM** 对冗长的节点内容进行智能概括，生成短标签（如 `Background: AI History`）。
    *   **UI 优化**：矩阵的行/列标题和可视化图表均使用这些短标签，提升可读性。

### 1.4 矩阵自动预填
*   **功能描述**：利用上游数据中已定义的 `edges`（边关系）。
*   **优势**：
    *   加载模版时，直接根据 JSON 数据预填 N×N 关系矩阵。
    *   **无需再次消耗 Token** 调用 LLM 生成初始矩阵，大幅提升加载速度。

### 1.5 全文逻辑分析与无损导出
*   **逻辑分析增强**：在点击“生成详细说明”时，系统会将**原始的完整节点文本**（而非概括后的短标签）发送给 LLM。这确保了 AI 能够基于完整的上下文生成深刻、准确的逻辑关系解释。
*   **数据完整性**：
    *   虽然界面上显示的是概括后的标签，但系统在后台 (`st.session_state.raw_nodes_data`) 始终保留了完整的原始数据。
    *   最终导出的 `logic_chain.json`（无论是下载还是自动保存）都包含**完整的原始节点信息**，确保下游环节不会丢失任何细节。

## 2. 代码改动摘要

### `app.py`
*   **状态管理**：新增 `st.session_state.raw_nodes_data` 用于存储上游原始数据。
*   **侧边栏逻辑**：增加了 JSON 读取、模版解析和需求展示的 UI 代码。
*   **加载逻辑**：集成 `generator.summarize_nodes` 调用，并处理矩阵预填逻辑。
*   **导出逻辑**：修改了下载和保存按钮的处理函数，优先使用 `raw_nodes_data` 进行序列化。
*   **解释逻辑**：修改了 `RelationshipExplainer` 的调用参数，传入完整文本列表。

### `matrix_generator.py`
*   **新增方法**：`summarize_nodes(self, raw_nodes)`。
*   **实现细节**：构造专门的 Prompt 让 LLM 将长文本概括为 15 字以内的“角色: 关键词”格式标签。

### `relationship_explainer.py`
*   **调用兼容**：该类本身未做接口破坏性变更，但在 `app.py` 中被调用时，传入的数据源发生了变化（由界面可见文本变为后台原始文本）。

## 3. 数据流向图

```mermaid
graph LR
    A[combine124_output.json] -->|加载| B(App State)
    B -->|原始文本| C[Matrix Generator / Summarizer]
    C -->|短标签| D[Streamlit UI (矩阵/图表)]
    B -->|原始文本 + 边关系| E[Relationship Explainer]
    E -->|详细解释| F[UI Tooltip]
    B -->|原始文本| G[logic_chain.json (导出)]
    F -->|详细解释| G
```
