# refine_agent.py
"""
CAMEL 微调代理 - 语义分割与关系构建
职责：对粗分节点进行语义分割，添加重要性/标签，构建节点间语义关系
核心原则：不修改原始内容，只添加元数据和关系
"""

from typing import List, Dict, Any, Tuple, Optional, Set
import logging
import re
import json
import math
from datetime import datetime
from enum import Enum
from dataclasses import asdict

from chapter_node import ChapterNode, NodeType, RelationshipType, PositionInfo
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent

logger = logging.getLogger(__name__)

class RelationSourceType(Enum):
    """关系来源类型"""
    AUTOMATIC = "automatic"      # 自动规则（SEQUENCE）
    KEYWORD = "keyword"          # 关键词模式匹配
    CAMEL = "camel"              # CAMEL 语义分析
    NONE = "none"                # 无关系

class RefineAgent:
    """CAMEL 微调代理 - 语义分割与关系构建"""
    
    def __init__(self, camel_config: Dict[str, Any]):
        """
        初始化 CAMEL 微调代理
        
        Args:
            camel_config: CAMEL 配置字典，包含:
                - model_type: 模型类型 (如 "deepseek-chat")
                - api_key: API 密钥
                - base_url: 基础 URL (可选)
        """
        self.camel_config = camel_config
        self.model = None
        self._init_camel_model()
        
        # 预定义的关系模式（学术文本优化）
        self.relationship_patterns = {
            RelationshipType.DEPENDENT: [
                r"(?:方法|approach|technique|algorithm).*?(?:实验|experiment|evaluation|result)",
                r"(?:数据|data|dataset).*?(?:分析|analysis|processing|feature)",
                r"(?:模型|model|framework).*?(?:训练|training|optimization|parameter)"
            ],
            RelationshipType.SIMILAR: [
                r"^(?:同样|similarly|also|furthermore|additionally).{0,15}(?:方法|method|result|experiment)",
                r"(?:如上所述|as discussed|in section).*?(?:同样适用于|also applies to)",
                r"^(?:与|compared with|versus).{0,20}(?:相似|similar|identical)"
            ],
            RelationshipType.CONTRAST: [
                r"(?:但是|however|but|相反|contrast|differ|unlike|whereas|although|though)",
                r"(?:不同于|differs from|in contrast to|on the other hand)",
                r"(?:局限性|limitation|weakness|problem|challenge).{0,20}(?:然而|however)"
            ],
            RelationshipType.EXAMPLE: [
                r"(?:例如|for example|e\.g\.|such as|including|specifically)",
                r"(?:案例|case study|instance|scenario).*?(?:展示|demonstrate|illustrate)"
            ]
        }
        
        logger.info(f"初始化 RefineAgent (语义分割+关系构建) - 模型: {camel_config.get('model_type', 'unknown')}")
    
    def _init_camel_model(self):
        """初始化 CAMEL 模型"""
        try:
            api_key = self.camel_config.get("api_key")
            model_type = self.camel_config.get("model_type", "deepseek-chat")
            base_url = self.camel_config.get("base_url")
            
            if not api_key:
                raise ValueError("CAMEL API 密钥未配置")
            
            # 创建模型 (支持自定义 base_url)
            model_kwargs = {
                "model_platform": ModelPlatformType.OPENAI,
                "model_type": model_type,
                "api_key": api_key
            }
            if base_url:
                model_kwargs["base_url"] = base_url
            
            self.model = ModelFactory.create(**model_kwargs)
            logger.info(f"CAMEL 模型初始化成功: {model_type}")
            
        except Exception as e:
            logger.error(f"CAMEL 模型初始化失败: {str(e)}")
            # 不抛出异常，后续使用回退策略
            self.model = None
    
    def refine(
        self,
        rough_nodes: List[ChapterNode],
        planner_instructions: Dict[str, Any]
    ) -> Tuple[List[ChapterNode], Dict[str, Any]]:
        """
        对粗分节点进行语义细化
        
        Args:
            rough_nodes: 粗分后的 ChapterNode 列表
            planner_instructions: Planner 指令
                
        Returns:
            (细化后的节点列表, 反馈信息)
        """
        logger.info(f"开始细化 {len(rough_nodes)} 个粗分节点")
        logger.debug(f"Planner 指令: {json.dumps(planner_instructions, indent=2)}")
        
        refined_nodes = []
        refinement_stats = {
            "total_rough_nodes": len(rough_nodes),
            "refined_nodes": 0,
            "segments_created": 0,
            "relationships_built": 0,
            "camel_relation_calls": 0,
            "errors": 0
        }
        
        # 限制 CAMEL 关系调用总数
        max_camel_calls = planner_instructions.get("max_camel_relation_calls", 10)
        camel_call_count = 0
        
        for i, rough_node in enumerate(rough_nodes):
            try:
                # 检查是否需要细化
                should_refine = self._should_refine_node(rough_node, planner_instructions)
                
                if should_refine:
                    # 细化单个节点
                    refined_segments, segment_stats = self._refine_single_node(
                        rough_node, 
                        planner_instructions,
                        max_camel_calls - camel_call_count
                    )
                    
                    # 更新统计
                    refinement_stats["refined_nodes"] += 1
                    refinement_stats["segments_created"] += len(refined_segments)
                    refinement_stats["relationships_built"] += segment_stats["relationships"]
                    camel_call_count += segment_stats["camel_calls"]
                    refinement_stats["camel_relation_calls"] = camel_call_count
                    
                    # 添加到结果
                    refined_nodes.extend(refined_segments)
                    
                    logger.debug(f"细化节点 '{rough_node.title}': 创建 {len(refined_segments)} 个片段")
                else:
                    # 无细化需求，直接使用原节点
                    refined_nodes.append(rough_node)
                    logger.debug(f"跳过细化: '{rough_node.title}' (长度: {len(rough_node.content)})"
                                f", 重要性: {rough_node.importance:.2f}")
            
            except Exception as e:
                logger.warning(f"细化节点 '{rough_node.title}' 失败: {str(e)}", exc_info=True)
                # 回退到原节点
                refined_nodes.append(rough_node)
                refinement_stats["errors"] += 1
        
        # 构建跨节点自动关系 (SEQUENCE)
        self._build_automatic_relations(refined_nodes, planner_instructions)
        refinement_stats["relationships_built"] += len([
            rel for node in refined_nodes 
            for rel in node.get_all_relationships().values() 
            for _ in rel
        ])
        
        feedback = self._generate_refinement_feedback(refinement_stats, planner_instructions)
        logger.info(f"细化完成: {refinement_stats['refined_nodes']} 个节点被细化, "
                   f"创建 {refinement_stats['segments_created']} 个片段, "
                   f"建立 {refinement_stats['relationships_built']} 个关系")
        
        return refined_nodes, feedback
    
    def _should_refine_node(self, node: ChapterNode, instructions: Dict[str, Any]) -> bool:
        """判断节点是否需要细化"""
        # 1. 内容长度超过阈值
        refine_threshold = instructions.get("refine_threshold", 800)
        if len(node.content) > refine_threshold:
            return True
        
        # 2. 节点被标记为需要细化
        if "需要细化" in node.tags or "长章节" in node.tags:
            return True
        
        # 3. 重点章节（即使较短也细化）
        focus_keywords = instructions.get("focus_keywords", [])
        title_lower = node.title.lower()
        if any(kw in title_lower for kw in focus_keywords):
            return True
        
        # 4. Planner 显式要求细化
        if instructions.get("force_refine", False):
            return True
        
        return False
    
    def _refine_single_node(
        self,
        rough_node: ChapterNode,
        instructions: Dict[str, Any],
        remaining_camel_calls: int
    ) -> Tuple[List[ChapterNode], Dict[str, int]]:
        """
        细化单个粗分节点
        
        Returns:
            (细化后的片段列表, 本次细化的统计)
        """
        # 1. 语义分割：获取分割点
        segments_info, segmentation_method = self._semantic_segmentation(
            rough_node, instructions
        )
        
        # 2. 创建片段节点
        segment_nodes = self._create_segment_nodes(
            rough_node, segments_info, instructions
        )
        
        # 3. 构建片段间关系
        relationships_built = 0
        
        # 3.1 自动关系 (SEQUENCE)
        self._build_automatic_relations(segment_nodes, instructions)
        relationships_built += len(segment_nodes) - 1  # N-1 个 SEQUENCE 关系
        
        # 3.2 关键词驱动关系
        keyword_relations = self._build_keyword_relations(
            segment_nodes, rough_node
        )
        relationships_built += keyword_relations
        
        # 3.3 CAMEL 语义关系（默认开启，但限制调用次数）
        camel_relations = 0
        camel_calls_used = 0
        
        if instructions.get("build_semantic_relations", True) and remaining_camel_calls > 0:
            camel_relations, camel_calls_used = self._build_camel_relations(
                segment_nodes, 
                rough_node,
                instructions,
                min(remaining_camel_calls, instructions.get("max_camel_calls_per_node", 3))
            )
            relationships_built += camel_relations
        
        # 4. 返回结果
        stats = {
            "relationships": relationships_built,
            "camel_calls": camel_calls_used,
            "segmentation_method": segmentation_method
        }
        
        return segment_nodes, stats
    
    def _semantic_segmentation(
        self,
        rough_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        语义分割：将粗分节点分割为多个片段
        
        Returns:
            (片段信息列表, 分割方法)
        """
        # 1. 尝试 CAMEL 语义分割
        if self.model and instructions.get("use_camel_segmentation", True):
            try:
                return self._camel_segmentation(rough_node, instructions), "camel"
            except Exception as e:
                logger.warning(f"CAMEL 分割失败: {str(e)}，回退到规则分割")
        
        # 2. 回退到规则分割
        return self._rule_based_segmentation(rough_node, instructions), "rule"
    
    def _camel_segmentation(
        self,
        rough_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """使用 CAMEL 进行语义分割"""
        # 构建提示词
        prompt = self._build_camel_segmentation_prompt(rough_node, instructions)
        
        # 调用 CAMEL
        response = self._call_camel(prompt, "semantic_segmentation")
        
        # 解析响应
        segments_info = self._parse_camel_segmentation_response(
            response, rough_node, instructions
        )
        
        return segments_info
    
    def _build_camel_segmentation_prompt(
        self,
        rough_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> str:
        """构建 CAMEL 语义分割提示词"""
        target_language = instructions.get("target_language", "zh")
        min_segment_length = instructions.get("min_segment_length", 150)
        max_segments = instructions.get("max_segments_per_node", 5)
        
        language_instruction = "使用中文回答" if target_language == "zh" else f"使用{target_language}回答"
        
        return (
            f"你是一名学术文本分析专家。请将以下 LaTeX 内容按语义分割为 {max_segments} 个片段:\n\n"
            f"内容:\n{rough_node.content[:4000]}\n\n"  # 限制长度
            f"要求:\n"
            f"1. 每个片段长度 >= {min_segment_length} 字符\n"
            f"2. 保持 LaTeX 公式和命令完整（不要修改原始内容）\n"
            f"3. 为每个片段分配重要性 (0.0-1.0) 和 1-3 个标签\n"
            f"4. {language_instruction}\n\n"
            f"返回严格 JSON 格式:\n"
            f"{{\n"
            f'  "segments": [\n'
            f'    {{\n'
            f'      "start_char": 0,\n'
            f'      "end_char": 500,\n'
            f'      "importance": 0.8,\n'
            f'      "tags": ["方法", "公式"]\n'
            f'    }}\n'
            f'  ]\n'
            f"}}"
        )
    
    def _parse_camel_segmentation_response(
        self,
        response: str,
        rough_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """解析 CAMEL 语义分割响应"""
        try:
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                raise ValueError("未找到有效 JSON")
            
            data = json.loads(json_match.group(0))
            segments = data.get("segments", [])
            
            # 验证和清理
            valid_segments = []
            content_length = len(rough_node.content)
            min_length = instructions.get("min_segment_length", 150)
            
            for seg in segments:
                start = int(seg.get("start_char", 0))
                end = int(seg.get("end_char", 0))
                importance = float(seg.get("importance", 0.5))
                tags = seg.get("tags", [])
                
                # 验证位置
                if start < 0 or end > content_length or end <= start:
                    continue
                
                # 验证长度
                if end - start < min_length:
                    continue
                
                # 验证重要性
                importance = max(0.0, min(1.0, importance))
                
                valid_segments.append({
                    "start_char": start,
                    "end_char": end,
                    "importance": importance,
                    "tags": [str(tag).strip() for tag in tags if tag],
                    "summary": f"片段 {len(valid_segments)+1}"  # 简化摘要
                })
            
            # 必须有至少一个有效片段
            if not valid_segments:
                raise ValueError("无有效片段")
            
            # 按位置排序
            valid_segments.sort(key=lambda x: x["start_char"])
            return valid_segments
            
        except Exception as e:
            logger.warning(f"解析 CAMEL 响应失败: {str(e)}")
            # 回退到规则分割
            return self._rule_based_segmentation(rough_node, instructions)
    
    def _rule_based_segmentation(
        self,
        rough_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """基于规则的语义分割"""
        content = rough_node.content
        min_length = instructions.get("min_segment_length", 150)
        max_segments = instructions.get("max_segments_per_node", 5)
        
        # 1. 按段落分割
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content) if p.strip()]
        
        # 2. 合并短段落
        merged_paragraphs = []
        current = ""
        
        for para in paragraphs:
            if len(current) + len(para) < min_length:
                current = (current + "\n\n" + para) if current else para
            else:
                if current:
                    merged_paragraphs.append(current)
                current = para
        
        if current:
            merged_paragraphs.append(current)
        
        # 3. 限制最大段落数
        if len(merged_paragraphs) > max_segments:
            merged_paragraphs = merged_paragraphs[:max_segments]
        
        # 4. 构建片段信息
        segments_info = []
        current_pos = 0
        
        for i, para in enumerate(merged_paragraphs):
            start_char = current_pos
            end_char = current_pos + len(para)
            
            # 估算重要性（基于位置和长度）
            position_weight = 1.0 if i == 0 else 0.8 if i == len(merged_paragraphs) - 1 else 0.6
            length_weight = min(1.0, len(para) / 1000)
            importance = min(0.9, 0.5 + position_weight * length_weight * 0.4)
            
            # 生成标签
            tags = self._generate_rule_based_tags(para, rough_node)
            
            segments_info.append({
                "start_char": start_char,
                "end_char": end_char,
                "importance": importance,
                "tags": tags,
                "summary": f"{rough_node.title} - 片段 {i+1}"
            })
            
            current_pos = end_char + 2  # +2 for \n\n
        
        # 5. 确保至少一个片段
        if not segments_info:
            segments_info.append({
                "start_char": 0,
                "end_char": len(content),
                "importance": 0.7,
                "tags": ["内容"],
                "summary": rough_node.title
            })
        
        return segments_info
    
    def _generate_rule_based_tags(
        self,
        content: str,
        rough_node: ChapterNode
    ) -> List[str]:
        """基于规则生成标签"""
        content_lower = content.lower()
        title_lower = rough_node.title.lower()
        
        # 预定义标签模式
        tag_patterns = {
            "方法": ["method", "algorithm", "approach", "technique", "模型", "框架"],
            "实验": ["experiment", "setup", "dataset", "result", "accuracy", "实验", "数据"],
            "理论": ["theorem", "proof", "lemma", "理论", "证明", "公式", "方程"],
            "讨论": ["discussion", "analysis", "interpretation", "讨论", "分析", "局限性"],
            "结论": ["conclusion", "summary", "future work", "结论", "总结", "展望"]
        }
        
        tags = []
        # 检查标题
        for tag, patterns in tag_patterns.items():
            if any(p in title_lower for p in patterns):
                tags.append(tag)
                break
        
        # 检查内容
        if not tags:
            for tag, patterns in tag_patterns.items():
                if any(p in content_lower for p in patterns):
                    tags.append(tag)
                    break
        
        # 默认标签
        if not tags:
            tags = ["内容"]
        
        return tags
    
    def _create_segment_nodes(
        self,
        rough_node: ChapterNode,
        segments_info: List[Dict[str, Any]],
        instructions: Dict[str, Any]
    ) -> List[ChapterNode]:
        """创建片段节点"""
        segment_nodes = []
        now = datetime.now()
        
        for i, seg_info in enumerate(segments_info):
            # 提取内容片段
            content = rough_node.content[seg_info["start_char"]:seg_info["end_char"]]
            
            # 创建新节点
            segment_node = ChapterNode(
                node_id=f"{rough_node.node_id}_seg{i}",
                title=f"{rough_node.title} - {seg_info.get('summary', f'片段{i+1}')}",
                content=content,
                level=rough_node.level + 1,  # 比父节点深一级
                node_type=NodeType.CONTENT,
                parent_id=rough_node.node_id,
                position=PositionInfo(
                    start_char=rough_node.position.start_char + seg_info["start_char"],
                    end_char=rough_node.position.start_char + seg_info["end_char"],
                    source_file=rough_node.position.source_file
                ),
                metadata={
                    "source_node_id": rough_node.node_id,
                    "segment_index": i,
                    "segmentation_method": instructions.get("segmentation_method", "rule"),
                    "original_content_range": [seg_info["start_char"], seg_info["end_char"]]
                }
            )
            
            # 设置重要性和标签
            segment_node.importance = seg_info["importance"]
            for tag in seg_info["tags"]:
                segment_node.add_tag(tag)
            
            # 更新度量指标
            segment_node.update_metrics(
                char_count=len(content),
                word_count=len(content.split()),
                sentence_count=len(re.split(r'[.!?。！？]', content))
            )
            
            # 继承部分元数据
            if "latex_command" in rough_node.metadata:
                segment_node.metadata["latex_command"] = rough_node.metadata["latex_command"]
            
            # 标记为已细化
            segment_node.add_tag("细化")
            
            segment_nodes.append(segment_node)
        
        return segment_nodes
    
    def _build_automatic_relations(
        self,
        nodes: List[ChapterNode],
        instructions: Dict[str, Any]
    ):
        """构建自动关系 (SEQUENCE)"""
        if not instructions.get("build_automatic_relations", True):
            return
        
        # 按位置排序
        nodes.sort(key=lambda x: x.position.start_char)
        
        # 构建 SEQUENCE 关系
        for i in range(len(nodes) - 1):
            nodes[i].add_relationship(RelationshipType.SEQUENCE, nodes[i+1].node_id)
    
    def _build_keyword_relations(
        self,
        nodes: List[ChapterNode],
        parent_node: ChapterNode
    ) -> int:
        """构建关键词驱动关系"""
        relationships_built = 0
        
        # 检查所有节点对
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                node1 = nodes[i]
                node2 = nodes[j]
                
                # 构建关系
                rel_type = self._detect_relationship_by_keywords(node1, node2, parent_node)
                if rel_type:
                    node1.add_relationship(rel_type, node2.node_id)
                    # 记录关系来源
                    if "relationship_sources" not in node1.metadata:
                        node1.metadata["relationship_sources"] = {}
                    node1.metadata["relationship_sources"][node2.node_id] = RelationSourceType.KEYWORD.value
                    relationships_built += 1
        
        return relationships_built
    
    def _detect_relationship_by_keywords(
        self,
        node1: ChapterNode,
        node2: ChapterNode,
        parent_node: ChapterNode
    ) -> Optional[RelationshipType]:
        """通过关键词检测关系"""
        combined_content = (node1.content + " " + node2.content).lower()
        
        # 检查每种关系类型
        for rel_type, patterns in self.relationship_patterns.items():
            for pattern in patterns:
                if re.search(pattern, combined_content, re.IGNORECASE):
                    logger.debug(f"检测到关系 {rel_type.value} between '{node1.title}' and '{node2.title}': 匹配 '{pattern}'")
                    return rel_type
        
        return None
    
    def _build_camel_relations(
        self,
        nodes: List[ChapterNode],
        parent_node: ChapterNode,
        instructions: Dict[str, Any],
        max_calls: int
    ) -> Tuple[int, int]:
        """
        构建 CAMEL 语义关系
        
        Returns:
            (成功构建的关系数, 实际使用的 CAMEL 调用次数)
        """
        if not self.model or max_calls <= 0:
            return 0, 0
        
        relationships_built = 0
        calls_used = 0
        
        # 仅检查相邻节点（减少调用次数）
        for i in range(len(nodes) - 1):
            if calls_used >= max_calls:
                break
                
            node1 = nodes[i]
            node2 = nodes[i+1]
            
            # 跳过已有关系的节点
            if node1.has_relationship(RelationshipType.SIMILAR, node2.node_id) or \
               node1.has_relationship(RelationshipType.DEPENDENT, node2.node_id):
                continue
            
            # 调用 CAMEL
            rel_type, confidence = self._call_camel_for_relationship(
                node1, node2, parent_node, instructions
            )
            calls_used += 1
            
            # 验证置信度
            confidence_threshold = instructions.get("semantic_relation_threshold", 0.7)
            if rel_type and confidence >= confidence_threshold:
                node1.add_relationship(rel_type, node2.node_id)
                # 记录关系来源
                if "relationship_sources" not in node1.metadata:
                    node1.metadata["relationship_sources"] = {}
                node1.metadata["relationship_sources"][node2.node_id] = RelationSourceType.CAMEL.value
                relationships_built += 1
                logger.debug(f"CAMEL 关系: '{node1.title}' -> '{node2.title}' = {rel_type.value} (置信度: {confidence:.2f})")
            
            # 暂停防止速率限制
            if calls_used < max_calls:
                import time
                time.sleep(0.1)
        
        return relationships_built, calls_used
    
    def _call_camel_for_relationship(
        self,
        node1: ChapterNode,
        node2: ChapterNode,
        parent_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> Tuple[Optional[RelationshipType], float]:
        """调用 CAMEL 构建关系"""
        # 构建提示词
        prompt = self._build_camel_relationship_prompt(node1, node2, parent_node, instructions)
        
        # 调用 CAMEL
        response = self._call_camel(prompt, "semantic_relationship")
        
        # 解析响应
        return self._parse_camel_relationship_response(response, instructions)
    
    def _build_camel_relationship_prompt(
        self,
        node1: ChapterNode,
        node2: ChapterNode,
        parent_node: ChapterNode,
        instructions: Dict[str, Any]
    ) -> str:
        """构建 CAMEL 关系提示词"""
        # 限制内容长度
        max_preview = 300
        content1 = node1.content[:max_preview] + ("..." if len(node1.content) > max_preview else "")
        content2 = node2.content[:max_preview] + ("..." if len(node2.content) > max_preview else "")
        
        # 允许的关系类型
        allowed_types = instructions.get("allowed_relationship_types", [
            "DEPENDENT", "SIMILAR", "CONTRAST", "EXAMPLE"
        ])
        allowed_types_str = ", ".join(allowed_types)
        
        return (
            "你是一名学术关系提取专家。请分析以下两个相邻章节片段的语义关系:\n\n"
            f"片段1 (ID: {node1.node_id}):\n{content1}\n\n"
            f"片段2 (ID: {node2.node_id}):\n{content2}\n\n"
            f"可用关系类型（必须精确匹配）:\n"
            f"- DEPENDENT: 片段2 依赖 片段1 的内容\n"
            f"- SIMILAR: 两片段讨论高度相似主题\n"
            f"- CONTRAST: 两片段呈现对比或矛盾观点\n"
            f"- EXAMPLE: 片段2 是 片段1 的示例\n"
            f"- NONE: 无显著关系\n\n"
            f"要求:\n"
            f"1. 只返回最强的一个关系\n"
            f"2. 置信度 0-1（低于 0.7 时返回 NONE）\n"
            f"3. 严格 JSON 格式: {{\"relationship\": \"TYPE\", \"confidence\": 0.85}}"
        )
    
    def _parse_camel_relationship_response(
        self,
        response: str,
        instructions: Dict[str, Any]
    ) -> Tuple[Optional[RelationshipType], float]:
        """解析 CAMEL 关系响应"""
        try:
            # 提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                return None, 0.0
            
            data = json.loads(json_match.group(0))
            rel_str = data.get("relationship", "NONE")
            confidence = float(data.get("confidence", 0.0))
            
            # 验证置信度
            if confidence < instructions.get("semantic_relation_threshold", 0.7):
                return None, confidence
            
            # 验证关系类型
            try:
                return RelationshipType(rel_str), confidence
            except ValueError:
                # 无效关系类型
                return None, confidence
                
        except Exception as e:
            logger.warning(f"解析 CAMEL 关系响应失败: {str(e)}")
            return None, 0.0
    
    def _call_camel(self, prompt: str, task_type: str) -> str:
        """调用 CAMEL API"""
        if not self.model:
            raise ValueError("CAMEL 模型未初始化")
        
        try:
            system_msg = BaseMessage.make_system_message(
                content="你是一名专业的学术内容分析专家。"
            )
            user_msg = BaseMessage.make_user_message(
                role_name="用户",
                content=prompt
            )
            
            agent = ChatAgent(
                system_message=system_msg,
                model=self.model,
                output_language="Chinese"
            )
            
            response = agent.step(user_msg)
            
            if not response or not response.msg:
                raise ValueError("CAMEL 返回空响应")
            
            return response.msg.content.strip()
            
        except Exception as e:
            logger.warning(f"CAMEL 调用失败 ({task_type}): {str(e)}")
            raise
    
    def _generate_refinement_feedback(
        self,
        stats: Dict[str, Any],
        instructions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成细化反馈"""
        success_rate = (stats["total_rough_nodes"] - stats["errors"]) / max(1, stats["total_rough_nodes"])
        
        return {
            "status": "success",
            "method": "semantic_refinement",
            "total_rough_nodes": stats["total_rough_nodes"],
            "refined_nodes": stats["refined_nodes"],
            "segments_created": stats["segments_created"],
            "relationships_built": stats["relationships_built"],
            "camel_relation_calls": stats["camel_relation_calls"],
            "errors": stats["errors"],
            "success_rate": round(success_rate, 3),
            "semantic_relations_enabled": instructions.get("build_semantic_relations", True),
            "segmentation_method": "hybrid (camel+rule)",
            "suggestions": self._generate_suggestions(stats, instructions)
        }
    
    def _generate_suggestions(
        self,
        stats: Dict[str, Any],
        instructions: Dict[str, Any]
    ) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        if stats["errors"] > 0:
            suggestions.append(f"发生 {stats['errors']} 次细化错误，建议检查 CAMEL 配置或网络连接")
        
        if stats["segments_created"] > stats["total_rough_nodes"] * 3:
            suggestions.append(f"创建了 {stats['segments_created']} 个片段，可能过细，建议提高 refine_threshold")
        
        if stats["camel_relation_calls"] > 0 and stats["relationships_built"] == 0:
            suggestions.append("CAMEL 调用未建立任何关系，检查关系类型白名单配置")
        
        if stats["segments_created"] < stats["total_rough_nodes"]:
            suggestions.append("片段数量少于粗分节点，可能未充分细化，建议降低 refine_threshold")
        
        return suggestions