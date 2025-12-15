import os
import shutil
import sys

# project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    print(f'Add {ROOT} to sys.path')
    sys.path.insert(0, ROOT)

from deepslide.agents.templater import Templater
from deepslide.agents.compiler import Compiler

from colorama import Fore


if __name__ == "__main__":

    TEST_DIR = os.path.join(ROOT, "test", "test_templater")
    DEMO_DIR = os.path.join(TEST_DIR, "demo")

    if os.path.exists(DEMO_DIR):
        shutil.rmtree(DEMO_DIR)

    templater = Templater(
        config_dir=os.path.join(ROOT, "deepslide", "config"),
        embdding_dir=os.path.join(ROOT, "template", "embedding"),
        template_dir=os.path.join(ROOT, "template", "beamer"),
    )

    user_desc = "A clean academic beamer with compact navigation, numbered captions, and modern fonts."
    name = templater.select(user_desc, top_k=3)

    # print(f"Selected template: {name}")
    print(f"{Fore.GREEN}Selected template: {name}{Fore.RESET}")

    src = os.path.join(ROOT, "template", "beamer", name)

    try:
        shutil.copytree(src, DEMO_DIR)
    except Exception as e:
        print(f"{Fore.RED}Error copying template: {e}{Fore.RESET}")
        exit(1)

    templater.modify(
        DEMO_DIR, 
        '''
        Make the following modifications to the template:

        1. Unify all visual elements to ensure consistency in the style of images, illustrations, and icons, eliminating visual distractions.  
        2. Strategically increase white space (negative space) to highlight key content and enhance the overall professionalism and quality of the page.  
        3. Use high-contrast non-pure color backgrounds as the main theme, while employing highly saturated accent colors to emphasize data, optimizing both long-term viewing comfort and visual impact.
        '''
    )

    compiler = Compiler(config_dir=os.path.join(ROOT, "deepslide", "config"), max_try=3)
    result = compiler.run(DEMO_DIR, helper = {"file": "base"})

    print(result)