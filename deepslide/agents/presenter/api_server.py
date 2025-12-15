from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
import sys
from dotenv import load_dotenv

# Ensure deepslide is importable
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(project_root)

from deepslide.agents.presenter.matrix_generator import MatrixGenerator
from deepslide.agents.presenter.relationship_explainer import RelationshipExplainer

app = FastAPI(title="Presenter Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage
sessions = {}

class GenerateRequest(BaseModel):
    nodes: List[str]

class MatrixUpdate(BaseModel):
    matrix: List[List[str]]

@app.post("/api/presenter/generate/{session_id}")
async def generate_matrix(session_id: str, request: Optional[GenerateRequest] = None):
    """
    Generate the logic connection matrix.
    If 'nodes' are provided in the body, uses them.
    Otherwise, falls back to a mock list (for testing/demo).
    """
    if request and request.nodes:
        nodes = request.nodes
    else:
        # Mock logic chain input for demo
        nodes = [
            "1. Introduction to Deep Learning",
            "2. Neural Network Basics",
            "3. Backpropagation Algorithm",
            "4. Applications in NLP",
            "5. Future Trends"
        ]
    
    try:
        # Load env for API keys
        from dotenv import load_dotenv
        env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
        load_dotenv(env_path)
        
        generator = MatrixGenerator()
        matrix = generator.generate_matrix(nodes)
    except Exception as e:
        print(f"Generation failed: {e}, using mock.")
        # Fallback Mock
        n = len(nodes)
        matrix = [["" for _ in range(n)] for _ in range(n)]
        # Add some sample connections if using the specific mock nodes
        if len(nodes) == 5 and "Introduction" in nodes[0]:
            matrix[0][1] = "Foundation" # Intro -> Basics
            matrix[1][2] = "Core Mechanism" # Basics -> Backprop

    sessions[session_id] = {
        "nodes": nodes,
        "matrix": matrix
    }
    return sessions[session_id]

@app.get("/api/presenter/session/{session_id}")
async def get_session(session_id: str):
    if session_id not in sessions:
        # Auto-generate for demo purposes if session not found
        # In a real flow, this might return 404
        return await generate_matrix(session_id, None)
    return sessions[session_id]

@app.post("/api/presenter/matrix/{session_id}/update")
async def update_matrix(session_id: str, update: MatrixUpdate):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    sessions[session_id]["matrix"] = update.matrix
    return {"status": "success", "matrix": update.matrix}

@app.post("/api/presenter/matrix/{session_id}/confirm")
async def confirm_matrix(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    nodes = sessions[session_id]["nodes"]
    matrix = sessions[session_id]["matrix"]
    edges = []
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i == j:
                continue
            val = matrix[i][j] if i < len(matrix) and j < len(matrix[i]) else ""
            if val:
                edges.append({
                    "from_index": i,
                    "to_index": j,
                    "from": nodes[i],
                    "to": nodes[j],
                    "reason": val
                })
    return {"nodes": nodes, "edges": edges}

@app.post("/api/presenter/matrix/{session_id}/explain")
async def explain_matrix(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    env_path = os.path.join(project_root, 'deepslide', 'config', 'env', '.env')
    load_dotenv(env_path)
    nodes = sessions[session_id]["nodes"]
    matrix = sessions[session_id]["matrix"]
    edges = []
    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i == j:
                continue
            val = matrix[i][j] if i < len(matrix) and j < len(matrix[i]) else ""
            if val:
                edges.append({
                    "from_index": i,
                    "to_index": j,
                    "from": nodes[i],
                    "to": nodes[j],
                    "reason": val
                })
    explainer = RelationshipExplainer()
    enriched = explainer.explain(nodes, edges)
    return {"nodes": nodes, "edges": enriched}

if __name__ == "__main__":
    print("Starting Presenter API on port 8002...")
    uvicorn.run(app, host="0.0.0.0", port=8002)
