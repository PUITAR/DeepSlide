from deepslide.utils import (
    Content,
    compile_content,
    replace_content,
    update_title,
    update_base,
)

from colorama import Fore

# from camel.societies import RolePlaying
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
# from camel.toolkits import OpenAIFunction
from camel.agents import ChatAgent

from dotenv import load_dotenv
import os

from pprint import pprint

# 正则表达式提取标签中的内容
# 1. <content></content>
# 2. <title></title>
import re

from typing import Any

CONFIG_DIR = os.path.join(os.path.dirname(__file__))

class Compiler:

    def __init__(self, config_dir: str = CONFIG_DIR, max_try: int = 3):

        self.config_dir = config_dir
        self.max_try = max_try

        # 读取 .env
        # env_path = os.path.join(config_dir, 'env', '.env')
        # load_dotenv(env_path)

        # tool list
        # TODO 后续考虑增加网络工具，从外部查询可能的解决方法
        tool_list = []

        # 初始化 LLM
        llm = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-chat",
            url='https://api.deepseek.com',
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            model_config_dict={
                "tools": tool_list,
                "temperature": 0.0,
            },
        )

        sys_msg = BaseMessage.make_assistant_message(
            role_name="Compiler Agent",
            content= open(
                # 'deepslide/config/prompts/sys_prompt_compiler.md',
                os.path.join(config_dir, 'prompts', 'sys_prompt_compiler.md'),
                'r',
                encoding='utf-8'
            ).read()
        )

        self.agent = ChatAgent(sys_msg, model=llm, tools=tool_list)

        self.usr_prompt = open(
            # 'deepslide/config/prompts/usr_prompt_compiler.md',
            os.path.join(config_dir, 'prompts', 'usr_prompt_compiler.md'),
            'r',
            encoding='utf-8'
        ).read()


    """
    Compile the LaTeX document in the `base_dir`.

    Compiling the project folder requires the following file structure:

    1. base.tex  
    - Type: File
    - Purpose: Global template style definition file.  
    - Forbidden: Writing main text directly here; arbitrarily deleting or modifying existing layout commands.  
    - Recommendation: If you need to adjust headers, footers, theme colors, or font sizes, do so here to keep the entire slide deck consistent.

    2. content.tex
    - Type: File
    - Purpose: The sole entry point for slide content.  
    - Forbidden: Piling up large blocks of formulas or figure code.  
    - Recommendation: Split logic by sections; keep each section to no more than 10 lines of main text.

    3. ref.bib  
    - Type: File
    - Purpose: Central bibliography data source.  
    - Forbidden: Fabricating reference entries; using non-standard BibTeX entry types.  
    - Recommendation: Add each new reference to this file immediately.

    4. picture/  
    - Type: Directory
    - Purpose: Root directory for all image assets.  
    - Forbidden: Placing images in the root or any other custom folder; using Chinese or special symbols in image filenames.  
    - Recommendation: Adjust images appropriately to ensure slide aesthetics after compilation.

    5. title.tex
    - Type: File
    - Purpose: Title slide content.  
    - Forbidden: Modifying title, author, or institute commands.  
    - Recommendation: Customize title, subtitle, author, and institute information here.
    
    Args:
        base_dir (str): The directory of the LaTeX document.

        helper (dict[str, Any], optional): The helper dictionary for the compiler to detect the error location. Defaults to None.
        {
            "file": "content",
            "line": ?,
            "idx": ?
        }
    
    Returns:
        dict: The result of the compilation.
    """
    def run(self, base_dir: str, helper: dict[str, Any] = None):
        """
        Compile -> Fail -> Fix -> Replace
        """
        for i in range(self.max_try):
            print(Fore.CYAN + f"\n[Try {i+1}] LaTeX compile..." + Fore.RESET)

            # 1. 直接调用工具进行编译
            result = compile_content(base_dir, helper=helper)

            # 2. 成功了就返回
            if result.get("success"):
                print(Fore.GREEN + "✅ Compile success" + Fore.RESET)
                return result

            # 3. 打印错误
            errors = result.get("errors", [])
            for _, e in enumerate(errors):
                print(
                    Fore.RED +
                    f"❌ Error: {e.get('message')} (file={e.get('file')}, line {e.get('line')}, idx={e.get('idx')})" +
                    Fore.RESET
                )

                error_file = e.get("file")
                # print(f"error_file: {error_file}")

                '''
                修复来自不同文件的错误
                1. title.tex 
                2. content.tex 
                3. base.tex
                '''

                # title.tex 错误
                if error_file == "title":
                    curr_title = open(os.path.join(base_dir, 'title.tex'), 'r', encoding='utf-8').read()
                    error_message = e.get('message')
                    user_msg = BaseMessage.make_user_message(
                        role_name="User",
                        content=self.usr_prompt.format(error_file, error_message, curr_title)
                    )

                    response = self.agent.step(user_msg)
                    correct_title = response.msg.content

                    match = re.search(r'<title>(.*?)</title>', correct_title, re.DOTALL)
                    if match:
                        correct_title = match.group(1).strip()
                    else:
                        break

                    # 替换错误标题
                    result = update_title(base_dir, correct_title)
                    if result:
                        print(
                            Fore.YELLOW + f"🔧 Fix: title\n" + Fore.RESET,
                            f"{correct_title}"
                        )

                    break

                elif error_file == "content":
                    # content.tex 错误
                    obj_idx = e.get('idx') or None

                    try:
                        content = Content()
                        content.from_file(os.path.join(base_dir, 'content.tex'))
                        snippet = content[obj_idx]
                    except Exception as e:
                        # print(Fore.RED + f"❌ {eidx}: {e}" + Fore.RESET)
                        continue

                    user_msg = BaseMessage.make_user_message(
                        role_name="User",
                        content=self.usr_prompt.format(error_file, e.get('message', ''), snippet)
                    )

                    response = self.agent.step(user_msg)

                    # pprint(response.content)
                    correct_content = response.msg.content
                    # get content from <content></content> wrapper
                    match = re.search(r'<content>(.*?)</content>', correct_content, re.DOTALL)
                    if match:
                        correct_content = match.group(1).strip()
                        # pprint(correct_content)
                    else:
                        break

                    # 4. 替换错误对象
                    result = replace_content(base_dir, obj_idx, correct_content)
                    if result:
                        print(
                            Fore.YELLOW + f"🔧 Fix: {obj_idx}-th object of content\n" + Fore.RESET,
                            f"{correct_content}"
                        )

                    # Fix an error every time
                    break

                elif error_file == "base":
                    # base.tex 错误
                    curr_base = open(os.path.join(base_dir, 'base.tex'), 'r', encoding='utf-8').read()
                    error_message = e.get('message')
                    user_msg = BaseMessage.make_user_message(
                        role_name="User",
                        content=self.usr_prompt.format(error_file, error_message, curr_base)
                    )

                    response = self.agent.step(user_msg)
                    correct_base = response.msg.content

                    # get base from <base></base> wrapper
                    match = re.search(r'<base>(.*?)</base>', correct_base, re.DOTALL)
                    if match:
                        correct_base = match.group(1).strip()
                    else:
                        break

                    # 替换错误base
                    result = update_base(base_dir, correct_base)
                    if result:
                        print(
                            Fore.YELLOW + f"🔧 Fix: base\n" + Fore.RESET,
                            f"{correct_base}"
                        )

                    break

        # 完成所有尝试后，再次编译
        result = compile_content(base_dir, helper=helper)

        if result.get("success"):
            print(Fore.GREEN + "✅ Compile success" + Fore.RESET)
        
        return result
