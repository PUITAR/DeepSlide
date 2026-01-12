import os
import sys
from modelscope.hub.snapshot_download import snapshot_download

log_file = "download_debug.log"

def log(msg):
    with open(log_file, "a") as f:
        f.write(msg + "\n")
    print(msg)

try:
    cache_dir = 'local_llm_server/models'
    log(f"Target dir: {cache_dir}")
    os.makedirs(cache_dir, exist_ok=True)
    
    model_id = 'damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch'
    log(f"Downloading {model_id}...")
    
    path = snapshot_download(model_id, cache_dir=cache_dir)
    log(f"Download success. Path: {path}")
    
    log("Directory listing:")
    for root, dirs, files in os.walk(cache_dir):
        log(f"{root}: {files}")
        
except Exception as e:
    log(f"Error: {e}")
    import traceback
    log(traceback.format_exc())
