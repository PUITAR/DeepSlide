# chapter_node.py
"""
ChapterNode类 - 表示章节节点的数据结构

简化版：仅保留ID、标题(摘要)、类型、内容、子节点列表。
设计为不可变对象以确保数据一致性，但允许通过方法添加关系。
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Set
from enum import Enum
import uuid


class NodeType(Enum):
    """节点类型枚举"""
    SECTION = "section"          # 章节
    SUBSECTION = "subsection"    # 子章节
    CONTENT = "content"          # 内容页
    CUSTOM = "custom"            # 自定义类型 (包含公式、图片、表格、定理等)


@dataclass
class ChapterNode:
    """章节节点类 - 表示PPT中的一个章节或幻灯片节点
    
    Attributes:
        node_id: 唯一标识符
        title: 章节标题 (作为摘要)
        content: 原始LaTeX内容或纯文本内容
        node_type: 节点类型
        children_ids: 子节点ID列表
        level: 层级（辅助构建树，非必须输出，但为了逻辑保留）
        parent_id: 父节点ID (辅助构建树)
    """

    # 1. 节点ID
    node_id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    
    # 标题
    title: str = ""
    
    # 2. 节点内容概要 (LLM生成)
    summary: str = ""
    
    # 4. 节点文本 (纯文本保存)
    content: str = ""
    
    # 3. 节点类型
    node_type: NodeType = NodeType.SECTION
    
    # 5. 子节点列表 (存储ID，输出时解析为对象)
    children_ids: List[str] = field(default_factory=list)
    
    # 辅助字段 (用于构建树结构)
    level: int = 1
    parent_id: Optional[str] = None
    
    # 兼容性字段 (保留 metadata 以防万一，但输出时会忽略)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 6. 是否使用
    used: bool = True

    def add_child(self, child_node: ChapterNode) -> None:
        """添加子节点"""
        if child_node.node_id not in self.children_ids:
            self.children_ids.append(child_node.node_id)
            child_node.parent_id = self.node_id

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        """转换为字典格式 (精简版)"""
        # Ensure node_type is a string
        node_type_val = self.node_type.value if hasattr(self.node_type, 'value') else str(self.node_type)
        
        data = {
            "node_id": self.node_id,
            "summary": self.summary if self.summary else self.title,  # Use generated summary if available
            "title": self.title, # Keep title for reference
            "node_type": node_type_val,
            "children": [], # Placeholder, filled by external recursive function
            "level": self.level, # Optional: helpful for debugging
            "used": self.used
        }

        if include_content:
            data["content"] = self.content

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChapterNode:
        """从字典创建ChapterNode实例"""
        # 处理枚举字段
        if "node_type" in data:
            try:
                data["node_type"] = NodeType(data["node_type"])
            except ValueError:
                # Fallback or keep as string if not in enum (though type hint says NodeType)
                pass

        # Handle 'summary' mapping back to 'title' if needed
        if "summary" in data and "title" not in data:
            data["title"] = data["summary"]
            
        # Filter out unknown fields to avoid TypeError
        valid_fields = {f.name for f in field(cls)}
        
        filtered_data = {k: v for k, v in data.items() if k in cls.__annotations__}
        
        return cls(**filtered_data)

    def __str__(self) -> str:
        return f"ChapterNode(id={self.node_id}, summary={self.title[:30]!r}, type={self.node_type.value})"
