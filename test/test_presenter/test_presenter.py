import os
import sys

# ==========================================
# 0. DeepSeek 模型配置 (核心配置)
# ==========================================
# 为了让 CAMEL 能够调用 DeepSeek，我们需要将 Base URL 指向 DeepSeek 的服务器
# 并且设置 ModelType 为兼容模式 (CAMEL 底层使用 OpenAI Client)

# ⚠️ 请将你的 DeepSeek API Key 填入环境变量，或者临时在这里设置
os.environ["OPENAI_API_KEY"] = "sk-6286dc11a31e45649dbf55081b8aef20" 
os.environ["OPENAI_API_BASE_URL"] = "https://api.deepseek.com" # DeepSeek 官方接口地址

# ==========================================
# 1. 路径环境设置
# ==========================================

# 当前脚本所在目录: /home/ym/DeepSlide/test/test_presenter
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录: /home/ym/DeepSlide
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))

# 加入系统路径
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

try:
    from deepslide.agents.presenter.presenterbase import PresenterAgent
except ImportError as e:
    print("\n❌ 导入失败: 无法找到 deepslide 模块。")
    print(f"请检查 PROJECT_ROOT 是否正确: {PROJECT_ROOT}")
    sys.exit(1)

# 定义文件路径
BASE_TEX_PATH = os.path.join(PROJECT_ROOT, "test/test_content/base.tex") # 指向你的 base.tex
CONTENT_TEX_PATH = os.path.join(PROJECT_ROOT, "test/test_content/content_test.tex")
OUTPUT_TXT_PATH = os.path.join(CURRENT_DIR, "webui/output_speech.txt")

def run_test():
    print("=" * 60)
    print("🎤 DeepSlide Presenter 测试 (含封面处理)")
    print("=" * 60)
    
    # 检查文件
    if not os.path.exists(BASE_TEX_PATH):
        print(f"❌ 错误: 找不到 base.tex -> {BASE_TEX_PATH}")
        return
    if not os.path.exists(CONTENT_TEX_PATH):
        print(f"❌ 错误: 找不到 content.tex -> {CONTENT_TEX_PATH}")
        return

    # 运行 Agent
    try:
        presenter = PresenterAgent()
        # 注意：现在需要传两个路径
        presenter.generate_script(BASE_TEX_PATH, CONTENT_TEX_PATH, OUTPUT_TXT_PATH)
    except Exception as e:
        print(f"❌ 运行异常: {e}")

    # 验证
    if os.path.exists(OUTPUT_TXT_PATH):
        with open(OUTPUT_TXT_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        print("\n=== 结果预览 ===")
        print(content[:500] + "...")
        print(f"\n📊 总长度: {len(content)}, <next> 数量: {content.count('<next>')}")

if __name__ == "__main__":
    run_test()