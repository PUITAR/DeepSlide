
import os
import json
import logging
from deepslide.agents.transformer.divider import Divider

# Setup logging
logging.basicConfig(level=logging.INFO)

def main():
    json_path = "/home/ym/DeepSlide/test/test_divider/divider_result.json"
    
    if not os.path.exists(json_path):
        print(f"Error: File not found at {json_path}")
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        print(f"Tree Visualization for {json_path}:")
        
        # Use Divider's visualize method
        # Since visualize is an instance method but doesn't use self state other than helper, 
        # we need an instance.
        divider = Divider()
        divider.visualize(data)
        
    except json.JSONDecodeError:
        print("Error: Failed to decode JSON")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
