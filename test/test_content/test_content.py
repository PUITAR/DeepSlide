import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from deepslide.utils import Content
from pprint import pprint

if __name__ == '__main__':
    tex_path = os.path.join(ROOT, "template/base/content.tex")
    
    c = Content()
    c.from_file(tex_path)

    assert len(c) > 0
    assert c.is_valid()

    pprint(c)

    c.to_file('content_test.tex')

    # 检查编译是否
    os.system(
        "cd " + os.path.dirname(__file__) + " && "
        "pdflatex -output-directory . base.tex content_test.tex"
    )

    # 检查生成的 PDF 是否存在
    assert os.path.exists(
        os.path.join(os.path.dirname(__file__), 'base.pdf'))

    suffix = [
        '.aux',
        '.log',
        '.nav',
        '.out',
        '.snm',
        '.toc',
    ]

    for s in suffix:
        p = os.path.join(os.path.dirname(__file__), 'base' + s)
        if os.path.exists(p):
            os.remove(p)

    print("PDF generated successfully.")
