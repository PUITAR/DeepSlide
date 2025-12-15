# test_real_latex.py
"""
使用真实 LaTeX 文件测试解析器
"""

import json
import os
from latex_parser import LatexParser

# 指定你的测试文件路径
TEX_FILE_PATH = "/home/ym/DeepSlide/deepslide/agents/divider/test/2511.22582v1/MergeConstraintsSM.tex"
OUTPUT_JSON_PATH = "./result/parsed_sections.json"

def main():
    print(f"📂 读取 LaTeX 文件: {TEX_FILE_PATH}")

    with open(TEX_FILE_PATH, 'r', encoding='utf-8') as f:
        tex_content = f.read()

    
    # 解析
    print("\n🔍 开始解析 LaTeX 结构...")
    parser = LatexParser()
    try:
        sections = parser.extract_sections(tex_content)
        print(f"✅ 解析成功! 共找到 {len(sections)} 个章节")
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 打印摘要和前几个章节详情
    print("\n📊 解析结果摘要:")
    analysis = parser.analyze_document_structure(tex_content)
    print(f"  - 总章节数: {analysis['total_sections']}")
    print(f"  - 层级分布: {analysis['level_distribution']}")
    print(f"  - 是否有层次结构: {'是' if analysis['has_hierarchy'] else '否'}")
    
    print("\n📄 前 5 个章节预览:")
    for i, sec in enumerate(sections[:5]):
        title_display = (sec['title'][:50] + '...') if len(sec['title']) > 50 else sec['title']
        raw_title_display = (sec['title_raw'][:50] + '...') if len(sec['title_raw']) > 50 else sec['title_raw']
        content_preview = (sec['content'][:100].replace('\n', ' ') + '...') if len(sec['content']) > 100 else sec['content'].replace('\n', ' ')
        
        print(f"\n[{i+1}] Level {sec['level']}: '{title_display}'")
        print(f"    Raw Title: '{raw_title_display}'")
        print(f"    Position: [{sec['start_char']}, {sec['end_char']}] (长度: {sec['end_char'] - sec['start_char']})")
        print(f"    Content Preview: {content_preview}")
    
    if len(sections) > 5:
        print(f"\n... 还有 {len(sections) - 5} 个章节未显示")
    
    # 保存为 JSON（便于人工检查）
    try:
        serializable_sections = []
        for sec in sections:
            serializable_sections.append({
                'title': sec['title'],
                'title_raw': sec['title_raw'],
                'content': sec['content'],
                'level': sec['level'],
                'start_char': sec['start_char'],
                'end_char': sec['ends_char'],
                'command': sec['command']
            })
        
        with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(serializable_sections, f, indent=2, ensure_ascii=False)
        print(f"\n💾 解析结果已保存至: {os.path.abspath(OUTPUT_JSON_PATH)}")
    except Exception as e:
        print(f"⚠️  保存 JSON 失败: {e}")

if __name__ == "__main__":
    main()