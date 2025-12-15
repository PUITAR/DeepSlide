## 📊 **ChapterNode 数据结构**

```python
class ChapterNode:
    # 基本属性
    node_id: str           # 唯一标识符 (uuid)
    title: str             # 章节标题
    content: str           # 原始 LaTeX 内容
    level: int             # 层级 (1-5, 1为顶级)
    node_type: NodeType    # 节点类型 (SECTION/SUBSECTION/CONTENT等)
    
    # 树结构关系
    parent_id: Optional[str]    # 父节点ID
    children_ids: List[str]     # 子节点ID列表
    
    # 位置信息
    position: PositionInfo      # 在原文档中的位置
    # - start_char: int    # 起始字符位置
    # - end_char: int      # 结束字符位置
    # - source_file: str   # 源文件名
    
    # 内容度量
    metrics: ContentMetrics     # 内容统计指标
    # - char_count: int    # 字符数
    # - word_count: int    # 单词数
    # - sentence_count: int # 句子数
    
    # 元数据
    metadata: Dict[str, Any]    # 扩展元数据
    # - latex_command: str # LaTeX命令 (如 "\section{...}")
    # - title_raw: str     # 原始标题 (含LaTeX命令)
    # - original_level: int # 原始层级
    
    # 重要性与标签
    importance: float      # 重要性 (0.0-1.0)
    tags: Set[str]         # 语义标签集合
    
    # 语义关系
    relationships: Dict[RelationshipType, Set[str]]  # 与其他节点的关系
    # - SEQUENCE: 序列关系
    # - SIMILAR: 相似关系  
    # - DEPENDENT: 依赖关系
    # - EXAMPLE: 示例关系
```

---

### ⚙️ **Divider 使用方法**

#### 1. **导入和初始化**
```python
from divider import Divider

divider = Divider()  # 自动加载 RoughDivider
```

#### 2. **执行分割**
```python
# 加载 LaTeX 内容
with open("document.tex", "r", encoding="utf-8") as f:
    latex_content = f.read()

# 设置 Planner 指令
planner_instructions = {
    # 粗分控制
    "max_section_depth": 3,          # 最大层级深度
    "max_sections": 12,              # 最大章节数量
    "merge_short_threshold": 150,    # 短章节合并阈值(字符)
    "focus_keywords": ["introduction", "method", "result", "conclusion"],
    "skip_keywords": ["reference", "appendix"],
    
    # CAMEL 细化控制 (可选)
    "use_camel_refinement": True,    # 是否使用 CAMEL 细化
    "refine_threshold": 400,         # 需要细化的长度阈值
    "min_segment_length": 80,        # 细分最小长度
    "max_segments_per_node": 3,      # 单节点最大片段数
    "refine_style": "ppt_bullet_points",  # 细化风格
    
    # 资源控制
    "debug_mode": True
}

# 执行分割
nodes, feedback = divider.divide(latex_content, planner_instructions)
```

---

### 📋 **Planner 指令详解**

#### **必需指令 (粗分阶段)**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_section_depth` | int | 3 | 最大分割层级 (1-5) |
| `max_sections` | int | 15 | 最大章节数量 (超量则合并) |
| `merge_short_threshold` | int | 100 | 短内容合并阈值(字符) |
| `focus_keywords` | List[str] | [] | 重点章节关键词 |
| `skip_keywords` | List[str] | [] | 跳过章节关键词 |

#### **可选指令 (CAMEL 细化)**
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `use_camel_refinement` | bool | False | 是否启用 CAMEL 细化 |
| `refine_threshold` | int | 800 | 需要细化的长度阈值 |
| `min_segment_length` | int | 150 | 细分最小长度 |
| `max_segments_per_node` | int | 5 | 单节点最大片段数 |
| `refine_style` | str | "ppt_bullet_points" | 细化风格 |
| `build_semantic_relations` | bool | True | 是否构建语义关系 |
| `semantic_relation_threshold` | float | 0.7 | 关系置信度阈值 |

---

### 📈 **返回结果结构**

#### **返回值**: `(nodes: List[ChapterNode], feedback: Dict[str, Any])`

#### **Feedback 结构**
```json
{
  "status": "success",           // 或 "warning" (回退时)
  "process_method": "rough_then_camel",  // 或 "rough_only"
  "has_camel_results": true,     // 是否使用了 CAMEL 结果
  "final_node_count": 15,        // 最终节点数量
  
  "rough_division": {
    "status": "success",
    "method": "structural_rough_division_v2",
    "raw_section_count": 68,     // 原始章节数
    "merged_section_count": 15,  // 合并后章节数
    "content_coverage_ratio": 0.998,  // 内容覆盖率
    "merge_operations": 8        // 合并操作数
  },
  
  "refinement": {
    "status": "success",         // 或 "error" (失败时)
    "method": "camel_refinement",
    "segments_created": 3,       // 创建的片段数
    "relationships_built": 12,   // 建立的关系数
    "camel_relation_calls": 4,   // CAMEL 关系调用数
    "fallback_reason": "camel_initialization_failed"  // 回退原因(可选)
  },
  
  "warnings": [                  // 警告信息(可选)
    "camel_initialization_failed"
  ],
  
  "suggestions": [               // 优化建议
    "检查 CAMEL 配置",
    "降低 max_sections 以减少合并"
  ]
}
```

---

#### **回退策略示例**
```python
# 当 CAMEL 不可用时
if camel_fails:
    return rough_nodes  # 返回粗分结果
    # feedback 中会包含:
    # "status": "warning",
    # "process_method": "rough_only", 
    # "has_camel_results": False,
    # "fallback_reason": "camel_refinement_failed"
```

---

### 🚀 **完整示例代码**

```python
# example_usage.py
from divider import Divider
import json

def main():
    # 1. 初始化
    divider = Divider()
    
    # 2. 加载 LaTeX
    with open("document.tex", "r", encoding="utf-8") as f:
        latex_content = f.read()
    
    # 3. 设置指令
    instructions = {
        "max_section_depth": 3,
        "max_sections": 10,
        "use_camel_refinement": True,  # 启用 CAMEL
        "refine_threshold": 400
    }
    
    # 4. 执行分割
    nodes, feedback = divider.divide(latex_content, instructions)
    
    # 5. 检查结果
    if feedback["status"] == "warning":
        print(f"⚠️  使用了回退策略: {feedback.get('fallback_reason')}")
    
    print(f"✅ 生成 {len(nodes)} 个节点")
    print(f"📊 处理方法: {feedback['process_method']}")
    
    # 6. 保存结果
    result = {
        "nodes": [node.to_dict(include_content=False) for node in nodes],
        "feedback": feedback
    }
    
    with open("result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
```
