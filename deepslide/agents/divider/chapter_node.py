# chapter_node.py
"""
ChapterNode类 - 表示章节节点的数据结构

这个类用于表示PPT中的一个章节或幻灯片节点，包含内容、层级和关系信息。
设计为不可变对象以确保数据一致性，但允许通过方法添加关系。
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Set
from enum import Enum
import uuid
from datetime import datetime


class NodeType(Enum):
    """节点类型枚举"""
    SECTION = "section"          # 章节
    SUBSECTION = "subsection"    # 子章节
    SLIDE = "slide"              # 幻灯片
    TITLE = "title"              # 标题页
    AGENDA = "agenda"            # 议程页
    SUMMARY = "summary"          # 总结页
    CONTENT = "content"          # 内容页
    IMAGE = "image"              # 图片页
    CODE = "code"                # 代码页
    TABLE = "table"              # 表格页
    QUOTE = "quote"              # 引用页
    CUSTOM = "custom"            # 自定义类型


class RelationshipType(Enum):
    """关系类型枚举"""
    DEPENDENT = "dependent_on"          # 依赖关系：A依赖B
    SIMILAR = "similar_to"              # 相似关系：A与B相似
    CONTRAST = "contrasts_with"         # 对比关系：A与B对比
    SEQUENCE = "sequence_of"            # 序列关系：A在B之后
    EXAMPLE = "example_of"              # 示例关系：A是B的示例
    SUMMARY = "summary_of"              # 总结关系：A是B的总结
    DETAIL = "detail_of"                # 详细关系：A是B的详细说明


@dataclass
class PositionInfo:
    """位置信息 - 记录节点在原始文档中的位置"""
    start_line: int = 0          # 起始行号
    end_line: int = 0            # 结束行号
    start_char: int = 0          # 起始字符位置
    end_char: int = 0            # 结束字符位置
    page_number: Optional[int] = None  # PDF页码（如果有）
    source_file: Optional[str] = None  # 源文件路径

    def length(self) -> int:
        """计算内容长度"""
        return self.end_char - self.start_char

    def contains(self, other: PositionInfo) -> bool:
        """检查是否包含另一个节点的位置（需同源文件）"""
        if self.source_file != other.source_file:
            return False
        return (self.start_char <= other.start_char and
                self.end_char >= other.end_char)


@dataclass
class ContentMetrics:
    """内容度量指标"""
    word_count: int = 0                  # 单词数
    char_count: int = 0                  # 字符数
    sentence_count: int = 0              # 句子数
    paragraph_count: int = 0             # 段落数
    formula_count: int = 0               # 公式数
    image_count: int = 0                 # 图片数
    table_count: int = 0                 # 表格数
    code_block_count: int = 0            # 代码块数
    readability_score: Optional[float] = None  # 可读性评分
    complexity_score: Optional[float] = None   # 复杂度评分

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


@dataclass
class ChapterNode:
    """章节节点类 - 表示PPT中的一个章节或幻灯片节点

    Attributes:
        node_id: 唯一标识符
        title: 章节标题
        content: 原始LaTeX内容或纯文本内容
        level: 层级（1-顶级章节，2-子章节等）
        node_type: 节点类型
        parent_id: 父节点ID
        children_ids: 子节点ID列表
        position: 在原始文档中的位置信息
        metrics: 内容度量指标
        metadata: 扩展元数据
        created_at: 创建时间
        updated_at: 更新时间
        relationships: 与其他节点的关系
        importance: 重要性评分（0-1）
        tags: 标签列表
    """

    # 基本属性
    node_id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    title: str = ""
    content: str = ""
    level: int = 1
    node_type: NodeType = NodeType.SECTION

    # 树结构关系
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)

    # 位置信息
    position: PositionInfo = field(default_factory=PositionInfo)

    # 内容度量
    metrics: ContentMetrics = field(default_factory=ContentMetrics)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # 语义关系（存储关系类型和目标节点ID）
    relationships: Dict[RelationshipType, Set[str]] = field(
        default_factory=lambda: {rt: set() for rt in RelationshipType}
    )

    # 重要性评分和标签
    importance: float = 0.5  # 默认中等重要性
    tags: Set[str] = field(default_factory=set)

    def __post_init__(self):
        """初始化后处理"""
        # 确保 importance 在 [0.0, 1.0] 范围内
        if not (0.0 <= self.importance <= 1.0):
            raise ValueError("importance must be between 0.0 and 1.0")

        # 防御性补全 relationships（应对未来 enum 扩展或反序列化不全）
        for rt in RelationshipType:
            if rt not in self.relationships:
                self.relationships[rt] = set()

    def add_child(self, child_node: ChapterNode) -> None:
        """添加子节点 - 安全修正版"""
        # 检查子节点ID是否已存在，避免重复添加
        if child_node.node_id not in self.children_ids:
            self.children_ids.append(child_node.node_id)
            child_node.parent_id = self.node_id  # 设置子节点的父ID
            self.updated_at = datetime.now()
    
    def remove_child(self, child_id: str) -> bool:
        """移除子节点"""
        if child_id in self.children_ids:
            self.children_ids.remove(child_id)
            # 注意：这里不重置 child.parent_id，因为可能有其他引用
            self.updated_at = datetime.now()
            return True
        return False

    def add_relationship(self,
                         relation_type: RelationshipType,
                         target_node_id: str) -> None:
        """添加关系（不能指向自己）"""
        if target_node_id != self.node_id:
            self.relationships[relation_type].add(target_node_id)
            self.updated_at = datetime.now()

    def remove_relationship(self,
                            relation_type: RelationshipType,
                            target_node_id: str) -> bool:
        """移除关系"""
        if target_node_id in self.relationships[relation_type]:
            self.relationships[relation_type].remove(target_node_id)
            self.updated_at = datetime.now()
            return True
        return False

    def has_relationship(self,
                         relation_type: RelationshipType,
                         target_node_id: str) -> bool:
        """检查是否存在特定关系"""
        return target_node_id in self.relationships[relation_type]

    def get_all_relationships(self) -> Dict[RelationshipType, List[str]]:
        """获取所有非空关系（返回列表形式）"""
        return {rt: list(nodes) for rt, nodes in self.relationships.items()
                if nodes}

    def add_tag(self, tag: str) -> None:
        """添加标签（转为小写）"""
        self.tags.add(tag.lower())
        self.updated_at = datetime.now()

    def remove_tag(self, tag: str) -> bool:
        """移除标签"""
        tag_lower = tag.lower()
        if tag_lower in self.tags:
            self.tags.remove(tag_lower)
            self.updated_at = datetime.now()
            return True
        return False

    def has_tag(self, tag: str) -> bool:
        """检查是否包含标签"""
        return tag.lower() in self.tags

    def update_metrics(self,
                       word_count: Optional[int] = None,
                       char_count: Optional[int] = None,
                       **kwargs) -> None:
        """更新度量指标"""
        if word_count is not None:
            self.metrics.word_count = word_count
        if char_count is not None:
            self.metrics.char_count = char_count

        for key, value in kwargs.items():
            if hasattr(self.metrics, key):
                setattr(self.metrics, key, value)

        self.updated_at = datetime.now()

    def to_dict(self, include_content: bool = True) -> Dict[str, Any]:
        """转换为字典格式（便于JSON序列化）

        Args:
            include_content: 是否包含content字段（可能很大）
        """
        data = {
            "node_id": self.node_id,
            "title": self.title,
            "level": self.level,
            "node_type": self.node_type.value,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "position": asdict(self.position),
            "metrics": self.metrics.to_dict(),
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "relationships": {
                rt.value: list(nodes)
                for rt, nodes in self.relationships.items()
                if nodes
            },
            "importance": self.importance,
            "tags": list(self.tags)
        }

        if include_content:
            data["content"] = self.content

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChapterNode:
        """从字典创建ChapterNode实例"""
        # 处理枚举字段
        if "node_type" in data:
            data["node_type"] = NodeType(data["node_type"])

        # 处理嵌套 dataclass
        if "position" in data:
            data["position"] = PositionInfo(**data["position"])
        if "metrics" in data:
            data["metrics"] = ContentMetrics(**data["metrics"])

        # 处理 relationships：确保所有 RelationshipType 都存在
        full_relationships = {rt: set() for rt in RelationshipType}
        if "relationships" in data:
            rel_data = data.pop("relationships")
            for rt_str, node_list in rel_data.items():
                try:
                    rt = RelationshipType(rt_str)
                    full_relationships[rt] = set(node_list)
                except ValueError:
                    # 忽略未知的关系类型（向后兼容）
                    continue
        data["relationships"] = full_relationships

        # 处理时间字段
        for time_key in ("created_at", "updated_at"):
            if time_key in data and isinstance(data[time_key], str):
                data[time_key] = datetime.fromisoformat(data[time_key])

        # 处理 tags
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = set(data["tags"])

        return cls(**data)

    def is_leaf(self) -> bool:
        """检查是否为叶节点（无子节点）"""
        return len(self.children_ids) == 0

    def get_depth(self, node_map: Dict[str, ChapterNode]) -> int:
        """计算节点深度（从根节点开始）"""
        if not self.parent_id:
            return 0
        if self.parent_id in node_map:
            parent = node_map[self.parent_id]
            return parent.get_depth(node_map) + 1
        return 1  # 父节点不在 map 中，默认深度为 1

    def __str__(self) -> str:
        """简洁字符串表示（截断长标题）"""
        title_display = self.title if len(self.title) <= 50 else self.title[:47] + "..."
        return f"ChapterNode(id={self.node_id}, title={title_display!r}, level={self.level}, type={self.node_type.value})"

    def __repr__(self) -> str:
        """详细表示"""
        return f"ChapterNode(node_id={self.node_id!r}, title={self.title!r}, level={self.level}, node_type={self.node_type}, children={len(self.children_ids)})"


# 辅助函数
def create_chapter_hierarchy(nodes: List[ChapterNode]) -> Dict[str, ChapterNode]:
    """从节点列表构建层次结构映射"""
    node_map = {node.node_id: node for node in nodes}
    for node in nodes:
        if node.parent_id and node.parent_id in node_map:
            parent = node_map[node.parent_id]
            parent.add_child(node)
    return node_map


def find_root_nodes(nodes: List[ChapterNode]) -> List[ChapterNode]:
    """查找根节点（没有父节点的节点）"""
    return [node for node in nodes if not node.parent_id]


def traverse_preorder(root: ChapterNode,
                      node_map: Dict[str, ChapterNode]) -> List[ChapterNode]:
    """前序遍历章节树"""
    result = [root]
    for child_id in root.children_ids:
        if child_id in node_map:
            child = node_map[child_id]
            result.extend(traverse_preorder(child, node_map))
    return result


# 测试代码
if __name__ == "__main__":
    # 创建示例节点
    root = ChapterNode(
        node_id="root_1",
        title="Introduction to Machine Learning",
        content="This is an introduction to machine learning...",
        level=1,
        node_type=NodeType.SECTION,
        importance=0.8
    )

    child1 = ChapterNode(
        title="Supervised Learning",
        content="Supervised learning algorithms...",
        level=2
    )

    child2 = ChapterNode(
        title="Unsupervised Learning",
        content="Unsupervised learning approaches...",
        level=2
    )

    # 添加子节点
    root.add_child(child1)
    root.add_child(child2)

    # 添加关系
    root.add_relationship(RelationshipType.SEQUENCE, child1.node_id)
    child1.add_relationship(RelationshipType.SEQUENCE, child2.node_id)

    # 添加标签
    root.add_tag("ml")
    root.add_tag("introduction")

    # 更新度量
    root.update_metrics(word_count=150, char_count=800)

    # 测试序列化
    root_dict = root.to_dict()
    print(f"Root node dict keys: {list(root_dict.keys())}")

    # 测试反序列化
    root_copy = ChapterNode.from_dict(root_dict)
    print(f"Root copy: {root_copy}")

    # 测试辅助函数
    nodes = [root, child1, child2]
    node_map = create_chapter_hierarchy(nodes)
    print(f"Total nodes: {len(node_map)}")

    roots = find_root_nodes(nodes)
    print(f"Root nodes: {[r.title for r in roots]}")