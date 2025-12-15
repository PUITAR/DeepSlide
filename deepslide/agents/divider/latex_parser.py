# latex_parser.py
"""
简化版LaTeX解析器 - 专注于章节结构提取
保留原始LaTeX命令和精确位置信息，为粗略划分提供基础
"""

import re
from typing import List, Dict


class LatexParser:
    """LaTeX解析器 - 仅提取章节结构，保留原始命令和位置信息"""
    
    def __init__(self):
        # 章节命令模式（支持可选参数，如 \section[short]{long}）
        self.section_patterns = [
            (r'\\chapter(?:\[[^\]]*\])?\*?\{([^}]*)\}', 1),
            (r'\\section(?:\[[^\]]*\])?\*?\{([^}]*)\}', 2),
            (r'\\subsection(?:\[[^\]]*\])?\*?\{([^}]*)\}', 3),
            (r'\\subsubsection(?:\[[^\]]*\])?\*?\{([^}]*)\}', 4),
            (r'\\paragraph(?:\[[^\]]*\])?\*?\{([^}]*)\}', 5),
        ]
    
    def extract_sections(self, tex_content: str) -> List[Dict]:
        sections = []
        matches = []
        
        for pattern, level in self.section_patterns:
            for match in re.finditer(pattern, tex_content, re.DOTALL):
                title_raw = match.group(1)  # 提取 { } 中的原始标题内容
                title_clean = self._clean_title(title_raw)
                matches.append({
                    'title': title_clean,
                    'title_raw': title_raw,  # ← 确保包含此字段
                    'level': level,
                    'start': match.start(),
                    'end': match.end(),
                    'full_match': match.group(0),
                })
        
        matches.sort(key=lambda x: x['start'])
        
        if not matches:
            sections.append({
                'title': 'Document',
                'title_raw': '',  # ← 确保包含此字段
                'content': tex_content.strip(),
                'level': 1,
                'start_char': 0,
                'end_char': len(tex_content),
                'command': ''
            })
            return sections
        
        for i, match in enumerate(matches):
            content_start = match['end']
            content_end = matches[i + 1]['start'] if i + 1 < len(matches) else len(tex_content)
            content = tex_content[content_start:content_end].strip()
            content = self._remove_comments(content)
            
            # 保留所有匹配的章节（即使内容为空，也保留结构）
            sections.append({
                'title': match['title'],
                'title_raw': match['title_raw'],  # ← 关键：必须包含
                'content': content,
                'level': match['level'],
                'start_char': match['start'],
                'end_char': content_end,
                'command': match['full_match']
            })
        
        return sections
    
    def _clean_title(self, title: str) -> str:
        """仅移除标题中的行内注释"""
        return re.sub(r'%.*$', '', title, flags=re.MULTILINE).strip()
    
    def _remove_comments(self, content: str) -> str:
        """移除内容中的行内注释"""
        lines = []
        for line in content.split('\n'):
            pos = line.find('%')
            if pos != -1:
                line = line[:pos].rstrip()
            if line:
                lines.append(line)
        return '\n'.join(lines).strip()
    
    def analyze_document_structure(self, tex_content: str) -> Dict:
        sections = self.extract_sections(tex_content)
        level_dist = {}
        for sec in sections:
            level_dist[sec['level']] = level_dist.get(sec['level'], 0) + 1
        return {
            'total_sections': len(sections),
            'level_distribution': level_dist,
            'has_hierarchy': len(level_dist) > 1,
            'avg_section_length': sum(len(s['content']) for s in sections) / len(sections) if sections else 0
        }