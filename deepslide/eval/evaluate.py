import os
import sys
import json

class PPT_Speech_Evaluator:
    """
    用于评估PPT和Speech对齐质量的类
    """
    
    # 常量定义
    PPT_ITEM_MARKER = '%% ITEM'
    PPT_TYPE_MARKER = 'TYPE'
    SPEECH_SEPARATOR = '<next>'
    ADD_MARKER = '<add>'
    PPT_TITLE_START = '\\frametitle{'
    PPT_TITLE_END = '}'
    
    def __init__(self, ppt_text=None, speech_text=None):
        """
        初始化评估器
        
        Args:
            ppt_text (str, optional): PPT文本内容
            speech_text (str, optional): Speech文本内容
        """
        self._ppt_text = ppt_text
        self._speech_text = speech_text
        self._ppt_frames = None
        self._speech_segments = None
        self._aligned_pairs = None
        self._add_segments = None
        
    @property
    def ppt_text(self):
        return self._ppt_text
    
    @ppt_text.setter
    def ppt_text(self, value):
        self._ppt_text = value
        self._ppt_frames = None  # 清除缓存
        
    @property
    def speech_text(self):
        return self._speech_text
    
    @speech_text.setter
    def speech_text(self, value):
        self._speech_text = value
        self._speech_segments = None  # 清除缓存
        
    @property
    def ppt_frames(self):
        """惰性计算PPT帧"""
        if self._ppt_frames is None:
            self._ppt_frames = self._extract_ppt_frames()
        return self._ppt_frames
    
    @property
    def speech_segments(self):
        """惰性计算Speech段"""
        if self._speech_segments is None:
            self._speech_segments = self._extract_speech_segments()
        return self._speech_segments
    
    @property
    def aligned_pairs(self):
        """惰性计算对齐对"""
        if self._aligned_pairs is None:
            self._aligned_pairs, self._add_segments = self._align_ppt_speech()
        return self._aligned_pairs
    
    @property
    def add_segments(self):
        """惰性计算add部分"""
        if self._add_segments is None:
            self._aligned_pairs, self._add_segments = self._align_ppt_speech()
        return self._add_segments
    
    def load_ppt_from_file(self, filepath):
        """
        从文件加载PPT文本
        
        Args:
            filepath (str): PPT文件路径
            
        Returns:
            self: 返回实例本身以便链式调用
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self._ppt_text = f.read()
            self._ppt_frames = None  # 清除缓存
            print(f"已加载PPT文件: {filepath}")
        except Exception as e:
            print(f"加载PPT文件失败: {e}")
        return self

    def load_speech_from_file(self, filepath):
        """
        从文件加载Speech文本
        
        Args:
            filepath (str): Speech文件路径
            
        Returns:
            self: 返回实例本身以便链式调用
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self._speech_text = f.read()
            self._speech_segments = None  # 清除缓存
            print(f"已加载Speech文件: {filepath}")
        except Exception as e:
            print(f"加载Speech文件失败: {e}")
        return self

    def _extract_ppt_frames(self):
        """
        从PPT文本中提取分帧（内部方法）
        
        Returns:
            list: PPT帧列表
        """
        if not self._ppt_text:
            print("错误: PPT文本为空")
            return []
            
        # 分割成行
        lines = self._ppt_text.split('\n')
        
        frames = []
        current_frame = []
        collecting = False
        
        for line in lines:
            # 检查是否是新的ITEM开始
            if self.PPT_ITEM_MARKER in line and self.PPT_TYPE_MARKER in line:
                # 如果之前已经在收集帧，则保存它
                if collecting:
                    if current_frame:  # 确保不是空的
                        frames.append('\n'.join(current_frame))
                    current_frame = []
                # 标记开始收集内容
                collecting = True
            elif collecting:
                # 收集内容行
                current_frame.append(line)
        
        # 添加最后一个帧
        if current_frame:
            frames.append('\n'.join(current_frame))
        
        return frames

    def _extract_speech_segments(self):
        """
        从Speech文本中提取段（内部方法）
        
        Returns:
            list: Speech段列表
        """
        if not self._speech_text:
            print("错误: Speech文本为空")
            return []
            
        segments = self._speech_text.split(self.SPEECH_SEPARATOR)
        cleaned_segments = [segment.strip() for segment in segments if segment.strip()]
        
        return cleaned_segments

    def _align_ppt_speech(self):
        """
        对齐PPT帧和Speech段（内部方法）
        
        Returns:
            tuple: (aligned_pairs, add_segments) 对齐对和add部分
        """
        ppt_frames = self.ppt_frames
        speech_segments = self.speech_segments
        
        print(f"PPT帧数: {len(ppt_frames)}")
        print(f"Speech段数: {len(speech_segments)}")
        
        # 识别add部分和主内容
        add_segments = []
        main_speech_segments = []
        
        for i, segment in enumerate(speech_segments):
            # 简单判断：以<add>开头的可能是add
            if segment.startswith(self.ADD_MARKER):
                add_segments.append((f"add_{i}", segment))
            else:
                main_speech_segments.append(segment)
        
        # 确保数量匹配
        if len(main_speech_segments) < len(ppt_frames):
            # 如果Speech段不够，用空字符串填充
            print(f"警告: 主Speech段数({len(main_speech_segments)})少于PPT帧数({len(ppt_frames)})，使用空字符串填充")
            while len(main_speech_segments) < len(ppt_frames):
                main_speech_segments.append("")
        elif len(main_speech_segments) > len(ppt_frames):
            # 如果Speech段太多，只取前ppt_frames个
            print(f"警告: 主Speech段数({len(main_speech_segments)})多于PPT帧数({len(ppt_frames)})，截断处理")
            main_speech_segments = main_speech_segments[:len(ppt_frames)]
        
        # 生成对齐对
        aligned_pairs = list(zip(ppt_frames, main_speech_segments))
        
        return aligned_pairs, add_segments

    def evaluate(self, output_dir=None):
        """
        执行评估并输出结果
        
        Args:
            output_dir (str, optional): 输出目录路径
            
        Returns:
            dict: 评估结果
        """
        # 使用属性访问触发惰性计算
        ppt_frames = self.ppt_frames
        speech_segments = self.speech_segments
        aligned_pairs = self.aligned_pairs
        add_segments = self.add_segments
        
        # 输出结果到控制台
        print(f"\n评估结果:")
        print(f"  PPT帧数: {len(ppt_frames)}")
        print(f"  Speech段数: {len(speech_segments)}")
        print(f"  对齐对数: {len(aligned_pairs)}")
        print(f"  Add部分数: {len(add_segments)}")
        
        # 保存结果到文件
        if output_dir:
            self.save_results(output_dir)
        
        # 返回结果用于后续处理
        return {
            "ppt_frames": ppt_frames,
            "speech_segments": speech_segments,
            "aligned_pairs": aligned_pairs,
            "add_segments": add_segments
        }

    def save_results(self, output_dir):
        """
        保存评估结果到文件
        
        Args:
            output_dir (str): 输出目录路径
        """
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存文本格式结果
        self._save_text_results(output_dir)
        
        # 保存JSON格式结果
        self._save_json_results(output_dir)

    def _save_text_results(self, output_dir):
        """
        保存文本格式结果
        """
        output_path = os.path.join(output_dir, "alignment_results.txt")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("PPT-SPEECH对齐评估结果\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"PPT帧数: {len(self._ppt_frames)}\n")
            f.write(f"Speech段数: {len(self._speech_segments)}\n")
            f.write(f"对齐对数: {len(self._aligned_pairs)}\n")
            f.write(f"Add部分数: {len(self._add_segments)}\n\n")
            
            # 写入add部分
            if self._add_segments:
                f.write("Add部分:\n")
                for name, content in self._add_segments:
                    f.write(f"  {name}: {content[:100]}...\n")
                f.write("\n")
            
            # 写入对齐对
            if self._aligned_pairs:
                f.write("对齐对:\n")
                for i, (frame, speech) in enumerate(self._aligned_pairs, 1):
                    # 提取PPT标题
                    title_start = frame.find(self.PPT_TITLE_START)
                    title = ""
                    if title_start != -1:
                        title_end = frame.find(self.PPT_TITLE_END, title_start)
                        if title_end != -1:
                            title = frame[title_start+len(self.PPT_TITLE_START):title_end]
                    
                    f.write(f"\n【第{i}对】PPT标题: {title}\n")
                    f.write(f"PPT内容预览: {frame[:200].replace(chr(10), ' ').replace(chr(13), ' ')}...\n")
                    f.write(f"Speech内容预览: {speech[:200].replace(chr(10), ' ').replace(chr(13), ' ')}...\n")
                    f.write("-" * 50 + "\n")
        
        print(f"文本结果已保存到: {output_path}")

    def _save_json_results(self, output_dir):
        """
        保存JSON格式结果
        """
        # 准备JSON数据结构
        json_data = {
            "summary": {
                "ppt_frame_count": len(self._ppt_frames),
                "speech_segment_count": len(self._speech_segments),
                "aligned_pair_count": len(self._aligned_pairs),
                "add_segment_count": len(self._add_segments),
            },
            "add_segments": [
                {
                    "id": name,
                    "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
                    "content_length": len(content)
                }
                for name, content in self._add_segments
            ],
            "aligned_pairs": [
                {
                    "pair_id": i,
                    "ppt_title": self._extract_ppt_title(frame),
                    "ppt_content_preview": frame[:200] + ("..." if len(frame) > 200 else ""),
                    "ppt_content_length": len(frame),
                    "speech_content_preview": speech[:200] + ("..." if len(speech) > 200 else ""),
                    "speech_content_length": len(speech)
                }
                for i, (frame, speech) in enumerate(self._aligned_pairs, 1)
            ]
        }
        
        # 保存JSON文件
        json_path = os.path.join(output_dir, "alignment_results.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        print(f"JSON结果已保存到: {json_path}")

    def _extract_ppt_title(self, frame):
        """从PPT帧中提取标题"""
        title_start = frame.find(self.PPT_TITLE_START)
        if title_start != -1:
            title_end = frame.find(self.PPT_TITLE_END, title_start)
            if title_end != -1:
                return frame[title_start+len(self.PPT_TITLE_START):title_end]
        return ""

    def get_aligned_pairs(self):
        """
        获取对齐的对
        
        Returns:
            list: 对齐对列表
        """
        return self.aligned_pairs

    def get_add_segments(self):
        """
        获取add部分
        
        Returns:
            list: add部分列表
        """
        return self.add_segments

    def get_summary(self):
        """
        获取评估摘要
        
        Returns:
            dict: 评估摘要
        """
        return {
            "ppt_frame_count": len(self.ppt_frames),
            "speech_segment_count": len(self.speech_segments),
            "aligned_pair_count": len(self.aligned_pairs),
            "add_segment_count": len(self.add_segments),
        }

def main():
    """主函数"""
    # 设置路径
    data_dir = "/home/ym/DeepSlide/deepslide/eval/data/gen_7a168fdc2f964310bddef4c3a5ab9be4"
    output_dir = "/home/ym/DeepSlide/deepslide/eval/output"

    ppt_path = os.path.join(data_dir, "content.tex")
    speech_path = os.path.join(data_dir, "speech.txt")

    # 检查文件是否存在
    if not os.path.exists(ppt_path):
        print(f"错误: PPT文件不存在 - {ppt_path}")
        return

    if not os.path.exists(speech_path):
        print(f"错误: Speech文件不存在 - {speech_path}")
        return

    # 使用链式调用执行评估
    evaluator = PPT_Speech_Evaluator()
    results = evaluator.load_ppt_from_file(ppt_path) \
                      .load_speech_from_file(speech_path) \
                      .evaluate(output_dir)
    
    # 获取摘要信息
    summary = evaluator.get_summary()
    print(f"\n评估摘要: {summary}")

if __name__ == "__main__":
    main()