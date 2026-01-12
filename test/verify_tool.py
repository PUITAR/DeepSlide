from compiler_tools import CompilerTools
import os

# Create a dummy file with mismatch
base_dir = "/home/ym/DeepSlide/test_temp"
os.makedirs(base_dir, exist_ok=True)
with open(os.path.join(base_dir, "bad.tex"), "w") as f:
    f.write("\\begin{frame}\n\\item { Unclosed brace\n\\end{frame}")

ct = CompilerTools(base_dir)
print("Checking balance...")
res = ct.check_balance("bad.tex")
print(f"Result: {res}")

# Cleanup
import shutil
shutil.rmtree(base_dir)
