import os
import json
import sys
from typing import Tuple, Optional

# 导入你写的提取器代码
try:
    from extractor import PresentationData
except ImportError:
    # 如果导入失败，尝试直接运行当前目录的extractor.py
    import sys
    sys.path.append('.')
    from extractor import PresentationData


# 修改为正确的路径
data_path = '/home/ym/DeepSlide/deepslide/eval/simple/data/gen_7a168fdc2f964310bddef4c3a5ab9be4'
output_dir = '/home/ym/DeepSlide/deepslide/eval/output'  # 修正拼写错误

def load_files_from_path(path: str) -> Tuple[str, str, Optional[str]]:
    """
    从指定路径加载LaTeX文件和演讲稿文件
    
    Args:
        path: 文件路径
    
    Returns:
        tuple: (latex_content, speech_content, error_message)
    """
    latex_files = []
    speech_file = None
    
    print(f"\n正在搜索路径: {path}")
    print(f"目录内容: {os.listdir(path)}")
    
    # 查找所有.tex文件
    for file in os.listdir(path):
        file_path = os.path.join(path, file)
        
        if file.endswith('.tex'):
            latex_files.append(file_path)
            print(f"  找到LaTeX文件: {file}")
        elif file == 'speech.txt':
            speech_file = file_path
            print(f"  找到演讲稿文件: {file}")
    
    # 如果没有找到文件，尝试其他常见名称
    if not latex_files:
        print("未找到.tex文件，尝试其他扩展名...")
        for file in os.listdir(path):
            file_lower = file.lower()
            if 'presentation' in file_lower or 'ppt' in file_lower or 'slide' in file_lower:
                latex_files.append(os.path.join(path, file))
                print(f"  找到可能的LaTeX文件: {file}")
                break
    
    if not speech_file:
        print("未找到演讲稿文件，尝试其他扩展名...")
        for file in os.listdir(path):
            file_lower = file.lower()
            if 'speech' in file_lower or 'script' in file_lower or 'transcript' in file_lower:
                speech_file = os.path.join(path, file)
                print(f"  找到可能的演讲稿文件: {file}")
                break
    
    # 读取所有LaTeX文件并合并
    latex_content = ""
    for latex_file in sorted(latex_files):  # 按文件名排序
        if os.path.exists(latex_file):
            try:
                with open(latex_file, 'r', encoding='utf-8') as f:
                    file_content = f.read()
                latex_content += f"\n\n%% FILE: {os.path.basename(latex_file)}\n"
                latex_content += file_content
                print(f"✓ 已加载LaTeX文件: {os.path.basename(latex_file)}")
                print(f"  文件大小: {len(file_content)} 字符")
            except Exception as e:
                print(f"⚠ 读取LaTeX文件失败 {latex_file}: {e}")
    
    if not latex_content.strip():
        return "", "", f"未找到可用的LaTeX文件，请检查路径: {path}"
    
    # 读取演讲稿文件
    speech_content = ""
    if speech_file and os.path.exists(speech_file):
        try:
            with open(speech_file, 'r', encoding='utf-8') as f:
                speech_content = f.read()
            print(f"✓ 已加载演讲稿文件: {os.path.basename(speech_file)}")
            print(f"  文件大小: {len(speech_content)} 字符")
        except Exception as e:
            print(f"⚠ 读取演讲稿文件失败: {e}")
            # 继续处理，即使演讲稿读取失败
    else:
        print("⚠ 未找到演讲稿文件，仅解析PPT")
    
    return latex_content, speech_content, None

def parse_presentation(path: str, output_dir: str = None) -> PresentationData:
    """
    解析指定路径下的演示文稿文件
    
    Args:
        path: 包含PPT和演讲稿文件的目录路径
        output_dir: 输出结果的目录（可选）
    
    Returns:
        PresentationData: 解析后的演示文稿数据
    """
    print(f"\n{'='*60}")
    print(f"开始解析演示文稿")
    print(f"文件路径: {path}")
    print(f"{'='*60}")
    
    # 加载文件
    latex_content, speech_content, error = load_files_from_path(path)
    
    if error:
        if not latex_content and not speech_content:
            raise FileNotFoundError(error)
        else:
            print(f"警告: {error}")
    
    # 调试：查看文件内容前几行
    if latex_content:
        print(f"\nLaTeX内容前500字符:")
        print("-" * 40)
        print(latex_content[:500])
        print("-" * 40)
    
    # 创建演示文稿数据
    try:
        presentation = PresentationData(latex_content, speech_content)
        print("\n✓ 演示文稿解析完成")
    except Exception as e:
        print(f"❌ 解析演示文稿失败: {e}")
        # 打印详细的错误信息
        import traceback
        traceback.print_exc()
        raise Exception(f"解析演示文稿失败: {e}")
    
    # 打印摘要
    presentation.print_summary()
    
    # 保存结果到文件
    if output_dir:
        save_results(presentation, output_dir)
    
    return presentation

def save_results(presentation: PresentationData, output_dir: str):
    """
    将解析结果保存到文件
    
    Args:
        presentation: 演示文稿数据
        output_dir: 输出目录
    """
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n保存结果到目录: {output_dir}")
    
    # 1. 保存对齐的演示文稿数据
    aligned_data = presentation.align_presentation()
    aligned_file = os.path.join(output_dir, "aligned_presentation.json")
    
    with open(aligned_file, 'w', encoding='utf-8') as f:
        json.dump(aligned_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 对齐数据已保存到: {aligned_file}")
    
    # 2. 保存幻灯片数据
    slides_data = []
    for slide in presentation.slide_frames:
        slide_dict = {
            'index': slide.index,
            'title': slide.title,
            'content': slide.content,
            'slide_type': slide.slide_type,
            'has_image': slide.has_image,
            'image_paths': slide.image_paths,
            'bullet_count': slide.bullet_count,
            'column_count': slide.column_count
        }
        slides_data.append(slide_dict)
    
    slides_file = os.path.join(output_dir, "slides.json")
    with open(slides_file, 'w', encoding='utf-8') as f:
        json.dump(slides_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 幻灯片数据已保存到: {slides_file}")
    
    # 3. 保存演讲稿数据
    speech_data = []
    for para in presentation.speech_paragraphs:
        para_dict = {
            'index': para.index,
            'text': para.text,
            'word_count': para.word_count
        }
        speech_data.append(para_dict)
    
    speech_file = os.path.join(output_dir, "speech.json")
    with open(speech_file, 'w', encoding='utf-8') as f:
        json.dump(speech_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 演讲稿数据已保存到: {speech_file}")
    
    # 4. 保存统计数据
    stats = presentation.get_statistics()
    stats_file = os.path.join(output_dir, "statistics.json")
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 统计数据已保存到: {stats_file}")
    
    # 5. 生成文本报告
    report_file = os.path.join(output_dir, "extraction_report.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("演示文稿解析报告\n")
        f.write("=" * 60 + "\n\n")
        
        f.write("📊 统计数据:\n")
        f.write(f"总幻灯片数: {stats['total_slides']}\n")
        f.write(f"章节数: {stats['section_count']}\n")
        f.write(f"幻灯片页数: {stats['frame_count']}\n")
        f.write(f"图片总数: {stats['total_images']}\n")
        f.write(f"项目符号总数: {stats['total_bullet_points']}\n")
        if 'avg_bullets_per_frame' in stats:
            f.write(f"平均每页项目符号: {stats['avg_bullets_per_frame']:.1f}\n")
        
        f.write(f"\n演讲稿段落数: {stats['total_speech_paragraphs']}\n")
        f.write(f"演讲稿总字数: {stats['total_speech_words']}\n")
        if 'avg_words_per_paragraph' in stats:
            f.write(f"平均每段字数: {stats['avg_words_per_paragraph']:.1f}\n")
        
        f.write("\n" + "=" * 60 + "\n")
        f.write("📄 幻灯片详情:\n")
        f.write("=" * 60 + "\n\n")
        
        for slide in presentation.slide_frames:
            f.write(f"【{slide.slide_type.upper()}】{slide.title}\n")
            f.write(f"内容预览: {slide.content[:500]}\n")
            if slide.has_image:
                f.write(f"包含图片: {len(slide.image_paths)} 张\n")
            f.write(f"项目符号数: {slide.bullet_count}\n")
            f.write("-" * 40 + "\n")
    
    print(f"✓ 文本报告已保存到: {report_file}")
    
    print(f"\n✅ 所有结果已保存到目录: {output_dir}")


def quick_parse(path: str = "."):
    """
    快速解析函数，可以直接调用
    
    Args:
        path: 文件路径，默认为当前目录
    
    Example:
        quick_parse("/home/user/presentation_files")
    """
    try:
        presentation = parse_presentation(path)
        return presentation
    except Exception as e:
        print(f"解析失败: {e}")
        return None

def get_evaluation_data(presentation: PresentationData) -> dict:
    """
    从解析结果中获取评估系统需要的数据
    
    Args:
        presentation: 解析后的演示文稿数据
    
    Returns:
        dict: 评估系统需要的数据格式
    """
    if not presentation.slide_frames or not presentation.speech_paragraphs:
        print("警告: 幻灯片或演讲稿数据为空")
        return {}
    
    # 准备评估系统输入
    frames_data = []
    paras_data = []
    
    # 转换幻灯片数据
    for slide in presentation.slide_frames:
        # 简化版本，你可以根据需要添加更多字段
        frame_dict = {
            "content": slide.content,
            "title": slide.title,
            "has_image": slide.has_image,
            "has_bullet": slide.bullet_count > 0,
            "slide_type": slide.slide_type,
            "image_count": len(slide.image_paths),
            "bullet_count": slide.bullet_count
        }
        frames_data.append(frame_dict)
    
    # 转换演讲稿数据
    for para in presentation.speech_paragraphs:
        para_dict = {
            "text": para.text,
            "word_count": para.word_count,
            "contains_question": "?" in para.text or "？" in para.text,
            "contains_data": any(word in para.text.lower() for word in ["数据", "统计", "结果", "%"])
        }
        paras_data.append(para_dict)
    
    return {
        "frames": frames_data,
        "paras": paras_data,
        "statistics": presentation.get_statistics(),
        "aligned": presentation.align_presentation()
    }

if __name__ == "__main__":
    try:
        print("🚀 启动演示文稿解析器")
        print(f"数据路径: {data_path}")
        print(f"输出目录: {output_dir}")
        
        # 检查路径是否存在
        if not os.path.exists(data_path):
            print(f"❌ 错误: 数据路径不存在: {data_path}")
            sys.exit(1)
            
        # 解析演示文稿
        presentation = parse_presentation(data_path, output_dir)
        
        print("\n" + "="*60)
        print("✅ 解析完成!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)