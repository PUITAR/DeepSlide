# test_camel.py
"""
测试 CAMEL-AI 的基本调用是否正确
"""

import os
from dotenv import load_dotenv
from camel.societies import RolePlaying
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.utils import print_text_animated
from colorama import Fore

# 加载环境变量
ENV_PATH = '/home/ym/DeepSlide/deepslide/config/env/.env'
load_dotenv(dotenv_path=ENV_PATH)

api_key = os.getenv('DEEPSEEK_API_KEY')
platform_type = os.getenv('DEFAULT_MODEL_PLATFORM_TYPE', 'deepseek')
model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')

print(f"API Key: {'Found' if api_key else 'NOT FOUND'}")
print(f"Platform Type: {platform_type}")
print(f"Model Type: {model_type}")

if not api_key:
    print("错误：未找到 DEEPSEEK_API_KEY")
    exit(1)

try:
    # 尝试创建模型实例
    model = ModelFactory.create(
        model_platform=ModelPlatformType(platform_type), # 使用小写
        model_type=model_type,
        api_key=api_key,
    )
    print("模型创建成功！")
except Exception as e:
    print(f"模型创建失败: {e}")
    exit(1)

# 简单的测试任务
task_prompt = "简单介绍一下机器学习是什么。"

try:
    print("\n开始 CAMEL-AI 角色扮演会话...")
    role_play_session = RolePlaying(
        assistant_role_name="机器学习专家",
        assistant_agent_kwargs=dict(model=model),
        user_role_name="好奇的用户",
        user_agent_kwargs=dict(model=model),
        task_prompt=task_prompt,
        with_task_specify=True,  # 先让模型细化任务
        task_specify_agent_kwargs=dict(model=model),
        output_language='中文'
    )

    print(
        Fore.GREEN
        + f"AI 助手系统消息:\n{role_play_session.assistant_sys_msg}\n"
    )
    print(
        Fore.BLUE + f"AI 用户系统消息:\n{role_play_session.user_sys_msg}\n"
    )

    print(Fore.YELLOW + f"原始任务提示:\n{task_prompt}\n")
    print(
        Fore.CYAN
        + "指定的任务提示:"
        + f"\n{role_play_session.specified_task_prompt}\n"
    )
    print(Fore.RED + f"最终任务提示:\n{role_play_session.task_prompt}\n")

    n = 0
    chat_turn_limit = 1  # 限制轮次，快速测试
    input_msg = role_play_session.init_chat()

    print("开始对话...")
    while n < chat_turn_limit:
        n += 1
        print(f"--- 轮次 {n} ---")
        assistant_response, user_response = role_play_session.step(input_msg)

        if assistant_response.terminated:
            print(
                Fore.RED
                + (
                    "AI 助手已终止。原因: "
                    f"{assistant_response.info['termination_reasons']}."
                )
            )
            break
        if user_response.terminated:
            print(
                Fore.RED
                + (
                    "AI 用户已终止。"
                    f"原因: {user_response.info['termination_reasons']}."
                )
            )
            break

        print_text_animated(
            Fore.BLUE + f"AI 用户:\n\n{user_response.msg.content}\n"
        )
        print_text_animated(
            Fore.GREEN + "AI 助手:\n\n"
            f"{assistant_response.msg.content}\n"
        )

        if "CAMEL_TASK_DONE" in user_response.msg.content:
            print("任务完成标记检测到，结束对话。")
            break

        input_msg = assistant_response.msg

    print("\nCAMEL-AI 测试完成。")

except Exception as e:
    print(f"CAMEL-AI 调用过程中出错: {e}")
    import traceback
    print(f"详细错误信息: {traceback.format_exc()}")