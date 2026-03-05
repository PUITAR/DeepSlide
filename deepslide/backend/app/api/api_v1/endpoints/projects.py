from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
import json
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import shutil
import re
import logging
import traceback

from app.services.project_analyzer_service import project_analyzer
from app.services.requirements_service import requirements_service
from app.services.editor_service import editor_service
from app.services.core.ppt_core import _strip_latex_inline
from app.services.core.logic_chain_budget import (
    allocate_minutes_from_ratios,
    enforce_max_nodes,
    parse_total_minutes,
    target_node_range,
)

router = APIRouter()
logger = logging.getLogger(__name__)

class ProjectCreate(BaseModel):
    name: str

class Project(BaseModel):
    project_id: str
    name: str
    created_at: str
    path: str
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    requirements: Optional[Dict[str, Any]] = None
    is_confirmed: bool = False
    analysis: Optional[Dict[str, Any]] = None
    voice_prompt_path: Optional[str] = None
    selected_voice_path: Optional[str] = None

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    history: List[Dict[str, str]]
    is_confirmed: bool
    requirements: Dict[str, Any]
    generated_chain: Optional[Dict[str, Any]] = None
    logic_chain_candidates: Optional[List[Dict[str, Any]]] = None

class NodesUpdateRequest(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: Optional[List[Dict[str, Any]]] = None


class VoiceSelectRequest(BaseModel):
    selected_voice_path: str

# Mock database
projects_db = []

_PROJECT_INDEX_FILENAME = "project.json"

def _project_index_path(project_path: str) -> str:
    return os.path.join(str(project_path or ""), _PROJECT_INDEX_FILENAME)

def _atomic_write_json(path: str, data: Dict[str, Any]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _save_project_record(p: Dict[str, Any]):
    try:
        if not isinstance(p, dict):
            return
        project_path = p.get("path")
        if not project_path:
            return
        payload = {
            "project_id": p.get("project_id"),
            "name": p.get("name"),
            "created_at": p.get("created_at"),
            "path": p.get("path"),
            "nodes": p.get("nodes") or [],
            "edges": p.get("edges") or [],
            "requirements": p.get("requirements") or {},
            "is_confirmed": bool(p.get("is_confirmed", False)),
            "analysis": p.get("analysis"),
            "voice_prompt_path": p.get("voice_prompt_path"),
            "selected_voice_path": p.get("selected_voice_path"),
        }
        _atomic_write_json(_project_index_path(str(project_path)), payload)
    except Exception:
        return

def _load_project_record(project_id: str, project_path: str) -> Optional[Dict[str, Any]]:
    try:
        idx = _project_index_path(project_path)
        if os.path.exists(idx):
            with open(idx, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        else:
            created_at = datetime.fromtimestamp(os.path.getmtime(project_path)).isoformat()
            data = {
                "project_id": project_id,
                "name": project_id,
                "created_at": created_at,
                "path": project_path,
                "nodes": [],
                "edges": [],
                "analysis": {"recovered": True},
                "requirements": {},
                "is_confirmed": False,
            }
        data["project_id"] = project_id
        data["path"] = project_path
        if "created_at" not in data or not data["created_at"]:
            data["created_at"] = datetime.fromtimestamp(os.path.getmtime(project_path)).isoformat()
        if "name" not in data or not str(data["name"] or "").strip():
            data["name"] = project_id
        if "nodes" not in data or not isinstance(data.get("nodes"), list):
            data["nodes"] = []
        if "edges" not in data or not isinstance(data.get("edges"), list):
            data["edges"] = []
        if "requirements" not in data or not isinstance(data.get("requirements"), dict):
            data["requirements"] = {}
        if "is_confirmed" not in data:
            data["is_confirmed"] = False
        return data
    except Exception:
        return None

def _load_existing_projects():
    try:
        root = str(getattr(project_analyzer, "projects_dir", "") or "")
        if not root or not os.path.isdir(root):
            return
        for name in os.listdir(root):
            if not re.fullmatch(r"[0-9a-fA-F-]{32,36}", str(name or "")):
                continue
            project_path = os.path.join(root, name)
            if not os.path.isdir(project_path):
                continue
            if any(p.get("project_id") == name for p in projects_db if isinstance(p, dict)):
                continue
            rec = _load_project_record(name, project_path)
            if rec:
                projects_db.append(rec)
    except Exception:
        return

_load_existing_projects()

def get_project(project_id: str):
    for p in projects_db:
        if p["project_id"] == project_id:
            return p
    try:
        project_path = os.path.join(project_analyzer.projects_dir, str(project_id))
        if os.path.isdir(project_path):
            rec = _load_project_record(str(project_id), project_path)
            if rec:
                projects_db.append(rec)
                return rec
    except Exception:
        pass


def _safe_read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read() or ""
    except Exception:
        return ""


def _strip_latex_title(text: str) -> str:
    if not text:
        return ""
    t = str(text)
    t = re.sub(r"%.*$", "", t, flags=re.MULTILINE)
    t = t.replace("~", " ")
    t = re.sub(r"\$([^$]+)\$", r"\1", t)

    for _ in range(6):
        t2 = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([\s\S]*?)\}", r"\1", t)
        if t2 == t:
            break
        t = t2

    t = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", t)
    t = (
        t.replace("\\&", "&")
        .replace("\\%", "%")
        .replace("\\#", "#")
        .replace("\\_", "_")
        .replace("\\{", "{")
        .replace("\\}", "}")
    )
    t = t.replace("{", "").replace("}", "")
    return " ".join(t.split()).strip()


def _extract_latex_title(tex: str) -> Optional[str]:
    raw = str(tex or "")
    raw = re.sub(r"%.*$", "", raw, flags=re.MULTILINE)

    m = re.search(r"\\title\s*(?:\[[^\]]*\])?\s*\{", raw)
    if not m:
        return None

    start = m.end()
    depth = 1
    i = start
    end = None
    while i < len(raw):
        ch = raw[i]
        if ch == "\\" and i + 1 < len(raw) and raw[i + 1] in "{}":
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1

    candidate = raw[start:end].strip() if end is not None else raw[start:].strip()
    if not candidate:
        return None
    plain = _strip_latex_title(candidate)
    if plain:
        return plain
    plain2 = _strip_latex_inline(candidate)
    return plain2 if plain2 else None

@router.get("/", response_model=List[Project])
async def read_projects():
    return projects_db

@router.post("/", response_model=Project)
async def create_project(project: ProjectCreate):
    project_id = str(uuid.uuid4())

    project_path = os.path.join(project_analyzer.projects_dir, project_id)
    os.makedirs(project_path, exist_ok=True)

    new_project = {
        "project_id": project_id,
        "name": project.name,
        "created_at": datetime.now().isoformat(),
        "path": project_path,
        "nodes": [],
        "edges": [],
        "requirements": {},
        "is_confirmed": False
    }
    projects_db.append(new_project)
    _save_project_record(new_project)
    return new_project

@router.post("/upload", response_model=Project)
async def create_project_with_upload(
    name: str = Form(...),
    file: UploadFile = File(...)
):
    logger.info(f"[upload] start name={name!r} filename={file.filename!r}")
    project_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    try:
        # 1. Save uploaded file
        file_path = await project_analyzer.save_upload_file(file)

        # 2. Extract archive OR materialize single-file upload into project dir
        project_path = project_analyzer.materialize_upload(file_path, project_id, original_filename=file.filename or "upload")

        # 3. Find source file
        source_path, source_type = project_analyzer.find_source_file(project_path)
        if not source_path:
            raise HTTPException(status_code=400, detail="No valid source file (tex/md/docx/pptx) found in the uploaded file.")

        # 4. Analyze project
        analysis_result = project_analyzer.analyze_project(project_path, source_path, source_type)
        merged_content = analysis_result.get("merged_content", "")
        detected_title = _extract_latex_title(merged_content)
        effective_name = detected_title or name

        # Extract Abstract (Simple Regex)
        abstract = ""
        match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', merged_content, re.DOTALL)
        if match:
            abstract = match.group(1).strip()

        analysis_result["abstract"] = abstract
        if detected_title:
            analysis_result["material_title"] = detected_title

        # 5. Init Requirements Service (Pass nodes for AI)
        nodes = analysis_result.get("nodes", [])
        requirements_service.init_project(project_id, file.filename, abstract, nodes)

        new_project = {
            "project_id": project_id,
            "name": effective_name,
            "created_at": created_at,
            "path": project_path,
            "nodes": nodes,
            "edges": [],
            "analysis": analysis_result,
            "requirements": {},
            "is_confirmed": False
        }
        projects_db.append(new_project)
        _save_project_record(new_project)

        logger.info(f"[upload] done project_id={project_id} path={project_path!r} source_type={source_type!r} source_path={source_path!r}")
        return new_project
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[upload] failed project_id={project_id} err={e}")
        logger.error(traceback.format_exc()[:4000])
        raise HTTPException(status_code=500, detail=str(e))


def _normalize_single_root_dir(extract_path: str) -> str:
    try:
        items = [p for p in os.listdir(extract_path) if p not in {"__MACOSX"}]

        if "recipe" in items and os.path.isdir(os.path.join(extract_path, "recipe")):
            return extract_path

        if len(items) == 1:
            only = os.path.join(extract_path, items[0])
            if os.path.isdir(only):
                if os.path.isdir(os.path.join(only, "recipe")):
                    return only
                if os.path.exists(os.path.join(only, "base.pdf")):
                    return only
                if os.path.exists(os.path.join(only, "recipe", "base.pdf")):
                    return only
    except Exception:
        pass
    return extract_path


@router.post("/upload_package", response_model=Project)
async def upload_presentation_package(
    name: str = Form(...),
    file: UploadFile = File(...),
):
    logger.info(f"[upload_package] start name={name!r} filename={file.filename!r}")
    project_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    file_path = await project_analyzer.save_upload_file(file)
    try:
        extract_path = project_analyzer.extract_file(file_path, project_id)
    except Exception as e:
         raise HTTPException(status_code=400, detail=f"Failed to extract package: {e}")

    project_path = _normalize_single_root_dir(extract_path)

    recipe_dir = os.path.join(project_path, "recipe")
    pdf_path = os.path.join(recipe_dir, "base.pdf")
    title_tex_path = os.path.join(recipe_dir, "title.tex")
    if not os.path.exists(title_tex_path):
        title_tex_path = os.path.join(project_path, "title.tex")
    detected_title = _extract_latex_title(_safe_read_text(title_tex_path)) if os.path.exists(title_tex_path) else None
    effective_name = detected_title or name

    pages = []
    if os.path.exists(pdf_path):
        try:
            pages = editor_service.get_preview_pages(project_path)
        except Exception as e:
            logger.warning(f"[upload_package] preview generation failed: {e}")

    new_project = {
        "project_id": project_id,
        "name": effective_name,
        "created_at": created_at,
        "path": project_path,
        "nodes": [],
        "edges": [],
        "analysis": {"package": True, "preview_pages": len(pages)},
        "requirements": {},
        "is_confirmed": True,
    }
    projects_db.append(new_project)
    _save_project_record(new_project)
    logger.info(f"[upload_package] done project_id={project_id} path={project_path!r} pdf_exists={os.path.exists(pdf_path)} pages={len(pages)}")
    return new_project

@router.get("/{project_id}", response_model=Project)
async def read_project(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p

@router.post("/{project_id}/chat", response_model=ChatResponse)
async def chat_requirements(project_id: str, req: ChatRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    logger.info(f"[requirements] project_id={project_id} input_len={len(req.message or '')}")

    collector = requirements_service.get_collector(project_id)

    def _transform_chain(chain: Dict[str, Any]) -> Dict[str, Any]:
        total_min = parse_total_minutes(collector.conversation_requirements.get("duration", "10min"), default=10)
        min_nodes, max_nodes = target_node_range(total_min)
        max_nodes = min(int(max_nodes), int(total_min))
        min_nodes = min(int(min_nodes), int(max_nodes))

        def _clip_title(t: str) -> str:
            toks = re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+", str(t or "").strip())
            return (" ".join(toks[:10]) if toks else str(t or "").strip()).strip()

        raw_nodes = (chain or {}).get("nodes", []) or []
        nodes = enforce_max_nodes(raw_nodes, max_nodes=max_nodes)
        try:
            minutes = allocate_minutes_from_ratios(nodes, total_minutes=total_min)
        except Exception:
            k = len(nodes) or 1
            base = int(total_min) // int(k)
            rem = int(total_min) % int(k)
            minutes = [base + (1 if i < rem else 0) for i in range(k)]

        new_nodes = []
        for i, node in enumerate(nodes):
            node_min = int(minutes[i]) if i < len(minutes) else 1
            new_nodes.append(
                {
                    "node_id": f"chain-node-{i}",
                    "title": _clip_title(node.get("text", node.get("role", "Section"))),
                    "summary": node.get("description", ""),
                    "content": node.get("description", ""),
                    "node_type": "section",
                    "duration": f"{node_min}min",
                    "metadata": node,
                }
            )

        new_edges = []
        for i in range(len(new_nodes) - 1):
            new_edges.append(
                {
                    "from": new_nodes[i]["node_id"],
                    "to": new_nodes[i + 1]["node_id"],
                    "reason": None,
                    "type": "sequential",
                }
            )
        return {"nodes": new_nodes, "edges": new_edges}

    logic_chain_candidates = None

    if collector.is_confirmed:
        collector.conversation_history.append({"role": "user", "content": str(req.message or "").strip()})
        response = "I can regenerate logic-chain candidates based on your feedback. I’m generating candidates now—please pick one to proceed to the Logic Chain stage."
        collector.conversation_history.append({"role": "assistant", "content": response})
    else:
        response = collector.process_input(req.message)
    
    # Update project state
    p["is_confirmed"] = collector.is_confirmed
    p["requirements"] = collector.conversation_requirements
    
    generated_chain = None
    if collector.is_confirmed:
        try:
            from app.services.core.chain_ai_generator import generate_chain_via_tools
            from app.services.core.content_tree_builder import make_tree_tools
            from app.services.core.lgcc_templates import load_lgcc_templates
            from app.services.core.template_recommender import select_templates_via_llm

            tools = make_tree_tools(getattr(collector, "nodes", []) or [])
            reqs = collector.conversation_requirements

            all_ids, templates = load_lgcc_templates()
            chosen = []
            try:
                chosen = select_templates_via_llm(
                    all_template_ids=all_ids,
                    abstract_text=collector.paper_info.get("abstract", ""),
                    conversation_history=collector.conversation_history,
                )
            except Exception as e:
                logger.warning(f"[requirements] template selection failed: {e}")
                chosen = []
            if not chosen:
                chosen = list(all_ids or [])[:4]
            if not chosen:
                chosen = ["default"]

            chains_by_id = {}
            for tid in chosen:
                tpl = templates.get(tid)
                extra = ""
                try:
                    extra = tpl.prompt_block()
                except Exception:
                    extra = ""
                if str(tid) == "default":
                    chain = generate_chain_via_tools(
                        tools=tools,
                        focus_sections=reqs.get("focus_sections", []),
                        duration_text=reqs.get("duration", "10min"),
                        abstract_text=collector.paper_info.get("abstract", ""),
                        conversation_history=collector.conversation_history,
                    )
                else:
                    chain = generate_chain_via_tools(
                        tools=tools,
                        focus_sections=reqs.get("focus_sections", []),
                        duration_text=reqs.get("duration", "10min"),
                        abstract_text=collector.paper_info.get("abstract", ""),
                        conversation_history=collector.conversation_history,
                        variant=str(tid),
                        extra_guidance=(
                            "Use the following narrative template. Roles must come from the template roles list when possible. "
                            "Keep each node text concise (<= 10 words).\n\n" + str(extra)
                        ),
                    )
                if chain:
                    chains_by_id[tid] = chain
            
        except Exception as e:
            logger.warning(f"[requirements] chain generation failed: {e}")
            chains_by_id = {}

        if not chains_by_id:
            try:
                focus = reqs.get("focus_sections", []) if isinstance(reqs, dict) else []
                focus = [str(x).strip() for x in (focus or []) if str(x).strip()]
                if not focus:
                    focus = [str(n.title).strip() for n in (getattr(collector, "nodes", []) or []) if str(getattr(n, "title", "")).strip()]
                focus = focus[:4]
                if focus:
                    nodes = [{"text": t, "description": ""} for t in focus]
                    chains_by_id = {"fallback": {"nodes": nodes}}
                    logger.warning("[requirements] using fallback logic-chain candidates (no LLM chain) ")
            except Exception as e:
                logger.warning(f"[requirements] fallback chain build failed: {e}")

        candidates = []
        store_map = {}
        try:
            _, templates = load_lgcc_templates()
        except Exception:
            templates = {}

        for i, tid in enumerate(list(chains_by_id.keys())[:4]):
            chain = chains_by_id.get(tid)
            if not chain:
                continue
            store_map[str(tid)] = chain
            cand = _transform_chain(chain)
            title = f"Recommendation {i + 1} · {str(tid)}"
            reason = "Recommended narrative structure based on your requirements and the paper abstract."
            try:
                tpl = templates.get(tid)
                if tpl is not None:
                    title = f"Recommendation {i + 1} · {str(tid)}"
            except Exception:
                pass
            if str(tid) == "fallback":
                title = f"Recommendation {i + 1} · fallback"
                reason = "Fallback chain from focus sections (LLM chain unavailable)."
            candidates.append({"candidate_id": str(tid), "title": title, "reason": reason, **cand})

        if candidates:
            p["logic_chain_candidates"] = store_map
            logic_chain_candidates = candidates

    return {
        "response": response,
        "history": collector.conversation_history,
        "is_confirmed": collector.is_confirmed,
        "requirements": collector.conversation_requirements,
        "generated_chain": generated_chain,
        "logic_chain_candidates": logic_chain_candidates,
    }


class SelectLogicChainRequest(BaseModel):
    candidate_id: str


@router.post("/{project_id}/logicchain/select", response_model=Project)
async def select_logic_chain(project_id: str, req: SelectLogicChainRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    cid = str(req.candidate_id or "")
    stored = (p.get("logic_chain_candidates") or {})
    chain = stored.get(cid)
    if not chain:
        raise HTTPException(status_code=400, detail="Candidate not found")

    collector = requirements_service.get_collector(project_id)

    total_min = parse_total_minutes(collector.conversation_requirements.get("duration", "10min"), default=10)
    min_nodes, max_nodes = target_node_range(total_min)
    max_nodes = min(int(max_nodes), int(total_min))
    min_nodes = min(int(min_nodes), int(max_nodes))

    raw_nodes = chain.get("nodes", []) or []
    nodes = enforce_max_nodes(raw_nodes, max_nodes=max_nodes)
    try:
        minutes = allocate_minutes_from_ratios(nodes, total_minutes=total_min)
    except Exception:
        k = len(nodes) or 1
        base = int(total_min) // int(k)
        rem = int(total_min) % int(k)
        minutes = [base + (1 if i < rem else 0) for i in range(k)]

    new_nodes = []
    for i, node in enumerate(nodes):
        node_min = int(minutes[i]) if i < len(minutes) else 1
        new_nodes.append(
            {
                "node_id": f"chain-node-{i}",
                "title": node.get("text", node.get("role", "Section")),
                "summary": node.get("description", ""),
                "content": node.get("description", ""),
                "node_type": "section",
                "duration": f"{node_min}min",
                "metadata": node,
            }
        )

    new_edges = []
    for i in range(len(new_nodes) - 1):
        new_edges.append(
            {
                "from": new_nodes[i]["node_id"],
                "to": new_nodes[i + 1]["node_id"],
                "reason": None,
                "type": "sequential",
            }
        )

    p["nodes"] = new_nodes
    p["edges"] = new_edges
    p["logic_chain_candidates"] = None
    return p

@router.get("/{project_id}/chat/history")
async def get_chat_history(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    collector = requirements_service.get_collector(project_id)
    return {"history": collector.conversation_history}

from app.services.editor_ai_service import editor_ai_service

class RecommendEdgesRequest(BaseModel):
    node_names: List[str]

@router.post("/{project_id}/logic/recommend", response_model=List[Dict[str, Any]])
async def recommend_edges(project_id: str, req: RecommendEdgesRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get abstract from analysis
    abstract = ""
    if p.get("analysis"):
        abstract = p["analysis"].get("abstract", "")
    
    edges = editor_ai_service.recommend_edges(req.node_names, abstract)
    return edges

@router.post("/{project_id}/nodes")
async def update_nodes(project_id: str, req: NodesUpdateRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    logger.info(f"[logic] save project_id={project_id} nodes={len(req.nodes)} edges={len(req.edges or [])}")
    
    p["nodes"] = req.nodes
    if req.edges is not None:
        p["edges"] = req.edges
        
    # Assuming this confirms the logic chain phase
    return {"success": True, "nodes": p["nodes"], "edges": p.get("edges", [])}


@router.post("/{project_id}/voice/select")
async def select_voice(project_id: str, req: VoiceSelectRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    p["selected_voice_path"] = req.selected_voice_path
    logger.info(f"[voice] select project_id={project_id} selected={req.selected_voice_path!r}")
    return {"success": True, "selected_voice_path": p.get("selected_voice_path")}
