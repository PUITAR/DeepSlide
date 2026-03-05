import os
import logging
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router

_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
if os.path.exists(_env_path):
    load_dotenv(_env_path)

class _NoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "additionalProperties" in msg and "'type': 'object'" in msg:
            return False
        if "'type': 'function'" in msg and "'parameters'" in msg:
            return False
        if '"type": "function"' in msg and '"parameters"' in msg:
            return False
        return True


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
for h in root_logger.handlers:
    h.addFilter(_NoiseFilter())

for noisy in ["openai", "httpx", "camel", "camel_ai", "uvicorn.access"]:
    logging.getLogger(noisy).setLevel(logging.WARNING)

app = FastAPI(title=settings.PROJECT_NAME)

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Welcome to DeepSlide API"}

@app.get("/health")
def health_check():
    return {"status": "ok"}
