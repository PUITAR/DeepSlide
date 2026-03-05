from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import os
import logging
import json
import re
import html
import mimetypes
import urllib.parse
import threading
import time
import traceback

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

from app.services.editor_service import editor_service
from app.services.requirements_service import requirements_service
from .projects import get_project
import importlib
from .editor_utils import _safe_int_from_filename, _zip_dir, _zip_paths
from .editor_pptx import _build_pptx_from_images, _build_pptx_from_pdf_editable, _build_pptx_from_tex
from .editor_html_repair import patch_html_doc_for_repair
from app.services.html_render_service import HtmlRenderOptions, render_html_slide_to_png_async

router = APIRouter()
logger = logging.getLogger(__name__)

_GEN_LOCK = threading.Lock()
_GEN_STATE: Dict[str, Dict[str, Any]] = {}

_HTML_GEN_LOCK = threading.Lock()
_HTML_GEN_STATE: Dict[str, Dict[str, Any]] = {}

_HTML_REPAIR_LOCK = threading.Lock()
_HTML_REPAIR_STATE: Dict[str, Dict[str, Any]] = {}

class EditorFilesResponse(BaseModel):
    files: Dict[str, str]

class SaveFilesRequest(BaseModel):
    updates: Dict[str, str]

class CommandRequest(BaseModel):
    command: str
    page_index: int


class BeautifyRequest(BaseModel):
    rounds: int = 1


class HtmlGenerateRequest(BaseModel):
    focus_pages: List[int] = []
    effects: List[str] = []
    per_slide_max_regions: int = 3
    effects_by_page: Dict[int, List[str]] = {}
    per_slide_max_regions_by_page: Dict[int, int] = {}
    visual_fx: bool = False
    visual_fx_intensity: str = "low"
    visual_fx_by_page: Dict[int, str] = {}
    visual_fx_enabled: Dict[str, bool] = {}


class EnrichReferenceGraphRequest(BaseModel):
    max_refs_per_slide: int = 3

@router.get("/{project_id}/files", response_model=EditorFilesResponse)
async def get_editor_files(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    
    files = editor_service.get_editor_files(p["path"])
    return {"files": files}

@router.post("/{project_id}/save")
async def save_editor_files(project_id: str, req: SaveFilesRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
        
    success = editor_service.save_editor_files(p["path"], req.updates)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save files")
    return {"success": True}

@router.post("/{project_id}/compile")
async def compile_project(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
        
    logger.info(f"[compile] start project_id={project_id}")
    result = editor_service.compile(p["path"])
    try:
        if result.get("success"):
            alignment = editor_service.verify_pdf_content_alignment(p["path"]) if hasattr(editor_service, "verify_pdf_content_alignment") else None
            if alignment and alignment.get("success"):
                recipe_dir = os.path.join(p["path"], "recipe")
                try:
                    with open(os.path.join(recipe_dir, "alignment.json"), "w", encoding="utf-8") as f:
                        json.dump(alignment, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                result["alignment"] = alignment
    except Exception:
        pass
    logger.info(f"[compile] done project_id={project_id} success={bool(result.get('success'))} errors={len(result.get('errors') or [])}")
    return result

@router.get("/{project_id}/preview/pages")
async def get_preview_pages(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
        
    pages = editor_service.get_preview_pages(p["path"])
    logger.info(f"[preview_pages] project_id={project_id} pages={len(pages)}")
    return {"pages": pages}

@router.get("/{project_id}/preview/{filename}")
async def get_preview_image(project_id: str, filename: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Security check: filename should be simple
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
        
    file_path = os.path.join(p["path"], "recipe", "preview_cache", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Image not found")


@router.get("/{project_id}/asset")
async def get_project_asset(project_id: str, path: str = Query(...)):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    base_dir = os.path.abspath(p["path"])
    raw = str(path or "").strip()
    if not raw or "\x00" in raw:
        raise HTTPException(status_code=400, detail="Invalid path")
    if raw.startswith("/"):
        raw = raw[1:]
    if ".." in raw or raw.startswith("~"):
        raise HTTPException(status_code=400, detail="Invalid path")

    abs_path = os.path.abspath(os.path.join(base_dir, raw))
    if not abs_path.startswith(base_dir + os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Asset not found")

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        raise HTTPException(status_code=400, detail="Unsupported asset type")

    mt = mimetypes.guess_type(abs_path)[0] or "application/octet-stream"
    return FileResponse(abs_path, media_type=mt)

@router.post("/{project_id}/command")
async def execute_command(project_id: str, req: CommandRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
        
    success = editor_service.process_modification(p["path"], req.command, req.page_index)
    compile_result = None
    if success:
        compile_result = editor_service.compile(p["path"])

    return {"success": success, "compile": compile_result}

@router.post("/{project_id}/generate")
async def generate_slides(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    with _GEN_LOCK:
        st = _GEN_STATE.get(project_id) or {}
        if st.get("status") in {"generating", "compiling", "enriching"}:
            return {"success": True, "started": False, "status": st.get("status"), "current_index": st.get("current_index"), "total": st.get("total")}

        _GEN_STATE[project_id] = {
            "status": "generating",
            "started_at": time.time(),
            "ended_at": None,
            "current_index": 0,
            "current_title": "",
            "total": int(len(p.get("nodes") or [])),
            "compile": None,
            "error": None,
        }

    def _worker():
        try:
            def _progress(i: int, total: int, name: str):
                with _GEN_LOCK:
                    st = _GEN_STATE.get(project_id) or {}
                    st["status"] = "generating"
                    st["current_index"] = int(i)
                    st["total"] = int(total)
                    st["current_title"] = str(name or "")
                    _GEN_STATE[project_id] = st

            logger.info(f"[generate] start project_id={project_id}")
            ok = editor_service.generate_slides(p, progress_cb=_progress)
            if not ok:
                raise RuntimeError("generate_slides failed")

            with _GEN_LOCK:
                st = _GEN_STATE.get(project_id) or {}
                st["status"] = "compiling"
                _GEN_STATE[project_id] = st

            compile_result = editor_service.compile(p["path"])

            enrich_result = None
            if not bool(compile_result.get("success")):
                with _GEN_LOCK:
                    st = _GEN_STATE.get(project_id) or {}
                    st["status"] = "error"
                    st["ended_at"] = time.time()
                    st["compile"] = compile_result
                    st["error"] = "compile_failed"
                    _GEN_STATE[project_id] = st
                logger.info(f"[generate] compile failed project_id={project_id}")
                return

            if bool(compile_result.get("success")):
                with _GEN_LOCK:
                    st = _GEN_STATE.get(project_id) or {}
                    st["status"] = "enriching"
                    _GEN_STATE[project_id] = st

                try:
                    lc = {"nodes": p.get("nodes") or [], "edges": p.get("edges") or []}
                except Exception:
                    lc = {"nodes": [], "edges": []}
                try:
                    enrich_result = editor_service.auto_enrich_citations(p["path"], logic_chain=lc, max_refs_per_slide=3)
                    logger.info(f"[generate] auto_enrich_citations result={enrich_result}")
                except Exception as e:
                    enrich_result = {"success": False, "reason": str(e)}
                    logger.error(f"[generate] auto_enrich_citations failed: {e}")

            with _GEN_LOCK:
                st = _GEN_STATE.get(project_id) or {}
                st["status"] = "done"
                st["ended_at"] = time.time()
                st["compile"] = compile_result
                st["enrich"] = enrich_result
                st["current_index"] = int(st.get("total") or 0)
                _GEN_STATE[project_id] = st
            logger.info(f"[generate] done project_id={project_id}")
        except Exception as e:
            with _GEN_LOCK:
                _GEN_STATE[project_id] = {
                    **(_GEN_STATE.get(project_id) or {}),
                    "status": "error",
                    "ended_at": time.time(),
                    "error": str(e),
                    "trace": traceback.format_exc()[:2000],
                }

    threading.Thread(target=_worker, daemon=True).start()
    return {"success": True, "started": True}


@router.get("/{project_id}/generate/status")
async def get_generate_status(project_id: str):
    with _GEN_LOCK:
        st = _GEN_STATE.get(project_id)
        if not st:
            return {"status": "idle"}
        out = dict(st)
        if "trace" in out:
            out.pop("trace", None)
        return out


@router.post("/{project_id}/ai/beautify")
async def ai_beautify(project_id: str, req: BeautifyRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    rounds = max(1, min(8, int(req.rounds or 3)))
    logger.info(f"[ai_beautify] start project_id={project_id} rounds={rounds}")

    ok = editor_service.beautify_pdf(p["path"], rounds=rounds)
    compile_result = editor_service.compile(p["path"])
    ok2 = bool(compile_result.get("success"))
    logger.info(f"[ai_beautify] done project_id={project_id} success={ok2}")
    return {"success": ok2, "compile": compile_result, "beautified": bool(ok)}


@router.get("/{project_id}/graph/reference")
async def get_reference_graph(project_id: str):
    return {"nodes": [], "edges": [], "pages": []}


@router.post("/{project_id}/graph/enrich")
async def enrich_reference_graph(project_id: str, req: EnrichReferenceGraphRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        lc = {"nodes": p.get("nodes") or [], "edges": p.get("edges") or []}
    except Exception:
        lc = {"nodes": [], "edges": []}
    res = editor_service.auto_enrich_citations(p["path"], logic_chain=lc, max_refs_per_slide=int(req.max_refs_per_slide or 3))
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=str(res.get("reason") or "enrich_failed"))
    return {"success": True, "updated_slide_ids": res.get("updated_slide_ids") or []}


@router.get("/{project_id}/ai/html/status")
async def get_html_gen_status(project_id: str):
    with _HTML_GEN_LOCK:
        st = _HTML_GEN_STATE.get(project_id) or {}
        return st


@router.get("/{project_id}/ai/html/repair/status")
async def get_html_repair_status(project_id: str):
    with _HTML_REPAIR_LOCK:
        st = _HTML_REPAIR_STATE.get(project_id) or {}
        return st


@router.post("/{project_id}/ai/html/repair")
async def ai_repair_html(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    with _HTML_REPAIR_LOCK:
        st = _HTML_REPAIR_STATE.get(project_id) or {}
        if st.get("status") == "repairing":
            return {"success": True, "started": False, "status": "repairing"}
        _HTML_REPAIR_STATE[project_id] = {"status": "repairing", "current": 0, "total": 0, "error": None}

    project_path = p["path"]
    recipe_dir = os.path.join(project_path, "recipe")
    html_dir = os.path.join(recipe_dir, "html_slides")
    if not os.path.isdir(html_dir):
        raise HTTPException(status_code=404, detail="HTML not found. Generate first.")

    meta_path = os.path.join(recipe_dir, "html_meta.json")
    meta = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f) or {}
        except Exception:
            meta = {}

    try:
        with open(os.path.join(recipe_dir, "content.tex"), "r", encoding="utf-8", errors="ignore") as f:
            content_tex = f.read()
    except Exception:
        content_tex = ""
    frames = HtmlRepairAgent.find_frames(content_tex)
    page_to_frame = meta.get("page_to_frame") if isinstance(meta, dict) else None
    if not isinstance(page_to_frame, list):
        page_to_frame = []

    pages = meta.get("html_pages") if isinstance(meta, dict) else None
    if not isinstance(pages, list) or not pages:
        pages = [fn for fn in os.listdir(html_dir) if isinstance(fn, str) and fn.lower().endswith(".html")]
        pages.sort(key=_safe_int_from_filename)

    all_images_rel = HtmlRepairAgent.scan_project_images(project_path)

    def _asset_url(rel_path: str) -> str:
        rel = str(rel_path or "").strip().lstrip("/")
        return f"/api/v1/projects/{project_id}/asset?path={urllib.parse.quote(rel)}"

    def _worker():
        try:
            with _HTML_REPAIR_LOCK:
                _HTML_REPAIR_STATE[project_id]["total"] = len(pages)
            agent = HtmlRepairAgent(ai_service._get_client("HTML_REPAIR") if getattr(ai_service, "_get_client", None) else None)
            repaired = 0
            for i, fn in enumerate(pages):
                with _HTML_REPAIR_LOCK:
                    _HTML_REPAIR_STATE[project_id]["current"] = i + 1
                fpath = os.path.join(html_dir, str(fn))
                if not os.path.isfile(fpath):
                    continue
                html_doc = ""
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        html_doc = f.read()
                    if len(html_doc) > 240_000:
                        html_doc = html_doc[:240_000]
                except Exception:
                    html_doc = ""
                if not html_doc:
                    continue

                slide_no = _safe_int_from_filename(str(fn))
                idx = max(0, slide_no - 1)
                frame_idx = None
                if page_to_frame and idx < len(page_to_frame):
                    if isinstance(page_to_frame[idx], int):
                        frame_idx = page_to_frame[idx]
                if frame_idx is None:
                    frame_idx = idx
                frame_tex = frames[frame_idx] if isinstance(frame_idx, int) and 0 <= frame_idx < len(frames) else ""

                ctx = HtmlRepairAgent.propose_fix(
                    project_id=project_id,
                    project_path=project_path,
                    slide_no=slide_no,
                    html_doc=html_doc,
                    frame_tex=frame_tex,
                    all_images_rel=all_images_rel,
                    prefer_frame_images=True,
                )
                issues = set(ctx.get("issues") or [])
                if "placeholder_div" not in issues and "commented_img" not in issues:
                    continue
                ctx["all_images_rel"] = all_images_rel[:2500]
                choice = agent.decide_with_llm(ctx, project_path=project_path)
                chosen_rel = str(choice.get("chosen_rel") or ctx.get("picked_rel_image") or "").strip().lstrip("/")
                chosen_url = _asset_url(chosen_rel) if chosen_rel else ""

                new_html, changes = HtmlRepairAgent.patch_html_with_image(html_doc, chosen_url)
                if changes > 0 and new_html != html_doc:
                    try:
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write(new_html)
                        repaired += 1
                    except Exception:
                        pass

            with _HTML_REPAIR_LOCK:
                _HTML_REPAIR_STATE[project_id]["status"] = "done"
                _HTML_REPAIR_STATE[project_id]["repaired"] = repaired
        except Exception as e:
            with _HTML_REPAIR_LOCK:
                _HTML_REPAIR_STATE[project_id]["status"] = "error"
                _HTML_REPAIR_STATE[project_id]["error"] = str(e)

    threading.Thread(target=_worker, daemon=True).start()
    return {"success": True, "started": True}

@router.post("/{project_id}/ai/html/generate")
async def ai_generate_html(project_id: str, req: HtmlGenerateRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        logger.info(
            f"[ai_html] request project_id={project_id} focus_pages={len(req.focus_pages or [])} effects={len(req.effects or [])} "
            f"visual_fx={bool(getattr(req, 'visual_fx', False))} intensity={str(getattr(req, 'visual_fx_intensity', '') or '')}"
        )
    except Exception:
        pass

    with _HTML_GEN_LOCK:
        st = _HTML_GEN_STATE.get(project_id) or {}
        if st.get("status") == "generating":
            return {"success": True, "started": False, "status": "generating"}
        
        _HTML_GEN_STATE[project_id] = {
            "status": "generating",
            "current": 0,
            "total": 0,
            "error": None
        }

    project_path = p["path"]
    recipe_dir = os.path.join(project_path, "recipe")
    os.makedirs(recipe_dir, exist_ok=True)

    pages = editor_service.get_preview_pages(project_path)
    if not pages:
        raise HTTPException(status_code=400, detail="No preview pages. Compile first.")

    try:
        if hasattr(editor_service, "align_speech_to_pdf_pages"):
            align = editor_service.align_speech_to_pdf_pages(project_path)
            if isinstance(align, dict) and not bool(align.get("success")):
                raise RuntimeError(str(align.get("reason") or "align_failed"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to align speech to PDF pages: {e}")

    focus = [int(x) for x in (req.focus_pages or []) if isinstance(x, int) or str(x).isdigit()]
    focus = [x for x in focus if 0 <= x < len(pages)]
    if not focus:
        focus = list(range(len(pages)))

    speech_path = os.path.join(recipe_dir, "speech.txt")
    speeches: List[str] = []
    try:
        with open(speech_path, "r", encoding="utf-8", errors="ignore") as f:
            speeches = f.read().split("<next>")
    except Exception:
        speeches = []

    effects = [str(x) for x in (req.effects or [])][:10]
    meta = {
        "focus_pages": focus,
        "effects": effects,
        "per_slide_max_regions": int(req.per_slide_max_regions or 3),
        "effects_by_page": req.effects_by_page or {},
        "per_slide_max_regions_by_page": req.per_slide_max_regions_by_page or {},
    }

    html_dir = os.path.join(recipe_dir, "html_slides")
    os.makedirs(html_dir, exist_ok=True)

    # Capture variables for the worker
    mr_global = int(req.per_slide_max_regions or 3)
    
    def _worker():
        try:
            with _HTML_GEN_LOCK:
                _HTML_GEN_STATE[project_id]["total"] = len(focus)

            # Load core structural data for frame alignment and references
            try:
                with open(os.path.join(recipe_dir, "content.tex"), "r", encoding="utf-8", errors="ignore") as f:
                    content_tex = f.read()
            except Exception:
                content_tex = ""
            frames = [m.group(1) for m in re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', content_tex, re.DOTALL)]
            
            page_to_frame = []
            dsid_by_page = []
            page_meta_by_page = []
            try:
                # Priority 1: alignment_dsid.json (High precision based on tikz markers)
                # Priority 2: alignment.json (Fuzzy matching based on text content)
                dsid_path = os.path.join(recipe_dir, "alignment_dsid.json")
                fuzzy_path = os.path.join(recipe_dir, "alignment.json")
                
                alignment_data = {}
                if os.path.exists(dsid_path):
                    with open(dsid_path, "r", encoding="utf-8") as f:
                        alignment_data = json.load(f)
                        # Map dsid indices to 0-based frame indices
                        dsid_by_page = alignment_data.get("dsid_by_page") or []
                        page_meta_by_page = alignment_data.get("page_meta_by_page") or []
                        page_to_frame = [ (idx - 1) if (idx is not None and isinstance(idx, int) and idx > 0) else None for idx in dsid_by_page ]
                
                if not any(x is not None for x in page_to_frame) and os.path.exists(fuzzy_path):
                    with open(fuzzy_path, "r", encoding="utf-8") as f:
                        alignment_data = json.load(f)
                        page_to_frame = alignment_data.get("page_to_frame") or []
            except Exception:
                page_to_frame = []
                dsid_by_page = []
                page_meta_by_page = []
            
            references_source = []
            try:
                ref_path = os.path.join(recipe_dir, "ref.bib")
                if os.path.exists(ref_path):
                    with open(ref_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_bib = f.read()
                        # Extract bibliography entries for context
                        references_source = [str(x).strip() for x in re.split(r"@\w+\{", raw_bib) if str(x).strip()]
            except Exception:
                references_source = []

            def _gate_effects(effects_in: List[str], data: Dict[str, Any]) -> List[str]:
                """Source-level gating: avoid placeholders AND avoid redundant dual-renderings.

                Key rule: at most ONE primary visual effect per slide.
                (Image Focus | Table Viz | Auto Diagram). Text Keynote is allowed only when
                it does not duplicate the visual's content.
                """
                eff = [str(x) for x in (effects_in or []) if str(x or "").strip()]
                title = str(data.get("title") or "").strip()
                subtitle = str(data.get("subtitle") or "").strip()
                bullets = data.get("bullets") or []
                plain = str(data.get("plain") or "").strip()
                tables = data.get("tables") or []
                images = data.get("images") or []
                has_text = bool(title or subtitle or bullets or plain)
                if not has_text:
                    ft = str(data.get("_frame_tex") or "")
                    has_text = bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", ft))

                out: List[str] = []
                for e in eff[:10]:
                    if e == "Table Viz" and not tables:
                        continue
                    if e == "Auto Diagram" and not has_text:
                        continue
                    if e == "Image Focus" and not images:
                        continue
                    if e in {"Text Keynote", "Auto Layout"} and not has_text:
                        continue
                    out.append(e)

                # Choose ONE primary visual. Priority: real images > real tables > diagram fallback.
                primaries = [x for x in out if x in {"Image Focus", "Table Viz", "Auto Diagram"}]
                primary = None
                if "Image Focus" in primaries:
                    primary = "Image Focus"
                elif "Table Viz" in primaries:
                    primary = "Table Viz"
                elif "Auto Diagram" in primaries:
                    primary = "Auto Diagram"

                # Data-driven fallback:
                # - If user asked for any primary visual effect but this slide has no image/table,
                #   prefer an Auto Diagram when there is text, rather than leaving placeholders.
                requested_primary = any(x in eff for x in ("Image Focus", "Table Viz", "Auto Diagram"))
                if primary is None and requested_primary and has_text and (not images) and (not tables):
                    primary = "Auto Diagram"

                if primary:
                    out = [x for x in out if x not in {"Image Focus", "Table Viz", "Auto Diagram"}]
                    out.insert(0, primary)

                # Text Keynote is treated as a styling effect in spec mode (no extra panels), so it may coexist.

                # If we have a strong visual (Image/Table), keep Text Keynote only if there's actually text to emphasize.
                if primary in {"Image Focus", "Table Viz"} and not has_text:
                    out = [x for x in out if x != "Text Keynote"]

                # If there is effectively no text at all, do not keep text-only styling effects.
                if not has_text:
                    out = [x for x in out if x not in {"Text Keynote", "Auto Layout"}]

                # Keep motion as a light global enhancement only.
                seen = set()
                dedup: List[str] = []
                for x in out:
                    if x in seen:
                        continue
                    seen.add(x)
                    dedup.append(x)
                return dedup[:6]

            def _infer_theme_from_preview(full_image_path: str) -> str:
                try:
                    from PIL import Image

                    with Image.open(full_image_path) as im:
                        im = im.convert("L")
                        im = im.resize((96, 54))
                        pixels = list(im.getdata())
                    if not pixels:
                        return "light"
                    avg = sum(pixels) / float(len(pixels))
                    return "light" if avg >= 150 else "dark"
                except Exception:
                    return "light"

            def _is_probably_placeholder_png(abs_path: str) -> bool:
                try:
                    if not abs_path:
                        return False
                    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
                        return False
                    ext = os.path.splitext(abs_path)[1].lower()
                    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                        return False
                    if os.path.getsize(abs_path) > 50_000:
                        return False
                    from PIL import Image
                    with Image.open(abs_path) as im:
                        im = im.convert("RGB")
                        im = im.resize((32, 32))
                        px = list(im.getdata())
                    if not px:
                        return False
                    base = (226, 232, 240)
                    max_dev = 0
                    max_span = 0
                    for c in range(3):
                        vals = [p[c] for p in px]
                        max_span = max(max_span, max(vals) - min(vals))
                        max_dev = max(max_dev, max(abs(v - base[c]) for v in vals))
                    return max_span <= 6 and max_dev <= 10
                except Exception:
                    return False

            def _strip_tex(s: str) -> str:
                t = str(s or "")
                # 1. Protect Math: Keep $...$ but normalize spaces inside
                t = re.sub(r"\$([\s\S]*?)\$", lambda m: f"${m.group(1).strip()}$", t)
                
                # 2. Map common symbols to Unicode (Scientific / Technical)
                symbol_map = {
                    r"\rightarrow": "→", r"\Rightarrow": "⇒", r"\leftrightarrow": "↔",
                    r"\approx": "≈", r"\neq": "≠", r"\leq": "≤", r"\geq": "≥",
                    r"\times": "×", r"\pm": "±", r"\nabla": "∇", r"\partial": "∂",
                    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
                    r"\theta": "θ", r"\lambda": "λ", r"\mu": "μ", r"\sigma": "σ",
                    r"\omega": "ω", r"\pi": "π", r"\infty": "∞", r"\forall": "∀",
                    r"\exists": "∃", r"\in": "∈", r"\notin": "∉", r"\dots": "...",
                    r"\ldots": "...", r"\cdot": "·"
                }
                for sym, uni in symbol_map.items():
                    t = t.replace(sym, uni)

                # 3. Handle common formatting commands (keep content)
                t = re.sub(r"\\(?:textbf|textit|text|emph|url|href)\{([^}]*)\}", r"\1", t)
                t = re.sub(r"\\(?:href)\{[^}]*\}\{([^}]*)\}", r"\1", t)
                
                # 4. Strip remaining commands but keep content if it's in {}
                t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
                t = re.sub(r"\{([^\}]*)\}", r"\1", t)
                
                # 5. Final Cleanup
                t = re.sub(r"\s+", " ", t)
                return t.strip()

            def _parse_tabular(block: str) -> List[List[str]]:
                rows: List[List[str]] = []
                for ln in str(block or "").splitlines():
                    ln = ln.strip()
                    if not ln or ln.startswith("%"):
                        continue
                    ln = re.sub(r"\\hline", "", ln)
                    ln = ln.strip().rstrip("\\")
                    if "&" not in ln:
                        continue
                    cells = [c.strip() for c in ln.split("&")]
                    cells = [_strip_tex(c) for c in cells]
                    if any(cells):
                        rows.append(cells)
                return rows

            def _extract_frame_struct(frame_tex: str) -> Dict[str, Any]:
                title = ""
                subtitle = ""
                m = re.search(r"\\frametitle\{([^}]*)\}", frame_tex)
                if m:
                    title = _strip_tex(m.group(1))
                m2 = re.search(r"\\framesubtitle\{([^}]*)\}", frame_tex)
                if m2:
                    subtitle = _strip_tex(m2.group(1))

                bullets: List[str] = []
                for blk in re.findall(r"\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}", frame_tex):
                    for it in re.split(r"\\item", blk)[1:]:
                        txt = _strip_tex(it)
                        if txt:
                            bullets.append(txt)

                images_raw: List[str] = []
                images: List[str] = []
                for im in re.findall(r"\\includegraphics\*?(?:\[[^\]]*\])?\{([^\}]+)\}", frame_tex):
                    rel = str(im).strip()
                    if rel:
                        images_raw.append(rel)
                    resolved = _resolve_image_rel(rel)
                    if resolved:
                        images.append(resolved)

                tables: List[List[List[str]]] = []
                table_patterns = [
                    r"\\begin\{tabular\}(?:\[[^\]]*\])?\{[^\}]*\}([\s\S]*?)\\end\{tabular\}",
                    r"\\begin\{tabularx\}(?:\[[^\]]*\])?\{[^\}]*\}\{[^\}]*\}([\s\S]*?)\\end\{tabularx\}",
                    r"\\begin\{tabular\*\}(?:\[[^\]]*\])?\{[^\}]*\}\{[^\}]*\}([\s\S]*?)\\end\{tabular\*\}",
                    r"\\begin\{longtable\}(?:\[[^\]]*\])?\{[^\}]*\}([\s\S]*?)\\end\{longtable\}",
                ]
                for pat in table_patterns:
                    for blk in re.findall(pat, frame_tex):
                        rows = _parse_tabular(blk)
                        if rows:
                            tables.append(rows)

                body = re.sub(r"\\begin\{frame\}[\s\S]*?\\frametitle\{[\s\S]*?\}\s*", "", frame_tex)
                body = re.sub(r"\\begin\{itemize\}[\s\S]*?\\end\{itemize\}", " ", body)
                body = re.sub(r"\\includegraphics\*?(?:\[[^\]]*\])?\{[^\}]+\}", " ", body)
                body = re.sub(r"\\begin\{tabular\}[\s\S]*?\\end\{tabular\}", " ", body)
                plain = _strip_tex(body)

                return {
                    "title": title,
                    "subtitle": subtitle,
                    "bullets": bullets[:12],
                    "images_raw": images_raw[:12],
                    "images": images[:6],
                    "tables": tables[:2],
                    "plain": plain[:1200],
                }

            def _asset_url(rel_path: str) -> str:
                rel = str(rel_path or "").strip()
                rel = rel.lstrip("/")
                return f"/api/v1/projects/{project_id}/asset?path={urllib.parse.quote(rel)}"

            def _preview_url(filename: str) -> str:
                safe = str(filename or "").strip()
                if not safe or ".." in safe or "/" in safe:
                    return ""
                return f"/api/v1/projects/{project_id}/preview/{urllib.parse.quote(safe)}"

            def _resolve_image_rel(rel_path: str) -> str:
                raw_in = str(rel_path or "").strip().replace("\\\\", "/")
                raw_in = raw_in.replace("\\_", "_")
                raw_in = raw_in.replace("\\%", "%")
                raw_in = raw_in.replace("\\#", "#")
                raw_in = raw_in.replace("\\&", "&")
                raw_in = raw_in.lstrip("/")
                if not raw_in or "\x00" in raw_in or raw_in.startswith("~"):
                    return ""

                allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf"}
                project_abs = os.path.abspath(project_path)

                def _normalize_rel_from_abs(abs_path: str) -> str:
                    try:
                        rel = os.path.relpath(abs_path, project_abs)
                    except Exception:
                        return ""
                    rel = rel.replace("\\\\", "/")
                    if rel.startswith("../") or rel == "..":
                        return ""
                    if ".." in rel.split("/"):
                        return ""
                    return rel.lstrip("/")

                def _exists_abs(abs_path: str) -> str:
                    if not abs_path.startswith(project_abs + os.sep):
                        return ""
                    if not os.path.exists(abs_path) or not os.path.isfile(abs_path):
                        return ""
                    ext = os.path.splitext(abs_path)[1].lower()
                    if ext not in allowed:
                        return ""
                    return abs_path

                candidates: List[str] = []
                ext = os.path.splitext(raw_in)[1].lower()
                if ext:
                    candidates.append(os.path.abspath(os.path.join(recipe_dir, raw_in)))
                    candidates.append(os.path.abspath(os.path.join(project_abs, raw_in)))
                else:
                    for e in [".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf"]:
                        candidates.append(os.path.abspath(os.path.join(recipe_dir, raw_in + e)))
                        candidates.append(os.path.abspath(os.path.join(project_abs, raw_in + e)))

                for abs_path in candidates:
                    pth = _exists_abs(abs_path)
                    if not pth:
                        continue
                    if os.path.splitext(pth)[1].lower() == ".pdf":
                        try:
                            from app.services.core.pdf_rasterize import pdf_first_page_to_png
                            out_dir = os.path.abspath(os.path.join(recipe_dir, "converted_images"))
                            png_abs = pdf_first_page_to_png(pth, out_dir, dpi=180)
                            if png_abs:
                                rel_png = _normalize_rel_from_abs(png_abs)
                                if rel_png:
                                    return rel_png
                        except Exception:
                            continue
                        continue
                    rel = _normalize_rel_from_abs(pth)
                    if rel:
                        return rel
                return ""

            def _patch_html_assets(doc: str, assets: Dict[str, Any]) -> str:
                out = str(doc or "")
                a = assets or {}
                page = str(a.get("page_image_path") or "")
                slide = str(a.get("slide_image_path") or "")
                # Intentionally DO NOT patch page_image_path: preview screenshots must not enter final HTML.
                if slide:
                    out = out.replace("assets/slide_image_path", slide)
                    out = out.replace("assets.slide_image_path", slide)
                    out = out.replace("assets[\"slide_image_path\"]", slide)
                    out = out.replace("assets['slide_image_path']", slide)
                return out

            def _strip_preview_image_sources(doc: str) -> str:
                """Hard safety: remove any references to /preview/ or page_image_path placeholders."""
                out = str(doc or "")
                # Remove any explicit preview URLs (img/src, CSS url())
                out = re.sub(r"<img[^>]*src=(['\"])[^'\"]*/preview/[^'\"]*\1[^>]*>", "", out, flags=re.IGNORECASE)
                out = re.sub(r"url\((['\"])?[^)\"']*/preview/[^)\"']*\1\)", "none", out, flags=re.IGNORECASE)
                # Remove any placeholder usage that could later be patched
                out = out.replace("assets/page_image_path", "")
                out = out.replace("assets.page_image_path", "")
                out = out.replace("assets[\"page_image_path\"]", "")
                out = out.replace("assets['page_image_path']", "")
                return out

            def _read_requirements_context() -> str:
                try:
                    collector = requirements_service.get_collector(project_id)
                except Exception:
                    return ""
                req = getattr(collector, "conversation_requirements", {}) or {}
                try:
                    audience = str(req.get("audience", "") or "").strip()
                    duration = str(req.get("duration", "") or "").strip()
                    focus = req.get("focus_sections") or []
                    style = str(req.get("style_preference", "") or "").strip()
                    focus_txt = ", ".join([str(x).strip() for x in focus if str(x).strip()]) if isinstance(focus, list) else ""
                    parts = []
                    if audience:
                        parts.append(f"Audience: {audience}")
                    if duration:
                        parts.append(f"Duration: {duration}")
                    if focus_txt:
                        parts.append(f"Focus: {focus_txt}")
                    if style:
                        parts.append(f"Style: {style}")
                    summary = "; ".join(parts).strip()
                    return summary[:2000] if summary else ""
                except Exception:
                    return ""

            requirements_context = _read_requirements_context()
            def _read_title_meta() -> Dict[str, str]:
                out = {"title": "", "author": "", "date": ""}
                candidates = [
                    os.path.join(project_path, "title.tex"),
                    os.path.join(recipe_dir, "title.tex"),
                ]
                for pth in candidates:
                    try:
                        if os.path.exists(pth) and os.path.isfile(pth):
                            raw = (open(pth, "r", encoding="utf-8", errors="ignore").read() or "")[:4000]
                            m1 = re.search(r"\\title\{([^}]*)\}", raw)
                            m2 = re.search(r"\\author\{([^}]*)\}", raw)
                            m3 = re.search(r"\\date\{([^}]*)\}", raw)
                            if m1:
                                out["title"] = str(m1.group(1) or "").strip()
                            if m2:
                                out["author"] = str(m2.group(1) or "").strip()
                            if m3:
                                out["date"] = str(m3.group(1) or "").strip()
                            if any(v for v in out.values()):
                                return out
                    except Exception:
                        continue
                return out

            title_meta = _read_title_meta()
            RenderPlanAgent = None
            HtmlSlideRenderer = None
            try:
                _m1 = importlib.import_module("app.services.render_plan_agent")
                _m2 = importlib.import_module("app.services.html_slide_renderer")
                RenderPlanAgent = getattr(_m1, "RenderPlanAgent", None)
                HtmlSlideRenderer = getattr(_m2, "HtmlSlideRenderer", None)
            except Exception:
                RenderPlanAgent = None
                HtmlSlideRenderer = None

            renderer = HtmlSlideRenderer() if HtmlSlideRenderer else None

            def _style_summary_from_plan(plan: "RenderPlan", theme_str: str) -> str:
                try:
                    layout = str(getattr(plan, "layout", "") or "")
                    eff = ",".join([str(x) for x in (getattr(plan, "effects_used", []) or []) if str(x or "").strip()])
                    style_cfg = getattr(plan, "style_config", {}) or {}
                    theme_variant = str(style_cfg.get("theme_variant") or "glass")
                    accent = str(style_cfg.get("accent_color") or "primary")
                    motion = str(style_cfg.get("motion_intensity") or "low")
                    return f"layout={layout}; theme_variant={theme_variant}; accent={accent}; motion={motion}; effects={eff}; theme={theme_str or 'spec'}"
                except Exception:
                    return f"theme={theme_str or 'spec'}"
            
            html_pages: List[str] = []
            theme = "spec"
            req_snip = re.sub(r"\s+", " ", str(requirements_context or "")).strip()[:160]
            deck_style_summary = f"Theme={theme}; Effects={','.join(effects or [])}; Requirements={req_snip or 'N/A'}"
            visual_fx = bool(getattr(req, "visual_fx", False)) or (str(os.getenv("DS_VISUAL_FX_AUTO") or "").strip() == "1")
            deck_dna = None
            deck_hash = ""
            if visual_fx:
                try:
                    from app.services.visual_asset_service import load_or_create_deck_style  # type: ignore
                    first_idx = int(focus[0]) if focus else 0
                    first_img = os.path.join(recipe_dir, "preview_cache", pages[first_idx]) if pages and 0 <= first_idx < len(pages) else ""
                    initial_theme = _infer_theme_from_preview(first_img) if first_img else "light"
                    deck_dna, deck_hash = load_or_create_deck_style(
                        project_path=project_path,
                        requirements_context=requirements_context,
                        persona=str((p.get("requirements") or {}).get("persona") or ""),
                        theme=initial_theme,
                    )
                    if deck_hash:
                        deck_style_summary = deck_style_summary + f"; DeckStyleDNA={deck_hash}"
                except Exception:
                    deck_dna = None
                    deck_hash = ""
            prev_style_summary = ""
            def _extra_page_data(page_index: int, page_type: str, label: str) -> Dict[str, Any]:
                t = str(page_type or "").strip().lower()
                lbl = str(label or "").strip()
                if t == "title":
                    title = str(title_meta.get("title") or "").strip() or "Untitled"
                    subtitle = str(title_meta.get("author") or "").strip()
                    return {"title": title, "subtitle": subtitle, "bullets": [], "plain": "", "tables": [], "images": [], "_page_type": "title"}
                if t == "references":
                    bullets = []
                    for chunk in (references_source or [])[:12]:
                        s = " ".join([x.strip() for x in str(chunk or "").splitlines() if x.strip()])
                        s = re.sub(r"\s+", " ", s).strip()
                        if s:
                            bullets.append(s[:140])
                        if len(bullets) >= 6:
                            break
                    if not bullets:
                        bullets = ["References available in the paper."]
                    return {"title": "References", "subtitle": "", "bullets": bullets, "plain": "", "tables": [], "images": [], "_page_type": "references"}
                if t == "ending":
                    title = str(title_meta.get("title") or "").strip()
                    subtitle = f"Thanks! {title}".strip() if title else "Thanks!"
                    return {"title": "Thank You", "subtitle": subtitle, "bullets": [], "plain": "", "tables": [], "images": [], "_page_type": "ending"}
                if t == "outline":
                    return {"title": "Outline", "subtitle": "", "bullets": [], "plain": "", "tables": [], "images": [], "_page_type": "outline"}
                if t == "section":
                    return {"title": lbl or "Section", "subtitle": "", "bullets": [], "plain": "", "tables": [], "images": [], "_page_type": "section"}
                return {"title": lbl or f"Slide {int(page_index) + 1}", "subtitle": "", "bullets": [], "plain": "", "tables": [], "images": [], "_page_type": t or "extra"}

            for i_seq, idx in enumerate(focus):
                # UPDATE PROGRESS
                with _HTML_GEN_LOCK:
                    _HTML_GEN_STATE[project_id]["current"] = i_seq + 1

                enabled_raw = (req.effects_by_page or {}).get(idx) or effects
                fn = pages[idx]
                full_img = os.path.join(recipe_dir, "preview_cache", fn)
                theme = _infer_theme_from_preview(full_img)

                sid = None
                try:
                    sid = dsid_by_page[idx] if isinstance(dsid_by_page, list) and 0 <= idx < len(dsid_by_page) else None
                except Exception:
                    sid = None
                meta_i: Dict[str, Any] = {}
                try:
                    meta_i = page_meta_by_page[idx] if isinstance(page_meta_by_page, list) and 0 <= idx < len(page_meta_by_page) and isinstance(page_meta_by_page[idx], dict) else {}
                except Exception:
                    meta_i = {}
                page_type = str(meta_i.get("type") or "").strip().lower()
                label = str(meta_i.get("label") or "").strip()

                frame_idx = None
                frame_tex = ""
                if isinstance(sid, int) and sid > 0:
                    frame_idx = int(sid - 1)
                    if not (0 <= frame_idx < len(frames)):
                        raise RuntimeError(f"DSID out of range for page={idx+1}: sid={sid} frames={len(frames)} preview={fn}")
                    frame_tex = frames[frame_idx]
                    data = _extract_frame_struct(frame_tex)
                    data["_frame_tex"] = str(frame_tex or "")[:8000]
                else:
                    data = _extra_page_data(idx, page_type, label)
                    data["_frame_tex"] = ""
                data["preview_filename"] = fn
                data["_references_source"] = references_source
                data["images"] = [str(x) for x in (data.get("images") or []) if isinstance(x, str)]
                if data.get("images"):
                    kept = []
                    for rel_img in data["images"]:
                        abs_img = os.path.abspath(os.path.join(project_path, rel_img))
                        if _is_probably_placeholder_png(abs_img):
                            continue
                        kept.append(rel_img)
                    data["images"] = kept

                valid_images: List[str] = []
                valid_image_urls: List[str] = []
                for rel_img in (data.get("images") or []):
                    try:
                        resolved = _resolve_image_rel(str(rel_img))
                    except Exception:
                        resolved = ""
                    if isinstance(resolved, str) and resolved:
                        valid_images.append(str(resolved))
                        valid_image_urls.append(_asset_url(str(resolved)))
                data["images"] = valid_images
                data["_asset_image_urls"] = valid_image_urls

                images_raw = [str(x) for x in (data.get("images_raw") or []) if str(x or "").strip()]
                if images_raw and not valid_image_urls:
                    raise RuntimeError(
                        f"Image referenced in TeX but could not be resolved for HTML. "
                        f"page={idx+1} preview={fn} raw={images_raw[:6]}"
                    )
                if not isinstance(sid, int) and (page_type not in {"title", "references", "ending", "outline", "section", "extra"}):
                    raise RuntimeError(
                        f"Missing DSID marker for non-extra page. page={idx+1} preview={fn} page_type={page_type or 'unknown'}"
                    )

                enabled_hint = [str(x) for x in (enabled_raw or []) if str(x or "").strip()]
                enabled = _gate_effects(enabled_hint, data)

                speech = speeches[idx] if (idx < len(speeches) and len(speeches) == len(pages)) else (speeches[idx] if idx < len(speeches) else "")

                for k in ("title", "subtitle"):
                    if not data.get(k):
                        data[k] = ""
                if not data.get("title"):
                    data["title"] = f"Slide {idx + 1}"

                enabled_before_diagram_gate = list(enabled)
                diagram_threshold = 500
                try:
                    diagram_threshold = int(str(os.getenv("DS_AUTO_DIAGRAM_MIN_CHARS") or "").strip() or "500")
                except Exception:
                    diagram_threshold = 500
                diagram_threshold = max(0, min(20000, int(diagram_threshold)))
                try:
                    blob_parts = []
                    blob_parts.append(str(data.get("title") or ""))
                    blob_parts.append(str(data.get("subtitle") or ""))
                    blob_parts.append(str(data.get("plain") or ""))
                    blob_parts.extend([str(x or "") for x in (data.get("bullets") or [])])
                    blob = "\n".join([str(x).strip() for x in blob_parts if str(x or "").strip()]).strip()
                    speech_blob = str(speech or "").strip()
                    blob_len = len(blob) + len(speech_blob)
                except Exception:
                    blob_len = 0
                can_gate_diagram = (
                    ("Auto Diagram" in enabled_before_diagram_gate)
                    and ("Image Focus" not in enabled_before_diagram_gate)
                    and ("Table Viz" not in enabled_before_diagram_gate)
                )
                should_enter_diagram = bool(can_gate_diagram and (blob_len >= diagram_threshold))
                if can_gate_diagram and not should_enter_diagram:
                    enabled = [e for e in (enabled or []) if e != "Auto Diagram"]

                for rel in list(data.get("images") or []):
                    _ = _asset_url(rel)

                mr = int((req.per_slide_max_regions_by_page or {}).get(idx) or mr_global)
                mr = max(1, min(10, mr))

                html_doc = ""
                # === SlideSpec -> Deterministic Renderer ===
                allowed_image_urls = [str(u) for u in (data.get("_asset_image_urls") or []) if isinstance(u, str) and u]
                if not RenderPlanAgent or not renderer:
                    raise RuntimeError("Spec-mode HTML requires RenderPlanAgent + HtmlSlideRenderer.")
                
                tables = data.get("tables") or []
                table_rows = tables[0] if (tables and isinstance(tables, list) and tables[0]) else []
                # 1. Generate Baseline Plan
                plan = RenderPlanAgent.generate(
                    slide_no=idx + 1,
                    total_slides=len(pages),
                    theme=theme,
                    enabled_effects_hint=enabled,
                    content=data,
                    speech=str(speech or ""),
                    requirements_context=requirements_context,
                    allowed_image_urls=allowed_image_urls,
                    table_rows=table_rows,
                    title_meta=title_meta,
                    deck_style_summary=deck_style_summary,
                    prev_style_summary=prev_style_summary,
                )
                try:
                    plan.kicker = ""
                except Exception:
                    pass

                try:
                    plan.kicker = ""
                except Exception:
                    pass

                try:
                    plan.normalize()
                    plan.effects_used = [e for e in (plan.effects_used or []) if e in enabled]
                    plan.validate_effects(enabled_effects_hint=enabled)
                    plan.validate_urls(allowed_image_urls=[str(u) for u in (allowed_image_urls or []) if str(u or "").strip()])
                except Exception:
                    pass

                try:
                    if page_type in {"title", "ending"}:
                        plan.slide_role = "cover" if page_type == "title" else "ending"
                        plan.layout = "cover"
                        plan.title = str(data.get("title") or plan.title)
                        plan.subtitle = str(data.get("subtitle") or "")
                        plan.core_message = ""
                        plan.bullets = []
                        plan.steps = []
                        plan.metrics = []
                        plan.image = None
                        plan.table_viz = None
                        plan.diagram_spec = None
                        plan.effects_used = []
                        plan.require()
                    elif page_type == "references":
                        plan.slide_role = "references"
                        plan.layout = "references"
                        plan.title = "References"
                        plan.subtitle = ""
                        if not any(str(x or "").strip() for x in (getattr(plan, "bullets", None) or [])):
                            plan.bullets = [str(x) for x in (data.get("bullets") or []) if str(x or "").strip()][:10]
                        plan.core_message = ""
                        plan.steps = []
                        plan.metrics = []
                        plan.image = None
                        plan.table_viz = None
                        plan.diagram_spec = None
                        plan.effects_used = []
                        plan.require()
                except Exception:
                    pass

                try:
                    if can_gate_diagram:
                        if should_enter_diagram:
                            restricted = {"cover", "references", "toc", "section_transition", "hero_figure", "hero_figure_vertical", "table_focus"}
                            if getattr(plan, "layout", "") not in restricted:
                                spec = getattr(plan, "diagram_spec", None)
                                nodes = []
                                if isinstance(spec, dict):
                                    nodes = spec.get("nodes") or []
                                else:
                                    try:
                                        spec_dict = spec.model_dump() if hasattr(spec, "model_dump") else None
                                        if isinstance(spec_dict, dict):
                                            nodes = spec_dict.get("nodes") or []
                                    except Exception:
                                        nodes = []
                                has_valid_spec = bool(isinstance(nodes, list) and len(nodes) >= 2)
                                if not has_valid_spec:
                                    src_steps = [str(s).strip() for s in (getattr(plan, "steps", None) or []) if str(s or "").strip()]
                                    if not src_steps:
                                        src_steps = [str(s).strip() for s in (getattr(plan, "bullets", None) or []) if str(s or "").strip()]
                                    if not src_steps:
                                        src_steps = [str(s).strip() for s in re.split(r"[。\n;；]|(?<=[.!?])\\s+", str(getattr(plan, "core_message", "") or "")) if str(s or "").strip()]
                                    if not src_steps:
                                        src_steps = [str(s).strip() for s in (data.get("bullets") or []) if str(s or "").strip()]
                                    if not src_steps:
                                        src_steps = [str(s).strip() for s in re.split(r"[。\n;；]|(?<=[.!?])\\s+", str(data.get("plain") or "")) if str(s or "").strip()]
                                    if len(src_steps) < 2:
                                        long_txt = str(data.get("plain") or "").strip()
                                        if long_txt:
                                            chunk = 140
                                            src_steps = [long_txt[i : i + chunk].strip() for i in range(0, len(long_txt), chunk) if long_txt[i : i + chunk].strip()]
                                    src_steps = src_steps[:6]
                                    if len(src_steps) >= 2:
                                        nodes2 = []
                                        for i, s in enumerate(src_steps):
                                            lab = f"Step {i+1}"
                                            detail = s
                                            if ":" in s:
                                                a, b = s.split(":", 1)
                                                a = a.strip()
                                                b = b.strip()
                                                if a:
                                                    lab = a[:44]
                                                if b:
                                                    detail = b
                                            nodes2.append({"id": f"n{i+1}", "phase": "Execution", "label": lab, "detail": str(detail)[:220]})
                                        edges2 = [{"from": f"n{i+1}", "to": f"n{i+2}", "label": ""} for i in range(len(nodes2) - 1)]
                                        plan.diagram_spec = {"title": "", "nodes": nodes2, "edges": edges2, "layout": {"direction": "LR"}}
                                        has_valid_spec = True
                                if has_valid_spec:
                                    plan.layout = "diagram_flow"
                                    if "Auto Diagram" not in (plan.effects_used or []):
                                        plan.effects_used = list(plan.effects_used or []) + ["Auto Diagram"]
                        else:
                            if getattr(plan, "layout", "") == "diagram_flow":
                                plan.layout = "solo"
                            try:
                                plan.diagram_spec = None
                            except Exception:
                                pass
                            plan.effects_used = [e for e in (plan.effects_used or []) if e != "Auto Diagram"]
                except Exception:
                    pass

                if "Image Focus" in (plan.effects_used or []) and getattr(plan, "layout", "") == "hero_figure":
                    if getattr(plan, "image", None) and getattr(plan.image, "url", ""):
                        if not getattr(plan.image, "focus_template_id", None):
                            raise RuntimeError(
                                f"Image Focus requires image.focus_template_id. slide={idx+1} preview={fn}"
                            )

                try:
                    if "Table Viz" in (plan.effects_used or []) and getattr(plan, "layout", "") == "table_focus":
                        viz = getattr(plan, "table_viz", None)
                        payload_ok = bool(isinstance(getattr(viz, "payload", None), dict) and getattr(viz, "payload", None)) if viz else False
                        spec = getattr(viz, "spec", None) if viz else None
                        option_ok = bool(isinstance(spec, dict) and isinstance(spec.get("option"), dict) and bool(spec.get("option")))
                        if not (payload_ok or option_ok):
                            plan.effects_used = [e for e in (plan.effects_used or []) if e != "Table Viz"]
                            plan.layout = "solo"
                except Exception:
                    pass

                try:
                    if "Text Keynote" in (plan.effects_used or []):
                        blob = " ".join([str(getattr(plan, "title", "") or ""), str(getattr(plan, "subtitle", "") or ""), str(getattr(plan, "core_message", "") or "")] + [str(x or "") for x in (getattr(plan, "bullets", []) or [])])
                        if "[[[" not in blob and "[[" not in blob:
                            def _mark_once(s: str) -> str:
                                m = re.search(r"(\\b\\d+(?:\\.\\d+)?%?\\b|\\b\\d+x\\b)", s or "")
                                if not m:
                                    return s
                                a, b = m.span()
                                return (s[:a] + "[[[" + s[a:b] + "]]]" + s[b:]) if a >= 0 else s
                            if getattr(plan, "core_message", ""):
                                plan.core_message = _mark_once(str(plan.core_message or ""))
                            elif getattr(plan, "title", ""):
                                plan.title = _mark_once(str(plan.title or ""))
                except Exception:
                    pass

                try:
                    prev_style_summary = _style_summary_from_plan(plan, theme)
                except Exception:
                    prev_style_summary = prev_style_summary

                if visual_fx and deck_dna is not None and deck_hash:
                    try:
                        from app.services.visual_fx_integration import attach_visual_assets  # type: ignore
                        plan.visual_assets = attach_visual_assets(
                            project_id=project_id,
                            project_path=project_path,
                            slide_no=idx + 1,
                            page_idx=idx,
                            layout=str(getattr(plan, "layout", "") or ""),
                            slide_role=str(getattr(plan, "slide_role", "") or ""),
                            title=str(getattr(plan, "title", "") or ""),
                            subtitle=str(getattr(plan, "subtitle", "") or ""),
                            core_message=str(getattr(plan, "core_message", "") or ""),
                            bullets=[str(x) for x in (getattr(plan, "bullets", None) or []) if str(x or "").strip()],
                            deck_dna=deck_dna,
                            deck_hash=deck_hash,
                            visual_fx_intensity=str(getattr(req, "visual_fx_intensity", "low") or "low"),
                            visual_fx_by_page=getattr(req, "visual_fx_by_page", None),
                            visual_fx_enabled=getattr(req, "visual_fx_enabled", None),
                        )
                    except Exception as e:
                        allow_fallback = False
                        try:
                            allow_fallback = str(os.getenv("DS_VFX_ALLOW_FALLBACK") or "0").strip() == "1"
                        except Exception:
                            allow_fallback = False
                        try:
                            logger.error(f"[ai_html] visual_fx failed slide={idx+1}: {e}")
                        except Exception:
                            pass
                        if not allow_fallback:
                            raise
                        try:
                            plan.visual_assets = None
                        except Exception:
                            pass

                # 3. Rendering + Sandbox + QA with optional single regeneration
                def _parse_render_meta(doc: str) -> Dict[str, Any]:
                    m = re.search(r'<script type="application/json" id="render-meta">(.*?)</script>', doc, re.S)
                    if not m:
                        return {}
                    try:
                        return json.loads(m.group(1))
                    except Exception:
                        return {}

                def _needs_regeneration(issues: List[Any]) -> bool:
                    for it in issues or []:
                        try:
                            sev = getattr(it, "severity", "") or ""
                            t = getattr(it, "type", "") or getattr(it, "id", "")
                            if sev in ("high", "critical") and t in {
                                "JS_ERROR",
                                "NETWORK_ERROR",
                                "OVERFLOW",
                                "IMAGE_PRESENT_BUT_NO_HERO",
                                "TABLE_VIZ_MISSING",
                            }:
                                return True
                        except Exception:
                            continue
                    return False

                html_doc = ""
                from app.services.html_sandbox import run_sandbox  # type: ignore
                from app.services.render_review_agent import RenderReviewAgent  # type: ignore

                repair_context: Optional[Dict[str, Any]] = None

                for attempt in range(2):
                    html_doc = renderer.render_plan(plan, theme, speech_text=str(speech or ""), max_regions=mr)
                    if not html_doc:
                        raise RuntimeError("HtmlSlideRenderer.render returned empty HTML.")

                    meta_for_review = _parse_render_meta(html_doc)
                    # Use data URL so sandbox sees the same HTML, but assets still go through HTTP.
                    import base64
                    data_url = "data:text/html;base64," + base64.b64encode(html_doc.encode("utf-8")).decode("ascii")
                    sandbox_report = run_sandbox(data_url)

                    review = None
                    try:
                        review = RenderReviewAgent.review(
                            plan=plan,
                            html=html_doc,
                            render_meta=meta_for_review,
                            sandbox_report=sandbox_report.model_dump(),
                            max_issues=8,
                        )
                        if review.issues:
                            short = ", ".join(f"{it.id}:{it.severity}" for it in review.issues[:4])
                            logger.warning(f"[ai_html_review] slide={idx+1} attempt={attempt+1} issues={short}")
                    except Exception as e:
                        logger.warning(f"[ai_html_review] failed slide={idx+1}: {e}")

                    if attempt == 0 and review is not None and _needs_regeneration(getattr(review, "issues", [])):
                        repair_context = {
                            "issues": [i.model_dump() for i in (review.issues or [])],
                            "suggested_plan_patch": getattr(review, "suggested_plan_patch", {}),
                            "notes": getattr(review, "notes_for_slide_agent", ""),
                        }
                        try:
                            plan = RenderPlanAgent.generate(
                                slide_no=idx + 1,
                                total_slides=len(pages),
                                theme=theme,
                                enabled_effects_hint=enabled,
                                content=data,
                                speech=str(speech or ""),
                                requirements_context=requirements_context,
                                allowed_image_urls=allowed_image_urls,
                                table_rows=table_rows,
                                title_meta=title_meta,
                                deck_style_summary=deck_style_summary,
                                prev_style_summary=prev_style_summary,
                                repair_context=repair_context,
                            )
                        except Exception as e:
                            logger.warning(f"[ai_html_regen] failed to regenerate plan for slide={idx+1}: {e}")
                            break
                        continue

                    break

                # 4. Security & Cleanup
                html_doc = _strip_preview_image_sources(html_doc)

                out_name = f"slide_{idx+1}.html"
                out_path = os.path.join(html_dir, out_name)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(html_doc)
                html_pages.append(out_name)

            meta["html_pages"] = html_pages
            meta_path = os.path.join(recipe_dir, "html_meta.json")
            tmp_meta_path = f"{meta_path}.tmp"
            with open(tmp_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            os.replace(tmp_meta_path, meta_path)

            logger.info(f"[ai_html] generated project_id={project_id} slides={len(focus)} dir={html_dir!r}")
            
            with _HTML_GEN_LOCK:
                _HTML_GEN_STATE[project_id]["status"] = "done"

        except Exception as e:
            with _HTML_GEN_LOCK:
                _HTML_GEN_STATE[project_id]["status"] = "error"
                err_type = type(e).__name__
                err_msg = str(e or "").strip()
                if not err_msg:
                    err_msg = repr(e)
                _HTML_GEN_STATE[project_id]["error"] = f"{err_type}: {err_msg}"
                logger.exception(f"[ai_html] error: {err_type}: {err_msg}")

    threading.Thread(target=_worker, daemon=True).start()
    return {"success": True, "started": True}


@router.get("/{project_id}/html/pages")
async def get_html_pages(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    recipe_dir = os.path.join(p["path"], "recipe")
    html_dir = os.path.join(recipe_dir, "html_slides")
    meta_path = os.path.join(recipe_dir, "html_meta.json")
    if not os.path.exists(meta_path):
        if os.path.isdir(html_dir):
            try:
                files = [
                    fn
                    for fn in os.listdir(html_dir)
                    if isinstance(fn, str)
                    and fn.lower().endswith(".html")
                    and os.path.isfile(os.path.join(html_dir, fn))
                ]
                def _safe_int(fn: str) -> int:
                    m = re.search(r"(\d+)", str(fn or ""))
                    return int(m.group(1)) if m else 10**9
                files.sort(key=lambda x: (_safe_int(x), x))
                return {"pages": files, "meta": {"html_pages": files}}
            except Exception:
                return {"pages": []}
        return {"pages": []}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    pages = meta.get("html_pages") if isinstance(meta, dict) else None
    if not isinstance(pages, list):
        pages = []
    pages = [str(x) for x in pages if isinstance(x, str)]
    if pages:
        return {"pages": pages, "meta": meta}
    if os.path.isdir(html_dir):
        try:
            files = [
                fn
                for fn in os.listdir(html_dir)
                if isinstance(fn, str)
                and fn.lower().endswith(".html")
                and os.path.isfile(os.path.join(html_dir, fn))
            ]
            def _safe_int(fn: str) -> int:
                m = re.search(r"(\d+)", str(fn or ""))
                return int(m.group(1)) if m else 10**9
            files.sort(key=lambda x: (_safe_int(x), x))
            if isinstance(meta, dict):
                meta = {**meta, "html_pages": files}
            else:
                meta = {"html_pages": files}
            return {"pages": files, "meta": meta}
        except Exception:
            return {"pages": []}
    return {"pages": []}


@router.get("/{project_id}/html/{filename}")
async def get_html_file(project_id: str, filename: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = os.path.join(p["path"], "recipe", "html_slides", filename)
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception:
            return FileResponse(file_path)

        low = raw.lower()
        if "<html" in low and not low.lstrip().startswith(("<!doctype", "<html")):
            blocks = re.findall(r"```(?:html)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
            for b in blocks:
                bb = str(b or "").strip()
                if "<html" in bb.lower() or "<!doctype" in bb.lower():
                    raw = bb
                    break
            raw = re.sub(r"^```(?:html)?\s*", "", raw.strip(), flags=re.IGNORECASE)
            raw = re.sub(r"```\s*$", "", raw)
            raw = raw.strip()
            low = raw.lower()
            start_candidates = []
            di = low.find("<!doctype")
            hi = low.find("<html")
            if di >= 0:
                start_candidates.append(di)
            if hi >= 0:
                start_candidates.append(hi)
            if start_candidates:
                raw = raw[min(start_candidates):]
                low = raw.lower()
            end_tag = "</html>"
            ei = low.rfind(end_tag)
            if ei >= 0:
                raw = raw[: ei + len(end_tag)]
            raw = raw.strip()
            if raw.lower().startswith("<html"):
                raw = "<!doctype html>\n" + raw
            return HTMLResponse(raw)

        return HTMLResponse(raw)
    raise HTTPException(status_code=404, detail="HTML not found")


@router.post("/{project_id}/html/repair")
async def repair_html_slides(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    project_path = p["path"]
    recipe_dir = os.path.join(project_path, "recipe")
    html_dir = os.path.join(recipe_dir, "html_slides")
    if not os.path.isdir(html_dir):
        raise HTTPException(status_code=404, detail="HTML not found")

    repaired = 0
    for fn in os.listdir(html_dir):
        if not isinstance(fn, str) or not fn.lower().endswith(".html"):
            continue
        fpath = os.path.join(html_dir, fn)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except Exception:
            continue
        new = patch_html_doc_for_repair(raw, project_id=project_id, project_path=project_path)
        if new != raw:
            try:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new)
                repaired += 1
            except Exception:
                pass
    return {"success": True, "repaired": repaired}


@router.get("/{project_id}/export/pdf")
async def export_pdf(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    pdf_path = os.path.join(p["path"], "recipe", "base.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found. Compile first.")

    return FileResponse(pdf_path, filename=f"{p['name']}.pdf")


@router.get("/{project_id}/export/speech.txt")
async def export_speech(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    speech_path = os.path.join(p["path"], "recipe", "speech.txt")
    if not os.path.exists(speech_path):
        raise HTTPException(status_code=404, detail="speech.txt not found")

    return FileResponse(speech_path, filename=f"{p['name']}_speech.txt")


@router.get("/{project_id}/export/images.zip")
async def export_images_zip(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    cache_dir = os.path.join(p["path"], "recipe", "preview_cache")
    if not os.path.isdir(cache_dir):
        raise HTTPException(status_code=404, detail="Preview images not found. Compile first.")

    export_dir = os.path.join(p["path"], "recipe", "exports")
    zip_path = os.path.join(export_dir, "images.zip")
    _zip_dir(cache_dir, zip_path)
    return FileResponse(zip_path, filename=f"{p['name']}_images.zip")


@router.get("/{project_id}/export/pptx")
async def export_pptx(
    request: Request,
    project_id: str,
    mode: str = Query("static"),
    dpr: int = Query(2),
    timeout_ms: int = Query(60000),
    rewrite_assets: bool = Query(True),
):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    recipe_dir = os.path.join(p["path"], "recipe")
    export_dir = os.path.join(recipe_dir, "exports")
    pdf_path = os.path.join(recipe_dir, "base.pdf")
    m = str(mode or "static").strip().lower()
    if m not in {"static", "dynamic_replace", "dynamic_prepend", "dynamic_append"}:
        m = "static"

    if m == "static":
        out_path = os.path.join(export_dir, "slides.pptx")
        ok = _build_pptx_from_pdf_editable(pdf_path, out_path)
        if not ok:
            ok = _build_pptx_from_tex(recipe_dir, out_path)
        if not ok:
            cache_dir = os.path.join(recipe_dir, "preview_cache")
            if not os.path.isdir(cache_dir):
                raise HTTPException(status_code=404, detail="Preview images not found. Compile first.")
            imgs = [
                os.path.join(cache_dir, fn)
                for fn in sorted(os.listdir(cache_dir), key=_safe_int_from_filename)
                if fn.lower().endswith(".png")
            ]
            if not imgs:
                raise HTTPException(status_code=404, detail="No preview images")
            _build_pptx_from_images(imgs, out_path)
        return FileResponse(out_path, filename=f"{p['name']}.pptx")

    cache_dir = os.path.join(recipe_dir, "preview_cache")
    if not os.path.isdir(cache_dir) or not any(str(x).lower().endswith(".png") for x in os.listdir(cache_dir)):
        try:
            editor_service.get_preview_pages(p["path"])
        except Exception:
            pass
    if not os.path.isdir(cache_dir):
        raise HTTPException(status_code=404, detail="Preview images not found. Compile first.")
    pdf_imgs = [
        os.path.join(cache_dir, fn)
        for fn in sorted(os.listdir(cache_dir), key=_safe_int_from_filename)
        if fn.lower().endswith(".png")
    ]
    if not pdf_imgs:
        raise HTTPException(status_code=404, detail="No preview images")

    html_dir = os.path.join(recipe_dir, "html_slides")
    meta_path = os.path.join(recipe_dir, "html_meta.json")
    html_pages: List[str] = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            pages = meta.get("html_pages") if isinstance(meta, dict) else None
            if isinstance(pages, list):
                html_pages = [str(x) for x in pages if isinstance(x, str) and str(x).lower().endswith(".html")]
        except Exception:
            html_pages = []
    if not html_pages and os.path.isdir(html_dir):
        try:
            files = [
                fn
                for fn in os.listdir(html_dir)
                if isinstance(fn, str) and fn.lower().endswith(".html") and os.path.isfile(os.path.join(html_dir, fn))
            ]
            files.sort(key=lambda x: (_safe_int_from_filename(x), x))
            html_pages = files
        except Exception:
            html_pages = []

    html_map: Dict[int, str] = {}
    for fn in html_pages:
        mm = re.search(r"slide_(\d+)\.html", str(fn), flags=re.IGNORECASE)
        if not mm:
            continue
        idx = int(mm.group(1)) - 1
        if idx >= 0:
            html_map[idx] = fn

    base_origin = str(getattr(request, "base_url", "") or "").rstrip("/")
    api_origin = base_origin
    html_render_cache_dir = os.path.join(recipe_dir, "html_render_cache")
    os.makedirs(html_render_cache_dir, exist_ok=True)

    items: List[Dict[str, Any]] = []
    for i, pdf_img_path in enumerate(pdf_imgs):
        has_html = i in html_map
        if m == "dynamic_replace":
            if has_html:
                items.append({"kind": "html", "page_index": i, "html_file": html_map[i]})
            else:
                items.append({"kind": "pdf", "page_index": i, "pdf_img": pdf_img_path})
        elif m == "dynamic_prepend":
            if has_html:
                items.append({"kind": "html", "page_index": i, "html_file": html_map[i]})
            items.append({"kind": "pdf", "page_index": i, "pdf_img": pdf_img_path})
        else:
            items.append({"kind": "pdf", "page_index": i, "pdf_img": pdf_img_path})
            if has_html:
                items.append({"kind": "html", "page_index": i, "html_file": html_map[i]})

    rendered_imgs: List[str] = []
    render_report: Dict[str, Any] = {"mode": m, "slides": []}

    for it in items:
        if it.get("kind") == "pdf":
            rendered_imgs.append(str(it.get("pdf_img") or ""))
            continue

        fn = str(it.get("html_file") or "")
        html_path = os.path.join(html_dir, fn)
        if not fn or not os.path.exists(html_path):
            continue
        url = f"{api_origin}/api/v1/projects/{project_id}/html/{urllib.parse.quote(fn)}"
        rr = await render_html_slide_to_png_async(
            html_url=url,
            html_path=html_path,
            project_id=project_id,
            cache_dir=html_render_cache_dir,
            html_filename=fn,
            options=HtmlRenderOptions(dpr=int(dpr), timeout_ms=int(timeout_ms), rewrite_project_id_assets=bool(rewrite_assets)),
        )
        render_report["slides"].append({"page_index": int(it.get("page_index") or 0), "html_file": fn, **rr})
        if not rr.get("success"):
            raise HTTPException(status_code=500, detail=str(rr.get("error") or "HTML render failed"))
        png_path = str(rr.get("png_path") or "")
        if not png_path or not os.path.exists(png_path):
            raise HTTPException(status_code=500, detail="HTML render produced no png")
        rendered_imgs.append(png_path)

    rendered_imgs = [p for p in rendered_imgs if p and os.path.exists(p)]
    if not rendered_imgs:
        raise HTTPException(status_code=404, detail="No pages to export")

    out_path = os.path.join(export_dir, f"slides_{m}.pptx")
    report_path = os.path.join(export_dir, f"slides_{m}.render.json")
    try:
        os.makedirs(export_dir, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(render_report, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    _build_pptx_from_images(rendered_imgs, out_path)
    return FileResponse(out_path, filename=f"{p['name']}_{m}.pptx")


@router.get("/{project_id}/export/project.zip")
async def export_project_zip(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    export_dir = os.path.join(p["path"], "recipe", "exports")
    zip_path = os.path.join(export_dir, "project.zip")
    _zip_dir(p["path"], zip_path)
    return FileResponse(zip_path, filename=f"{p['name']}_project.zip")


@router.get("/{project_id}/export/html.zip")
async def export_html_zip(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    recipe_dir = os.path.join(p["path"], "recipe")
    html_dir = os.path.join(recipe_dir, "html_slides")
    cache_dir = os.path.join(recipe_dir, "preview_cache")
    meta_path = os.path.join(recipe_dir, "html_meta.json")
    if not os.path.isdir(html_dir):
        raise HTTPException(status_code=404, detail="HTML not found. Generate first.")
    if not os.path.isdir(cache_dir):
        raise HTTPException(status_code=404, detail="Preview images not found. Compile first.")

    export_dir = os.path.join(recipe_dir, "exports")
    zip_path = os.path.join(export_dir, "html.zip")
    _zip_paths(
        [
            {"src": html_dir, "arc": "html_slides"},
            {"src": cache_dir, "arc": "preview_cache"},
            {"src": meta_path, "arc": "html_meta.json"},
        ],
        zip_path,
    )
    return FileResponse(zip_path, filename=f"{p['name']}_html.zip")
