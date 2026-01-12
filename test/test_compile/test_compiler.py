import os
import sys

from shutil import copyfile

import time

# project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

if ROOT not in sys.path:
    print(f'Add {ROOT} to sys.path')
    sys.path.insert(0, ROOT)

from pprint import pprint

from deepslide.agents.compiler import Compiler
print(f"Compiler module path: {Compiler.__module__}")
import deepslide.agents.compiler.compiler as c_mod
print(f"Compiler file path: {c_mod.__file__}")
from deepslide.utils import Content


if __name__ == '__main__':
    # 获取当前脚本所在目录作为编译目标目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f'Compiling directory: {current_dir}')

    # 清理旧的 PDF 文件
    try:
        pdf_path = os.path.join(current_dir, 'base.pdf')
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
            print('Removed old base.pdf')
    except Exception as e:
        print(f'Error removing base.pdf: {e}')

    time.sleep(1)

    # 初始化编译器，增加重试次数以修复潜在错误
    compiler = Compiler(max_try=3)
    print(compiler)

    print('='*20)
    print(f'Start compilation for: {current_dir}')
    print('='*20)

    # 运行编译器
    res = compiler.run(current_dir)

    print('\nCompilation Result:')
    pprint(res)