## 核心功能

1.  **逻辑链条矩阵编辑器**：一个交互式工具，用于定义演讲各部分（节点）之间的关系。支持 AI 辅助初始化、手动编辑修正以及详细的逻辑关系解释。
2.  **演讲稿生成**：自动将 LaTeX 幻灯片内容转换为中文演讲稿。

## 目录结构

*   **`app.py`**: **Streamlit 应用程序**。提供全功能的 Web 界面，支持输入节点、编辑关系矩阵、确认逻辑链条以及生成详细解释。
*   **`api_server.py`**: **FastAPI 后端服务**。通过 REST 接口暴露矩阵生成和编辑逻辑，便于集成到其他前端（如 React）中。
*   **`matrix_generator.py`**: 核心逻辑模块，使用 LLM (DeepSeek) 分析输入节点并提议初始的 N×N 关系矩阵。
*   **`relationship_explainer.py`**: 核心逻辑模块，使用 LLM 为已确认的逻辑链条生成详细的文本解释。
*   **`presenterbase.py`**: 包含 `PresenterAgent` 类，负责处理 LaTeX 幻灯片解析并生成连贯的演讲稿（使用 `<next>` 标签分隔）。
*   **`utils.py`**: 工具模块，用于解析 LaTeX 文件（`base.tex`, `content.tex`）以提取幻灯片内容。
*   **`ui/MatrixEditor.jsx`**: React 组件示例，演示如何与 `api_server.py` 接口进行交互。
*   **`test_backend_logic.py`**: 用于测试后端逻辑生成能力的独立脚本。

*注意：如果未提供 API 密钥，工具将回退到模拟数据或空矩阵模式，允许手动操作。*

## 使用指南

### 1. 交互式逻辑矩阵编辑器 (Streamlit)

这是定义逻辑链条的主要界面。

**运行应用：**
```bash
# 请在项目根目录下运行
DEEPSEEK_API_KEY="sk-6286dc11a31e45649dbf55081b8aef20" streamlit run /home/ym/DeepSlide/deepslide/agents/presenter/app.py
```

**操作流程：**
1.  **输入**：在侧边栏输入您的演讲节点（主题或段落）。
2.  **生成**：点击“生成矩阵”。AI 将提议初始连接。
3.  **编辑**：在网格中勾选存在逻辑关系的单元格（行和列代表节点）。
4.  **确认**：点击“确认矩阵”锁定结构，进入可视化确认页面。
5.  **解释与交互**：
    *   点击“生成详细说明”，AI 将分析节点间的深层逻辑。
    *   **交互式图表**：生成的逻辑链条图表支持鼠标悬停（Tooltip）。将鼠标移动到连接线上，即可查看该关系的详细解释。有详细说明的边将高亮显示。
6.  **导出**：
    *   点击“下载逻辑链条 JSON”保存到本地下载目录。
    *   点击“✅ 完成流程”将自动保存 `logic_chain.json` 到 `presenter` 文件夹并结束会话。

### 1.1 使用上游 JSON 数据

如果上游 Agent 已生成逻辑链条与用户需求（例如 `combine124_output.json`），可直接在侧栏选择“上游JSON”作为数据源：
- 默认读取路径：`deepslide/agents/presenter/combine124_output.json`
- 从 `chains` 中选择链条（如 `pipeline`、`case_study`、`myth_fact`、`teaser_then_depth`），点击“加载链条”后自动预填节点与矩阵（依据 `edges` 的 `from_index`、`to_index` 和 `reason`）
- 侧栏同时展示受众、时长、风格、备注等需求摘要，便于与上游保持一致
### 2. 演讲稿生成 (Python SDK)

使用 `PresenterAgent` 编程方式从幻灯片生成演讲稿。

```python
from deepslide.agents.presenter.presenterbase import PresenterAgent

agent = PresenterAgent()
# 生成演讲稿，每页 Slide 内容之间用 <next> 分隔
agent.generate_script(
    base_tex_path="/path/to/base.tex",
    content_tex_path="/path/to/content.tex",
    output_file_path="/path/to/output_script.txt"
)
```
演讲稿生成支持 DeepSeek 兼容端点；逻辑链条已支持从上游 JSON 直接导入并编辑确认。

## 依赖列表

需要安装以下 Python 包：
*   `streamlit`
*   `fastapi`
*   `uvicorn`
*   `python-dotenv`
*   `camel-ai`
*   `pandas`
*   `graphviz`
