# 论文转PPT需求收集模块使用文档

## 概述

本模块是一个基于 CAMEL-AI 的智能需求收集系统，用于与用户对话以收集论文转PPT所需的关键信息，并输出结构化的 JSON 配置文件。

## 项目结构

```
Chatter/
├── app.py                    # Streamlit 前端界面（用户交互入口）
├── ppt_requirements_collector.py  # 核心业务逻辑类
├── camel_client.py           # CAMEL-AI 客户端封装
├── utils.py                  # 工具函数
└── requirements.txt          # 依赖列表
```

## 核心类说明

### 1. `PPTRequirementsCollector`

这是核心业务逻辑类，负责管理整个需求收集流程。

#### 初始化
```python
from ppt_requirements_collector import PPTRequirementsCollector

# 创建收集器实例
collector = PPTRequirementsCollector(env_path="/path/to/.env")
```

#### 主要方法

- **`set_paper_file(file_name)`**
  - 设置论文文件名
  - 参数：`file_name` - 论文文件名（字符串）

- **`process_user_input(user_input)`**
  - 处理用户输入，返回 AI 回复
  - 参数：`user_input` - 用户输入内容（字符串）
  - 返回：AI 回复内容（字符串）
  - **注意**：此方法会自动更新内部状态，包括提取 JSON 数据

- **`get_requirements()`**
  - 获取当前收集到的完整需求数据
  - 返回：包含 `paper_info`、`conversation_requirements`、`conversation_history` 的字典

- **`confirm_requirements()`**
  - 手动标记需求为已确认状态
  - 通常用于强制确认流程

- **`reset()`**
  - 重置收集器到初始状态
  - 清空所有历史记录和已确认的需求

#### 主要属性

- **`is_confirmed`** (布尔值)
  - 表示是否已收集到结构化 JSON 数据并确认
  - 当 AI 输出 JSON 时自动设为 `True`

- **`conversation_requirements`** (字典)
  - 存储从 AI 回复中提取的结构化数据
  - 格式示例：
    ```json
    {
      "audience": "本专业学生",
      "duration": "十五分钟",
      "focus_sections": ["背景和意义"],
      "style": "学术严谨",
      "special_notes": "使用复旦logo，蓝色系"
    }
    ```

### 2. `CamelAIClient`

CAMEL-AI 客户端封装类，负责与 AI 模型通信。

#### 初始化
```python
from camel_client import CamelAIClient

client = CamelAIClient(env_path="/path/to/.env")
```

#### 主要方法

- **`get_response(user_input)`**
  - 向 AI 发送用户输入并获取回复
  - 参数：`user_input` - 用户输入（字符串）
  - 返回：AI 回复（字符串）

- **`clear_memory()`**
  - 清空 AI 对话记忆

## 使用流程

### 1. 基本使用

```python
from ppt_requirements_collector import PPTRequirementsCollector

# 创建收集器
collector = PPTRequirementsCollector()

# 设置论文文件
collector.set_paper_file("my_paper.tex")

# 开始对话流程
ai_reply = collector.process_user_input("请开始收集PPT需求。")

# 继续处理用户输入
while not collector.is_confirmed:
    user_input = input("用户输入: ")  # 或从其他渠道获取
    ai_reply = collector.process_user_input(user_input)
    print(f"AI: {ai_reply}")

# 获取最终结果
requirements = collector.get_requirements()
print(requirements)
```

### 2. 与后端集成

```python
# 在后端处理流程中
def process_paper_to_ppt(paper_file, user_requirements_json):
    """
    处理论文转PPT的核心逻辑
    """
    # 解析 JSON 配置
    config = json.loads(user_requirements_json)
    
    # 提取关键信息
    paper_info = config["paper_info"]
    requirements = config["conversation_requirements"]
    
    # 使用配置生成 PPT
    audience = requirements.get("audience", "通用受众")
    duration = requirements.get("duration", "30分钟")
    focus_sections = requirements.get("focus_sections", [])
    style = requirements.get("style", "标准")
    special_notes = requirements.get("special_notes", "")
    
    # 执行 PPT 生成逻辑...
    return ppt_file_path

# 调用示例
requirements_json = get_requirements_from_frontend()  # 从前端获取
ppt_path = process_paper_to_ppt("input.tex", requirements_json)
```

## 输出 JSON 格式说明

```json
{
  "paper_info": {
    "file_name": "test.tex"
  },
  "conversation_requirements": {
    "audience": "目标受众（如：本科生、研究生、行业专家）",
    "duration": "演讲时长（如：15分钟、30分钟）",
    "focus_sections": ["重点章节列表", "如：引言", "方法", "结论"],
    "style": "PPT风格（如：学术严谨、简洁明了）",
    "special_notes": "特殊要求（如：使用特定Logo、配色方案）"
  },
  "conversation_history": [
    {
      "role": "assistant/user",
      "content": "对话内容"
    }
  ]
}
```

## 环境配置

### 1. 依赖安装

```bash
pip install camel-ai streamlit python-dotenv
```

### 2. 环境变量配置

创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your_api_key_here
DEFAULT_MODEL_PLATFORM_TYPE=deepseek
DEFAULT_MODEL_TYPE=deepseek-chat
```

### 3. 文件路径

- 默认 `.env` 路径：`/home/ym/DeepSlide/deepslide/config/env/.env`
- 可通过 `env_path` 参数自定义

## 错误处理

### 常见问题

1. **CAMEL-AI 初始化失败**
   - 检查 API Key 是否正确
   - 确认网络连接是否正常

2. **JSON 解析失败**
   - AI 可能未按要求输出 JSON 格式
   - 检查 `conversation_requirements` 是否为空

3. **状态机异常**
   - 使用 `collector.reset()` 重置状态
   - 检查 `app_state` 变量

### 健壮性建议

```python
# 在集成时添加错误处理
try:
    requirements = collector.get_requirements()
    # 验证必需字段
    if not requirements["conversation_requirements"]:
        raise ValueError("未收集到有效的需求数据")
    
    # 验证 JSON 格式
    required_fields = ["audience", "duration", "focus_sections"]
    for field in required_fields:
        if field not in requirements["conversation_requirements"]:
            raise ValueError(f"缺少必需字段: {field}")
            
except Exception as e:
    print(f"需求收集失败: {e}")
    # 回退到默认配置或重新开始
```

## 扩展建议

1. **增加字段验证**：在 `utils.py` 中添加更多数据验证规则
2. **支持更多 AI 模型**：修改 `CamelAIClient` 以支持其他模型
3. **对话历史分析**：利用 `conversation_history` 进行需求分析
4. **批量处理**：扩展 `PPTRequirementsCollector` 支持批量处理

## 维护说明

- **版本兼容性**：注意 CAMEL-AI API 可能的变更
- **性能优化**：长时间对话可能影响 AI 响应速度
- **日志记录**：建议添加对话日志用于调试和分析
- **单元测试**：核心逻辑应有对应的测试用例

---

*文档版本：v1.0*  
*最后更新：2025-12-12*