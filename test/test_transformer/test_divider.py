import os
import json
import logging

import sys

# project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    print(f'Add {ROOT} to sys.path')
    sys.path.insert(0, ROOT)

from deepslide.agents.transformer.divider import Divider

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Input file path
    input_path = "/home/ym/DeepSlide/test/test_divider/data/merged_main.tex"
    
    # Check if input file exists
    if not os.path.exists(input_path):
        logger.error(f"Input file not found: {input_path}")
        return

    # Initialize Divider
    logger.info("Initializing Divider...")
    divider = Divider()
    
    # Run divide
    logger.info(f"Processing {input_path}...")
    try:
        # Pass a schema if needed, or None
        result = divider.divide(input_path)
        
        # Output file path
        output_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(output_dir, "divider_result.json")
        
        # Save result
        logger.info(f"Saving result to {output_path}...")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            
        logger.info("Done!")
        
        # Visualize
        divider.visualize(result)
        
        # Calculate coverage
        divider.evaluate_coverage(result, input_path)
            
    except Exception as e:
        logger.exception(f"An error occurred during division: {e}")

if __name__ == "__main__":
    main()
