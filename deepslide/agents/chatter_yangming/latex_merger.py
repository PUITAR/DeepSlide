import os
import re

# 定义匹配 \input 或 \include 命令的正则表达式
# 匹配 \input{...}, \include{...}, \input{ ... } 等
# 它捕获大括号内的文件名/路径

INPUT_REGEX = re.compile(r'\\(?:input|include)\s*\{([^}]+)\}')

def merge_latex_file(filepath, base_dir):
    """
    递归地读取并合并 LaTeX 文件内容。
    
    :param filepath: 当前要处理的 .tex 文件路径（相对于 base_dir）
    :param base_dir: 项目的根目录
    :return: 合并后的文件内容字符串
    """
    
    # 构造文件的完整系统路径
    full_path = os.path.join(base_dir, filepath)
    
    # 确保文件存在
    if not os.path.exists(full_path):
        print(f"⚠️ 警告: 文件未找到 - {full_path}")
        return f"\\input{{{filepath}}}" # 找不到就保留原命令
    
    # 读取文件内容
    with open(full_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 使用 sub 方法进行替换
    def replacer(match):
        # match.group(1) 是正则表达式捕获的大括号内的文件路径
        included_file_path = match.group(1)
        
        # 尝试修正相对路径：由于被包含的文件中的路径通常是相对于主文件的，
        # 我们在这里不需要做复杂的路径修正，因为 \input 总是相对于 base_dir（即主文件所在目录）。
        
        # 递归调用 merge_latex_file 来处理被包含文件中的 \input
        print(f"✅ On Merge: {included_file_path}")
        
        # 确保被包含的文件名有 .tex 后缀，如果没有则添加
        if not included_file_path.endswith('.tex'):
            included_file_path += '.tex'
            
        merged_content = merge_latex_file(included_file_path, base_dir)
        
        # 为了调试和结构清晰，可以在被包含内容前后添加注释
        comment_start = f"\n\n% --- START OF FILE: {included_file_path} ---\n"
        comment_end = f"\n% --- END OF FILE: {included_file_path} ---\n\n"
        
        return comment_start + merged_content + comment_end

    # 替换所有匹配到的 \input/\include 命令
    return INPUT_REGEX.sub(replacer, content)

# --- 使用方法 ---
# if __name__ == "__main__":
#     # 请根据您的项目配置修改以下三个变量
    
#     # 1. 您的项目根目录 (通常是包含主 .tex 文件的文件夹)
#     PROJECT_ROOT = '.' 
    
#     # 2. 您的主 .tex 文件名
#     MAIN_FILE_NAME = 'main.tex' 
    
#     # 3. 输出的新文件名
#     OUTPUT_FILE_NAME = 'output_merged.tex'
    
#     try:
#         print(f"🚀 开始合并项目: {MAIN_FILE_NAME}")
        
#         # 启动递归合并过程
#         merged_content = merge_latex_file(MAIN_FILE_NAME, PROJECT_ROOT)
        
#         # 写入结果文件
#         output_path = os.path.join(PROJECT_ROOT, OUTPUT_FILE_NAME)
#         with open(output_path, 'w', encoding='utf-8') as f:
#             f.write(merged_content)
            
#         print("-" * 30)
#         print(f"🎉 恭喜! 文件已成功合并到: {output_path}")
        
#     except Exception as e:
#         print(f"\n❌ 发生错误: {e}")