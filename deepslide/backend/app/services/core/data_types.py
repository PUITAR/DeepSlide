from pydantic import BaseModel, Field
from typing import List, Optional

class LogicNode(BaseModel):
    name: str = Field(description="Name of the slide topic")
    description: str = Field(description="Detailed description of what this slide covers")
    duration: str = Field(description="Estimated duration (e.g., '1 min', '30 sec')")
    keywords: List[str] = Field(default_factory=list)

class LogicEdge(BaseModel):
    from_: int = Field(alias="from")
    to: int
    type: str
    description: Optional[str] = None

class LogicFlow(BaseModel):
    nodes: List[LogicNode]
    edges: List[LogicEdge]
