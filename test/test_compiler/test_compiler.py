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
from deepslide.utils import Content


if __name__ == '__main__':
    PATH_TO_CASE= os.path.join(ROOT, 'test', 'test_compiler')
    # CONFIG_DIR = os.path.join(ROOT, 'deepslide', 'config')
    
    CASES = [
        os.path.join(PATH_TO_CASE, 'case1'),
        os.path.join(PATH_TO_CASE, 'case2'),
        os.path.join(PATH_TO_CASE, 'case3'),
        os.path.join(PATH_TO_CASE, 'case4'),
    ]

    title_case = os.path.join(PATH_TO_CASE, 'case4')

    # for case in CASES:
    #     # os.makedirs(os.path.join(case, 'picture'), exist_ok=True)
    #     # rm base.pdf
    #     try:
    #         os.remove(os.path.join(case, 'base.pdf'))
    #     except Exception as e:
    #         print(f'no base.pdf: {e}')

    time.sleep(1)

    compiler = Compiler(max_try=1)

    for idx, case in enumerate(CASES):
        print('='*20)
        print(f'case {idx+1}: {case}')
        errornote = open(os.path.join(case, 'ERRORNOTE.txt')).read()
        print(errornote)
        print('='*20)

        print(case)

        # 复制包含错误的content
        try:
            dst_tex = os.path.join(case, 'content.tex')
            src_tex = os.path.join(case, 'content_error.tex')
            copyfile(src_tex, dst_tex)
        except Exception as e:
            print(f'no error on content: {e}')
            # continue

        # 复制包含错误的title
        try:
            dst_tex = os.path.join(case, 'title.tex')
            src_tex = os.path.join(case, 'title_error.tex')
            copyfile(src_tex, dst_tex)
        except Exception as e:
            print(f"no error on title: {e}")
            # continue
        
        if case == title_case:
            print(f"run title case: {case}")
            res = compiler.run(case, helper={
                "file": "title",
            })
        else:
            res = compiler.run(case)

        pprint(res)