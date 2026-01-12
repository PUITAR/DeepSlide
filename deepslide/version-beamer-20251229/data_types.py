from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from chapter_node import ChapterNode

class LogicNode(BaseModel):
    name: str = Field(..., description="Name of the logic node")
    description: str = Field(..., description="Main description of the logic node")
    duration: str = Field("1 min", description="Estimated duration for this part")
    # Content Tree for this logic node (Filtered view of the document)
    # Storing roots of the filtered tree (nodes with used=True)
    content_tree_roots: List[ChapterNode] = Field(default_factory=list, description="Filtered content tree roots for this logic node")
    # Node map for the filtered copy to allow traversal
    content_tree_map: Dict[str, ChapterNode] = Field(default_factory=dict, description="Node map for the filtered content tree of this logic node")
    
class LogicFlow(BaseModel):
    nodes: List[LogicNode] = Field(..., description="Ordered list of logic nodes representing the flow")

    def to_string(self) -> str:
        """Convert logic flow to a readable string for LLM."""
        lines = []
        for i, node in enumerate(self.nodes):
            lines.append(f"{i+1}. {node.name}: {node.description} (Duration: {node.duration})")
        return "\n".join(lines)
