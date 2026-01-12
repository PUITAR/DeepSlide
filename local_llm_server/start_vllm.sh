#!/bin/bash
# Enable error handling
set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Define paths
VLLM_BIN="/home/ym/anaconda3/envs/deepslide/bin/vllm"
PYTHON_BIN="/home/ym/anaconda3/envs/deepslide/bin/python"
MODEL_PATH="$SCRIPT_DIR/models/Qwen/Qwen3-32B"

# Check if model exists
if [ ! -d "$MODEL_PATH" ]; then
    echo "Error: Model not found at $MODEL_PATH"
    echo "Please run 'python download_model.py' first to download the model."
    exit 1
fi

# Ports
PROXY_PORT=8181       # External port (Auth Proxy)
VLLM_PORT=8001        # Internal port (vLLM)
VLM_PORT=8002         # Internal port (VLM)
VLLM_API_URL="http://localhost:$VLLM_PORT"
VLM_API_URL="http://localhost:$VLM_PORT"

echo "Starting vLLM server (Internal)..."
echo "Model: $MODEL_PATH"
echo "Internal Port: $VLLM_PORT"
echo "Tensor Parallel Size: 2 (Using 2 GPUs)"

# Start vLLM in background on internal port
# No API key here, the proxy handles it.
$VLLM_BIN serve "$MODEL_PATH" \
    --host 127.0.0.1 \
    --port $VLLM_PORT \
    --served-model-name "Qwen3-32B" \
    --tensor-parallel-size 2 \
    --trust-remote-code \
    --gpu-memory-utilization 0.95 \
    --enable-auto-tool-choice \
    --tool-call-parser hermes &

VLLM_PID=$!
echo "vLLM started with PID $VLLM_PID"

echo "Starting VLM Service on port $VLM_PORT..."
export VLM_PORT=$VLM_PORT
$PYTHON_BIN vlm_inference.py > vlm.log 2>&1 &
VLM_PID=$!
echo "VLM Service started with PID $VLM_PID"

# Wait for vLLM to be ready
echo "Waiting for vLLM to initialize..."
# Simple loop to check if vLLM port is listening
while ! nc -z localhost $VLLM_PORT; do   
  sleep 5
  echo "Waiting for vLLM on port $VLLM_PORT..."
done
echo "vLLM is ready!"

echo "Starting Auth Proxy Server on port $PROXY_PORT..."
# Export env vars for server.py
export PROXY_PORT=$PROXY_PORT
export VLLM_API_URL=$VLLM_API_URL

# Start Proxy Server
$PYTHON_BIN server.py

# Cleanup on exit
trap "kill $VLLM_PID" EXIT
