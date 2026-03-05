from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from .projects import get_project
from app.services.preview_metrics_service import compute_preview_metrics
from app.services.preview_insights_service import generate_audience_questions, generate_preview_coach_advice
from app.services.preview_insights_precompute import (
    get_preview_insights_status,
    read_persisted_by_page,
    read_persisted_metrics,
    start_prepare_preview_insights,
)


router = APIRouter()


class PreviewCoachRequest(BaseModel):
    page_index: int


class PreviewQuestionsRequest(BaseModel):
    page_index: int


class PreviewPrepareRequest(BaseModel):
    include_llm: bool = True
    force: bool = False
    lang: str = "en"


@router.get("/{project_id}/preview_insights/status")
async def get_preview_insights_status_api(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return get_preview_insights_status(project_id, p["path"])


@router.post("/{project_id}/preview_insights/prepare")
async def post_preview_insights_prepare(project_id: str, req: PreviewPrepareRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return start_prepare_preview_insights(project_id, p, include_llm=bool(req.include_llm), force=bool(req.force), lang=str(req.lang or "en"))


@router.get("/{project_id}/preview_insights/bundle")
async def get_preview_insights_bundle(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    metrics = read_persisted_metrics(p["path"])
    coach_by_page, coach_err = read_persisted_by_page(p["path"], "coach")
    questions_by_page, questions_err = read_persisted_by_page(p["path"], "questions")
    if not metrics or not metrics.get("ok"):
        raise HTTPException(status_code=404, detail="Metrics not prepared. Call prepare first.")
    if not coach_by_page and not questions_by_page:
        raise HTTPException(status_code=404, detail="Insights not prepared. Call prepare first.")
    status = get_preview_insights_status(project_id, p["path"])
    return {
        "ok": True,
        "status": status,
        "metrics": metrics,
        "coach": {"by_page": coach_by_page, "errors_by_page": coach_err},
        "questions": {"by_page": questions_by_page, "errors_by_page": questions_err},
    }


@router.get("/{project_id}/preview_insights/metrics")
async def get_preview_metrics(project_id: str):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    cached = read_persisted_metrics(p["path"])
    if cached and cached.get("ok"):
        return cached
    data = compute_preview_metrics(p)
    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=data.get("error") or {"message": "metrics_failed"})
    return data


@router.get("/{project_id}/preview_insights/coach")
async def get_preview_coach(project_id: str, page_index: int = Query(...)):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    by_page, errs = read_persisted_by_page(p["path"], "coach")
    key = str(int(page_index))
    if key in by_page:
        return {"ok": True, "page_index": int(page_index), "advice": by_page.get(key) or [], "error": errs.get(key)}
    raise HTTPException(status_code=404, detail="Coach advice not prepared. Call prepare first.")


@router.post("/{project_id}/preview_insights/coach/regenerate")
async def post_preview_coach_regenerate(project_id: str, req: PreviewCoachRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    metrics = read_persisted_metrics(p["path"]) or compute_preview_metrics(p)
    if not metrics.get("ok"):
        raise HTTPException(status_code=400, detail=metrics.get("error") or {"message": "metrics_failed"})
    page_index = int(req.page_index)
    per_slide = metrics.get("per_slide") if isinstance(metrics, dict) else None
    if not isinstance(per_slide, list) or page_index < 0 or page_index >= len(per_slide):
        raise HTTPException(status_code=400, detail="Invalid page_index")
    try:
        advice = generate_preview_coach_advice(p, page_index, metrics)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Coach generation failed")
    return {"ok": True, "page_index": page_index, "advice": advice}


@router.get("/{project_id}/preview_insights/questions")
async def get_preview_questions(project_id: str, page_index: int = Query(...)):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    by_page, errs = read_persisted_by_page(p["path"], "questions")
    key = str(int(page_index))
    if key in by_page:
        return {"ok": True, "page_index": int(page_index), "questions": by_page.get(key) or [], "error": errs.get(key)}
    raise HTTPException(status_code=404, detail="Questions not prepared. Call prepare first.")


@router.post("/{project_id}/preview_insights/questions/regenerate")
async def post_preview_questions_regenerate(project_id: str, req: PreviewQuestionsRequest):
    p = get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    metrics = read_persisted_metrics(p["path"]) or compute_preview_metrics(p)
    if not metrics.get("ok"):
        raise HTTPException(status_code=400, detail=metrics.get("error") or {"message": "metrics_failed"})
    page_index = int(req.page_index)
    per_slide = metrics.get("per_slide") if isinstance(metrics, dict) else None
    if not isinstance(per_slide, list) or page_index < 0 or page_index >= len(per_slide):
        raise HTTPException(status_code=400, detail="Invalid page_index")
    try:
        questions = generate_audience_questions(p, page_index, metrics)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Questions generation failed")
    return {"ok": True, "page_index": page_index, "questions": questions}
