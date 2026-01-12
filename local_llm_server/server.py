import os
import json
import uvicorn
import httpx
from fastapi import FastAPI, Request, HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.responses import StreamingResponse
from typing import List

# Configuration
VLLM_API_URL = os.getenv("VLLM_API_URL", "http://localhost:8001")
API_KEYS_FILE = "api_keys.json"
PROXY_PORT = int(os.getenv("PROXY_PORT", "8000"))

app = FastAPI(title="Local LLM Auth Proxy")
security = HTTPBearer()

def load_api_keys() -> List[str]:
    """Load allowed API keys from a JSON file."""
    if not os.path.exists(API_KEYS_FILE):
        print(f"Warning: {API_KEYS_FILE} not found. No keys allowed.")
        return []
    try:
        with open(API_KEYS_FILE, "r") as f:
            data = json.load(f)
            return data.get("api_keys", [])
    except Exception as e:
        print(f"Error loading API keys: {e}")
        return []

ALLOWED_KEYS = load_api_keys()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    """Verify the Bearer token against the allowed list."""
    # Reload keys to support dynamic updates
    current_keys = load_api_keys()
    
    token = credentials.credentials
    if token not in current_keys:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token

@app.get("/health")
async def health_check():
    return {"status": "proxy_ok", "backend_url": VLLM_API_URL}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_request(request: Request, path: str, token: str = Depends(verify_api_key)):
    """
    Proxy all authenticated requests to the vLLM backend or VLM backend.
    """
    if path == "v1/vision/refine":
         url = f"{VLM_API_URL}/{path}"
    else:
         url = f"{VLLM_API_URL}/{path}"
    
    # Exclude headers that might confuse the backend or are hop-by-hop
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None) # Let httpx handle this
    
    # We might need to pass the internal API key to vLLM if vLLM is protected
    # But in our design, vLLM on 8001 is internal and unprotected (or we inject a master key)
    # If vLLM expects a key, we can inject it here.
    # For now, assuming vLLM on 8001 is run without --api-key or we just pass the user's key if vLLM accepts any.
    # Actually, the user's plan is to let THIS proxy handle auth.
    # So we can strip the Authorization header or replace it if vLLM needs one.
    # If vLLM is run with --api-key, we need to pass that specific key.
    # Let's assume vLLM on 8001 is NOT enforcing auth, so we don't need to forward the header
    # OR we forward it and vLLM ignores it if not configured.
    # To be safe, let's just forward everything (except host).
    
    # Update: If vLLM is started WITHOUT --api-key, it won't check.
    
    async def response_generator(response):
        async for chunk in response.aiter_bytes():
            yield chunk

    async with httpx.AsyncClient() as client:
        try:
            # Read body for non-GET requests
            content = await request.body() if request.method != "GET" else None
            
            req = client.build_request(
                request.method,
                url,
                headers=headers,
                content=content,
                timeout=None  # streaming can be long
            )
            
            r = await client.send(req, stream=True)
            
            return StreamingResponse(
                response_generator(r),
                status_code=r.status_code,
                headers=dict(r.headers)
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Backend connection error: {exc}")

if __name__ == "__main__":
    print(f"Starting proxy server on port {PROXY_PORT} -> {VLLM_API_URL}")
    print(f"Allowed API keys: {len(ALLOWED_KEYS)}")
    uvicorn.run(app, host="0.0.0.0", port=PROXY_PORT)
