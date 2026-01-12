import os
import sys
import shutil
import time
import subprocess

# Add root to path
# __file__ is /home/ym/DeepSlide/test/test_compiler.py
# Target is /home/ym/DeepSlide/deepslide/version-beamer-20260106
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../deepslide/version-beamer-20260106'))
if ROOT not in sys.path:
    sys.path.append(ROOT)

try:
    from compiler import Compiler
except ImportError:
    print(f"Failed to import compiler from {ROOT}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def run_setup():
    """Run the setup script to regenerate test cases."""
    setup_script = os.path.join(os.path.dirname(__file__), "setup_tests.py")
    subprocess.run(["python", setup_script], check=True)

def test_compiler_fix(test_name, dir_name):
    print(f"\n{'='*50}")
    print(f"Running Test: {test_name}")
    print(f"{'='*50}")
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "compiler_tests", dir_name))
    
    if not os.path.exists(base_dir):
        print(f"Error: Directory {base_dir} does not exist.")
        return

    # Double check clean state
    if os.path.exists(os.path.join(base_dir, "base.pdf")):
        os.remove(os.path.join(base_dir, "base.pdf"))

    # Reduce max_try to 2 for testing to fail faster
    compiler = Compiler(max_try=2)
    
    start_time = time.time()
    result = compiler.run(base_dir)
    end_time = time.time()
    
    print(f"\nResult: {result.get('success')}")
    print(f"Time Taken: {end_time - start_time:.2f} seconds")
    
    if result.get("success"):
        print("✅ PASS")
    else:
        print("❌ FAIL")
        # Print last few lines of log if available
        log_path = os.path.join(base_dir, "base.log")
        if os.path.exists(log_path):
            print("--- Log Tail ---")
            with open(log_path, 'r', errors='ignore') as f:
                print("".join(f.readlines()[-20:]))
        print("Errors:", result.get("errors"))

if __name__ == "__main__":
    # 1. Reset Environment
    print("Resetting test environment...")
    run_setup()
    
    # 2. Run Specific Tests to avoid timeout and focus on new features
    # We prioritize the new Agent tests.
    
    tests = [
        ("Fast Fix (&)", "test_ampersand"), # Can be slow if fast fix fails
        ("Fast Fix (\\captionof)", "test_undefined"),
        ("Fast Fix (Math Mode _)", "test_math_error"),
        ("Fast Fix (Fragile Verbatim)", "test_fragile"),
        ("Fast Fix (Missing Image)", "test_missing_image"),
        ("Fast Fix (Unicode Char)", "test_utf8_error"),
        ("Agent/Fast Fix (Missing Plot)", "test_plot_missing"),
        
        ("Agent (Mismatched Braces)", "test_mismatched_braces"),
        ("Agent (Tabular Mismatch)", "test_tabular_error"),
    ]
    
    for name, dirname in tests:
        test_compiler_fix(name, dirname)
