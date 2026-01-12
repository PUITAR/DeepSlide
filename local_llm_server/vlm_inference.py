import os
import uvicorn
from fastapi import FastAPI, UploadFile, File, Form
from typing import Optional
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image
import io

# Setup for VLM (e.g., Qwen-VL-Chat or similar)
# This is a template for the VLM service.
# Ensure you have the model downloaded in 'models/Qwen-VL-Chat' or similar.

app = FastAPI(title="Local VLM Service")

MODEL_PATH = os.getenv("VLM_MODEL_PATH", "models/Qwen-VL-Chat") 
# Fallback to a small model or placeholder if not present
device = "cuda" if torch.cuda.is_available() else "cpu"

model = None
tokenizer = None

def load_model():
    global model, tokenizer
    if os.path.exists(MODEL_PATH):
        try:
            print(f"Loading VLM from {MODEL_PATH}...")
            tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, device_map="auto", trust_remote_code=True).eval()
            print("VLM Loaded.")
        except Exception as e:
            print(f"Error loading VLM: {e}")
    else:
        print(f"VLM Model path {MODEL_PATH} not found. Running in Mock Mode.")

@app.on_event("startup")
async def startup_event():
    load_model()

@app.post("/v1/vision/refine")
async def refine_slide(
    image: UploadFile = File(...),
    prompt: str = Form("Please refine the layout of this slide. It looks crowded."),
    current_latex: str = Form("")
):
    """
    Receives a slide image and current LaTeX, returns refined LaTeX or suggestions.
    """
    # Read image
    contents = await image.read()
    img = Image.open(io.BytesIO(contents)).convert("RGB")
    
    if model:
        # Real Inference
        # This syntax depends on the specific VLM (e.g. Qwen-VL)
        query = tokenizer.from_list_format([
            {'image': img},
            {'text': f"{prompt}\nCurrent LaTeX context (optional): {current_latex[:500]}..."}
        ])
        inputs = tokenizer(query, return_tensors='pt')
        inputs = inputs.to(model.device)
        pred = model.generate(**inputs)
        response = tokenizer.decode(pred.cpu()[0], skip_special_tokens=False)
        # Extract response
        # ... logic to parse response ...
        return {"refinement": response, "status": "processed"}
    else:
        # Mock Response
        return {
            "refinement": "Suggestion: The slide seems text-heavy. Consider splitting the 'Methods' section into two columns or moving the image to the right side. \n\nRefined LaTeX suggestion:\n```latex\n\\begin{frame}\n\\frametitle{Refined Slide}\n\\begin{columns}\n\\column{0.5\\textwidth}\nText...\n\\column{0.5\\textwidth}\nImage...\n\\end{columns}\n\\end{frame}\n```",
            "status": "mocked"
        }

if __name__ == "__main__":
    port = int(os.getenv("VLM_PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
