from modelscope import snapshot_download
import os

# Define local model directory
base_dir = os.path.dirname(os.path.abspath(__file__))
model_root = os.path.join(base_dir, "models")
os.makedirs(model_root, exist_ok=True)

print(f"Downloading Qwen/Qwen3-32B to {model_root}...")
try:
    model_path = snapshot_download('Qwen/Qwen3-32B', cache_dir=model_root)
    print(f"Model downloaded successfully to: {model_path}")
except Exception as e:
    print(f"Error downloading model: {e}")
