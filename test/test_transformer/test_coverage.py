
import os
import logging
from deepslide.agents.transformer.divider import Divider

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_coverage():
    file_path = "/home/ym/DeepSlide/test/test_divider/data/merged_main.tex"
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print("Running Divider coverage test...")
    divider = Divider()
    result = divider.divide(file_path)
    
    divider.evaluate_coverage(result, file_path)

if __name__ == "__main__":
    test_coverage()
