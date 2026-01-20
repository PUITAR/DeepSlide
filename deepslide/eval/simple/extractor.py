import re
from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class SlideFrame:
    """幻灯片帧数据结构"""
    index: int
    title: str
    content: str
    slide_type: str  # section 或 frame
    has_image: bool = False
    image_paths: List[str] = None
    bullet_count: int = 0
    column_count: int = 1  # 分栏数
    
    def __post_init__(self):
        if self.image_paths is None:
            self.image_paths = []

@dataclass
class SpeechParagraph:
    """演讲稿段落数据结构"""
    index: int
    text: str
    word_count: int = 0
    
    def __post_init__(self):
        if self.word_count == 0 and self.text:
            self.word_count = len(self.text.split())

class PPTExtractor:
    """PPT内容提取器"""
    
    @staticmethod
    def extract_from_latex(latex_text: str) -> List[SlideFrame]:
        """从LaTeX Beamer代码中提取PPT内容"""
        frames = []
        
        # 尝试不同的分割方式
        # 方式1: 按 %% ITEM 分割
        items = re.split(r'(%%\s*ITEM\s*\d+\s*TYPE\s*\w+)', latex_text)
        
        # 第一个元素可能是空字符串或文件头
        if items and not items[0].strip():
            items = items[1:]
        
        current_type = None
        current_content = ""
        
        for i, item in enumerate(items):
            item = item.strip()
            if not item:
                continue
            
            # 判断是否是ITEM标记
            if item.startswith('%% ITEM'):
                # 处理上一个累积的内容
                if current_type and current_content:
                    frames.extend(PPTExtractor._process_item(current_type, current_content, len(frames)))
                
                # 提取新类型
                type_match = re.search(r'TYPE\s*(\w+)', item)
                current_type = type_match.group(1) if type_match else "Unknown"
                current_content = ""
            else:
                # 累积内容
                current_content += item + "\n"
        
        # 处理最后一个项目
        if current_type and current_content:
            frames.extend(PPTExtractor._process_item(current_type, current_content, len(frames)))
        
        return frames
    
    @staticmethod
    def _process_item(item_type: str, content: str, start_index: int) -> List[SlideFrame]:
        """处理单个ITEM的内容"""
        frames = []
        
        if item_type == 'Section':
            # 尝试提取所有section
            section_matches = re.findall(r'\\section\{(.*?)\}', content, re.DOTALL)
            for i, section_title in enumerate(section_matches):
                frame = SlideFrame(
                    index=start_index + len(frames),
                    title=section_title.strip(),
                    content=section_title.strip(),
                    slide_type='section'
                )
                frames.append(frame)
        
        elif item_type == 'Frame':
            # 尝试提取所有frame
            # 查找所有\begin{frame}...\end{frame}块
            frame_pattern = r'\\begin\{frame\}(.*?)\\end\{frame\}'
            frame_matches = re.findall(frame_pattern, content, re.DOTALL)
            
            for i, frame_content in enumerate(frame_matches):
                # 提取frame标题
                title_match = re.search(r'\\frametitle\{(.*?)\}', frame_content, re.DOTALL)
                title = title_match.group(1).strip() if title_match else f"Frame {i+1}"
                
                # 提取完整内容
                full_content = PPTExtractor._extract_frame_content(frame_content)
                
                # 检查是否有图片
                has_image = '\\includegraphics' in frame_content
                image_paths = PPTExtractor._extract_image_paths(frame_content)
                
                # 计算项目符号数
                bullet_count = frame_content.count('\\item')
                
                frame = SlideFrame(
                    index=start_index + len(frames),
                    title=title,
                    content=full_content,
                    slide_type='frame',
                    has_image=has_image,
                    image_paths=image_paths,
                    bullet_count=bullet_count,
                    column_count=2 if '\\begin{columns}' in frame_content else 1
                )
                frames.append(frame)
        
        return frames
    
    @staticmethod
    def _extract_frame_content(latex_content: str) -> str:
        """提取frame的内容（保持关键信息）- 改进版"""
        if not latex_content:
            return ""
        
        content = latex_content
        
        # 1. 移除 \frametitle{...}
        content = re.sub(r'\\frametitle\{.*?\}', '', content, flags=re.DOTALL)
        
        # 2. 处理itemize环境，保留\item内容
        # 先移除\begin{itemize}和\end{itemize}
        content = re.sub(r'\\begin\{itemize\}', '', content)
        content = re.sub(r'\\end\{itemize\}', '', content)
        # 将\item替换为项目符号
        content = re.sub(r'\\item\s*', '• ', content)
        
        # 3. 处理columns环境
        content = re.sub(r'\\begin\{columns\}', '', content)
        content = re.sub(r'\\end\{columns\}', '', content)
        content = re.sub(r'\\begin\{column\}.*?\}', '', content)  # 移除列宽设置
        content = re.sub(r'\\end\{column\}', '', content)
        
        # 4. 处理figure环境
        content = re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', '', content, flags=re.DOTALL)
        
        # 5. 保留加粗、斜体等格式的内容
        content = re.sub(r'\\textbf\{(.*?)\}', r'\1', content, flags=re.DOTALL)
        content = re.sub(r'\\textit\{(.*?)\}', r'\1', content, flags=re.DOTALL)
        content = re.sub(r'\\emph\{(.*?)\}', r'\1', content, flags=re.DOTALL)
        
        # 6. 处理数学公式
        content = re.sub(r'\$(.*?)\$', r'[公式:\1]', content)
        content = re.sub(r'\$\$(.*?)\$\$', r'[公式:\1]', content, flags=re.DOTALL)
        
        # 7. 处理\mathcal和\mathbb
        content = re.sub(r'\\mathcal\{(.*?)\}', r'\1', content, flags=re.DOTALL)
        content = re.sub(r'\\mathbb\{(.*?)\}', r'\1', content, flags=re.DOTALL)
        
        # 8. 移除其他LaTeX命令但保留大括号内容
        content = re.sub(r'\\[a-zA-Z]+\{(.*?)\}', r'\1', content, flags=re.DOTALL)
        
        # 9. 移除单独的LaTeX命令
        content = re.sub(r'\\[a-zA-Z]+\b', '', content)
        
        # 10. 移除注释
        content = re.sub(r'%.*?\n', ' ', content)
        
        # 11. 移除图片命令（已单独记录）
        content = re.sub(r'\\includegraphics.*?\{.*?\}', '', content, flags=re.DOTALL)
        content = re.sub(r'\\caption\{.*?\}', '', content, flags=re.DOTALL)
        
        # 12. 清理空白字符
        content = re.sub(r'\s+', ' ', content)
        content = content.strip()
        
        return content
    
    @staticmethod
    def _extract_image_paths(latex_content: str) -> List[str]:
        """提取图片路径"""
        paths = []
        matches = re.findall(r'\\includegraphics.*?\{(.*?)\}', latex_content)
        for match in matches:
            path = match.strip().strip('{}')
            if path:
                paths.append(path)
        return paths

class SpeechExtractor:
    """演讲稿内容提取器"""
    
    @staticmethod
    def extract_from_text(speech_text: str) -> List[SpeechParagraph]:
        """从演讲稿文本中提取段落"""
        paragraphs = []
        
        # 按<next>标签分割
        segments = re.split(r'<next>\s*', speech_text.strip())
        
        for i, segment in enumerate(segments):
            if not segment.strip():
                continue
            
            # 清理文本，去除<add>标签
            clean_text = re.sub(r'<add>\s*', '', segment).strip()
            clean_text = re.sub(r'<next>', '', clean_text).strip()
            
            # 提取段落
            if clean_text:
                paragraph = SpeechParagraph(
                    index=i,
                    text=clean_text,
                    word_count=len(clean_text.split())
                )
                paragraphs.append(paragraph)
        
        return paragraphs

class PresentationData:
    """演示文稿数据管理器"""
    
    def __init__(self, latex_text: str = None, speech_text: str = None):
        self.latex_text = latex_text
        self.speech_text = speech_text
        self.slide_frames = []
        self.speech_paragraphs = []
        
        if latex_text:
            self.extract_slides()
        
        if speech_text:
            self.extract_speech()
    
    def extract_slides(self, latex_text: str = None):
        """提取幻灯片内容"""
        if latex_text:
            self.latex_text = latex_text
        
        if not self.latex_text:
            raise ValueError("No LaTeX text provided")
        
        self.slide_frames = PPTExtractor.extract_from_latex(self.latex_text)
    
    def extract_speech(self, speech_text: str = None):
        """提取演讲稿内容"""
        if speech_text:
            self.speech_text = speech_text
        
        if not self.speech_text:
            raise ValueError("No speech text provided")
        
        self.speech_paragraphs = SpeechExtractor.extract_from_text(self.speech_text)
        
    def align_presentation(self) -> List[Dict[str, Any]]:
        """对齐幻灯片和演讲稿（仅对齐frame类型的幻灯片）"""
        aligned_presentation = []
        
        # 1. 过滤出所有frame类型的幻灯片（跳过section）
        frame_slides = [slide for slide in self.slide_frames if slide.slide_type == 'frame']
        
        if not frame_slides:
            print("警告：没有找到frame类型的幻灯片")
            return aligned_presentation
        
        if not self.speech_paragraphs:
            print("警告：没有演讲稿段落")
            return aligned_presentation
        
        # 2. 按顺序对齐frame幻灯片和演讲稿段落
        min_length = min(len(frame_slides), len(self.speech_paragraphs))
        
        for i in range(min_length):
            slide = frame_slides[i]
            speech = self.speech_paragraphs[i]
            
            # 计算内容匹配度（改进版）
            content_match_score = self._calculate_content_match(slide.content, speech.text)
            
            aligned_presentation.append({
                'slide_index': slide.index,
                'frame_index': i,  # 在frame列表中的索引
                'speech_index': speech.index,
                'slide_title': slide.title,
                'slide_content': slide.content[:500] + "..." if len(slide.content) > 500 else slide.content,
                'speech_text': speech.text[:500] + "..." if len(speech.text) > 500 else speech.text,
                'slide_type': slide.slide_type,
                'has_image': slide.has_image,
                'image_count': len(slide.image_paths),
                'bullet_count': slide.bullet_count,
                'column_count': slide.column_count,
                'speech_word_count': speech.word_count,
                'content_match_score': content_match_score,
                'is_aligned': True
            })
        
        # 3. 处理未对齐的部分
        if len(frame_slides) > len(self.speech_paragraphs):
            print(f"警告：有 {len(frame_slides) - len(self.speech_paragraphs)} 个frame没有对应的演讲稿段落")
            
            # 为多余的frame创建部分对齐记录
            for i in range(len(self.speech_paragraphs), len(frame_slides)):
                slide = frame_slides[i]
                aligned_presentation.append({
                    'slide_index': slide.index,
                    'frame_index': i,
                    'speech_index': None,
                    'slide_title': slide.title,
                    'slide_content': slide.content[:500] + "..." if len(slide.content) > 500 else slide.content,
                    'speech_text': "（无对应演讲稿）",
                    'slide_type': slide.slide_type,
                    'has_image': slide.has_image,
                    'image_count': len(slide.image_paths),
                    'bullet_count': slide.bullet_count,
                    'column_count': slide.column_count,
                    'speech_word_count': 0,
                    'content_match_score': 0.0,
                    'is_aligned': False
                })
        
        elif len(self.speech_paragraphs) > len(frame_slides):
            print(f"警告：有 {len(self.speech_paragraphs) - len(frame_slides)} 个演讲稿段落没有对应的frame")
            
            # 为多余的演讲稿段落创建部分对齐记录
            for i in range(len(frame_slides), len(self.speech_paragraphs)):
                speech = self.speech_paragraphs[i]
                aligned_presentation.append({
                    'slide_index': None,
                    'frame_index': None,
                    'speech_index': speech.index,
                    'slide_title': "（无对应幻灯片）",
                    'slide_content': "（无对应幻灯片）",
                    'speech_text': speech.text[:500] + "..." if len(speech.text) > 500 else speech.text,
                    'slide_type': None,
                    'has_image': False,
                    'image_count': 0,
                    'bullet_count': 0,
                    'column_count': 1,
                    'speech_word_count': speech.word_count,
                    'content_match_score': 0.0,
                    'is_aligned': False
                })
        
        return aligned_presentation

    def _calculate_content_match(self, slide_content: str, speech_text: str) -> float:
        """计算幻灯片内容和演讲稿的匹配度（改进版）"""
        if not slide_content or not speech_text:
            return 0.0
        
        # 预处理：移除公式标记和特殊字符
        def clean_text(text):
            # 移除公式标记
            text = re.sub(r'\[公式:.*?\]', '', text)
            # 移除特殊字符，保留字母、数字和空格
            text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
            # 转为小写
            text = text.lower()
            # 分割单词
            words = text.split()
            # 移除短词和常见词
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 
                         'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 
                         'been', 'being', 'this', 'that', 'these', 'those', 'it', 'its'}
            words = [w for w in words if len(w) > 2 and w not in stop_words]
            return set(words)
        
        slide_words = clean_text(slide_content)
        speech_words = clean_text(speech_text)
        
        if not slide_words or not speech_words:
            return 0.0
        
        # 计算Jaccard相似度
        intersection = len(slide_words & speech_words)
        union = len(slide_words | speech_words)
        
        return intersection / union if union > 0 else 0.0
        
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计数据（更新对齐统计）"""
        stats = {
            'total_slides': len(self.slide_frames),
            'total_speech_paragraphs': len(self.speech_paragraphs),
            'section_count': sum(1 for f in self.slide_frames if f.slide_type == 'section'),
            'frame_count': sum(1 for f in self.slide_frames if f.slide_type == 'frame'),
            'total_images': sum(len(f.image_paths) for f in self.slide_frames),
            'total_bullet_points': sum(f.bullet_count for f in self.slide_frames),
            'total_speech_words': sum(p.word_count for p in self.speech_paragraphs)
        }
        
        # 平均统计
        if stats['frame_count'] > 0:
            stats['avg_bullets_per_frame'] = stats['total_bullet_points'] / stats['frame_count']
            stats['avg_images_per_frame'] = stats['total_images'] / stats['frame_count']
        
        if stats['total_speech_paragraphs'] > 0:
            stats['avg_words_per_paragraph'] = stats['total_speech_words'] / stats['total_speech_paragraphs']
        
        # 对齐统计
        aligned = self.align_presentation()
        aligned_frames = [item for item in aligned if item['is_aligned']]
        stats['aligned_frames_count'] = len(aligned_frames)
        stats['unaligned_frames_count'] = len(aligned) - len(aligned_frames)
        
        # 平均内容匹配度
        if aligned_frames:
            avg_match_score = sum(item['content_match_score'] for item in aligned_frames) / len(aligned_frames)
            stats['avg_content_match_score'] = avg_match_score
        
        return stats
    
    def print_summary(self):
        """打印摘要（更新对齐信息显示）"""
        print("=" * 60)
        print("演示文稿内容摘要")
        print("=" * 60)
        
        stats = self.get_statistics()
        
        print(f"\n幻灯片统计:")
        print(f"  - 总项目数: {stats['total_slides']}")
        print(f"  - 章节数: {stats['section_count']}")
        print(f"  - 幻灯片页数: {stats['frame_count']}")
        print(f"  - 图片总数: {stats['total_images']}")
        print(f"  - 项目符号总数: {stats['total_bullet_points']}")
        if stats['frame_count'] > 0:
            print(f"  - 平均每页项目符号: {stats.get('avg_bullets_per_frame', 0):.1f}")
        
        print(f"\n演讲稿统计:")
        print(f"  - 段落数: {stats['total_speech_paragraphs']}")
        print(f"  - 总字数: {stats['total_speech_words']}")
        if stats['total_speech_paragraphs'] > 0:
            print(f"  - 平均每段字数: {stats.get('avg_words_per_paragraph', 0):.1f}")
        
        # 对齐信息
        aligned = self.align_presentation()
        aligned_frames = [item for item in aligned if item['is_aligned']]
        
        print(f"\n对齐情况:")
        print(f"  - 成功对齐的frame数: {stats.get('aligned_frames_count', 0)}")
        if 'avg_content_match_score' in stats:
            print(f"  - 平均内容匹配度: {stats['avg_content_match_score']:.2f}")
        
        if len(aligned) > len(aligned_frames):
            print(f"  - 未对齐项目数: {stats.get('unaligned_frames_count', 0)}")
        
        # 显示前3个对齐的frame
        if aligned_frames:
            print("\n前3个对齐的frame:")
            for i, item in enumerate(aligned_frames[:3]):
                print(f"\n{i+1}. {item['slide_title']}")
                print(f"   幻灯片内容预览: {item['slide_content'][:150]}...")
                print(f"   演讲稿内容预览: {item['speech_text'][:150]}...")
                print(f"   内容匹配度: {item['content_match_score']:.2f}")
                print(f"   是否有图片: {'是' if item['has_image'] else '否'}")
        else:
            print("\n警告：没有成功对齐的项目")
        
        # 显示未对齐的项目
        unaligned_items = [item for item in aligned if not item['is_aligned']]
        if unaligned_items:
            print(f"\n未对齐项目 ({len(unaligned_items)} 个):")
            for item in unaligned_items[:2]:  # 只显示前2个
                if item['slide_index'] is None:
                    print(f"  - 演讲稿段落 {item['speech_index']+1} 没有对应的幻灯片")
                elif item['speech_index'] is None:
                    print(f"  - 幻灯片 '{item['slide_title']}' 没有对应的演讲稿段落")
        
        print("\n" + "=" * 60)