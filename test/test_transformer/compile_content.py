import os
import sys
from shutil import copyfile
import time
from pprint import pprint

# project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

if ROOT not in sys.path:
    print(f'Add {ROOT} to sys.path')
    sys.path.insert(0, ROOT)

from deepslide.agents.compiler import Compiler

def main():
    # Define paths
    test_transformer_dir = os.path.join(ROOT, 'test', 'test_transformer')
    source_tex = os.path.join(test_transformer_dir, 'test_presentation.tex')
    base_dir = os.path.join(test_transformer_dir, 'base')
    dest_tex = os.path.join(base_dir, 'content.tex')

    # Check if source exists
    if not os.path.exists(source_tex):
        print(f"Source file not found: {source_tex}")
        return

    # Check if base directory exists
    if not os.path.exists(base_dir):
        print(f"Base directory not found: {base_dir}")
        return

    print(f"Copying content from {source_tex} to {dest_tex}...")
    try:
        copyfile(source_tex, dest_tex)
        print("Copy successful.")
    except Exception as e:
        print(f"Error copying file: {e}")
        return

    # Clean up previous pdf if exists
    base_pdf = os.path.join(base_dir, 'base.pdf')
    if os.path.exists(base_pdf):
        try:
            os.remove(base_pdf)
            print(f"Removed existing {base_pdf}")
        except Exception as e:
            print(f"Error removing base.pdf: {e}")

    # Initialize Compiler
    print("Initializing Compiler...")
    compiler = Compiler(max_try=3)

    # Run Compiler
    print(f"Running Compiler on {base_dir}...")
    res = compiler.run(base_dir, helper={'file': 'content'})

    print("="*20)
    print("Compilation Result:")
    pprint(res)
    print("="*20)

    if res.get('success'):
        print(f"Compilation successful! PDF generated at {os.path.join(base_dir, 'base.pdf')}")
    else:
        print("Compilation failed.")

if __name__ == '__main__':
    main()
