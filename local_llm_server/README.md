# Local LLM Server with Qwen3-32B

This directory provides a local deployment of the Qwen3-32B model using `vllm`, exposed via a secure authentication proxy compatible with the OpenAI API.

## Architecture

- **Auth Proxy**: Listens on port **8181**. Handles API Key verification.
- **vLLM Engine**: Listens on port **8001** (Internal). Handles model inference.

## Prerequisites

- NVIDIA GPU(s) with sufficient VRAM (at least 2x A6000 or equivalent for 32B model)
- Anaconda environment `deepslide`

## Setup

1. **Download the Model**:
   Run the download script to fetch Qwen3-32B from ModelScope:
   ```bash
   /home/ym/anaconda3/envs/deepslide/bin/python download_model.py
   ```
   The model will be saved to `./models/Qwen/Qwen3-32B`.

## Quick Management (Recommended)

Use the provided management script `manage_service.py` for easy operation.

```bash
cd /home/ym/DeepSlide/local_llm_server
./manage_service.py --help
```

### Common Commands

*   **Start Service**:
    ```bash
    ./manage_service.py start --detach
    ```
    This will start the API server in the background.

*   **Stop Service**:
    ```bash
    ./manage_service.py stop
    ```

*   **Check Status**:
    ```bash
    ./manage_service.py status
    ```

*   **API Key Management**:
    ```bash
    ./manage_service.py add-key "my-new-secret-key"
    ./manage_service.py rm-key "sk-user-001"
    ./manage_service.py list-keys
    ```

## Manual Service Management

### 1. Start the Service

Run the startup script directly:

```bash
chmod +x start_vllm.sh
./start_vllm.sh
```

**Startup Process:**
1. Starts `vllm` engine on internal port 8001.
2. Waits for the model to load and initialize.
3. Starts the Auth Proxy server on public port 8181.

*Note: The first launch may take a few minutes to load model weights into GPU memory.*

### 2. Stop the Service

If running in foreground, press `Ctrl+C`.
If running in background, use `./manage_service.py stop` or manually kill processes:

```bash
pkill -f vllm
pkill -f server.py
```

## How to Request the Service (API)

The service exposes an OpenAI-compatible API endpoint at `http://localhost:8181/v1`.

### Curl Example

```bash
curl http://localhost:8181/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer deepslide-project-key" \
  -d '{
    "model": "Qwen3-32B",
    "messages": [
      {"role": "user", "content": "Hello, who are you?"}
    ],
    "temperature": 0.7
  }'
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8181/v1",
    api_key="sk-user-001"  # Must match a key in api_keys.json
)

response = client.chat.completions.create(
    model="Qwen3-32B",
    messages=[
        {"role": "user", "content": "Explain quantum mechanics in one sentence."}
    ]
)

print(response.choices[0].message.content)
```

### Using with DeepSlide

Update your project's main `.env` configuration to use this local server:

```env
DEFAULT_MODEL_API_KEY=sk-user-001
DEFAULT_MODEL_PLATFORM_TYPE=openai
DEFAULT_MODEL_TYPE=Qwen3-32B
LLM_BASE_URL=http://localhost:8181/v1
```
