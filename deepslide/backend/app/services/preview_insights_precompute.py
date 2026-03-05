import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.services.preview_metrics_service import compute_preview_metrics
from app.services.preview_insights_service import generate_audience_questions, generate_preview_coach_advice, _build_client


_LOCK = threading.Lock()
_STATE: Dict[str, Dict[str, Any]] = {}
_DEFAULT_LANG = "en"


def _recipe_dir(project_path: str) -> str:
    r = os.path.join(project_path, "recipe")
    return r if os.path.exists(r) else project_path


def _insights_dir(project_path: str) -> str:
    return os.path.join(_recipe_dir(project_path), "preview_insights")


def _paths(project_path: str) -> Dict[str, str]:
    base = _insights_dir(project_path)
    return {
        "dir": base,
        "metrics": os.path.join(base, "metrics.json"),
        "coach": os.path.join(base, "coach.json"),
        "questions": os.path.join(base, "questions.json"),
        "status": os.path.join(base, "status.json"),
    }


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _input_mtimes(project_path: str) -> Dict[str, float]:
    recipe = _recipe_dir(project_path)
    deps = [
        os.path.join(recipe, "base.pdf"),
        os.path.join(recipe, "content.tex"),
        os.path.join(recipe, "speech.txt"),
        os.path.join(recipe, "html_meta.json"),
        os.path.join(recipe, "alignment_dsid.json"),
    ]
    out: Dict[str, float] = {}
    for p in deps:
        bn = os.path.basename(p)
        try:
            out[bn] = float(os.path.getmtime(p)) if os.path.exists(p) else 0.0
        except Exception:
            out[bn] = 0.0
    return out


def _is_stale(project_path: str, lang: str) -> bool:
    ps = _paths(project_path)
    st = _safe_read_json(ps["status"])
    if not st or not isinstance(st.get("input_mtimes"), dict):
        return True
    saved_lang = str(st.get("lang") or "")
    if not saved_lang:
        return True
    if saved_lang != str(lang or ""):
        return True
    return dict(st["input_mtimes"]) != _input_mtimes(project_path)


def _content_pages(project_path: str, total_pages: int) -> List[int]:
    recipe = _recipe_dir(project_path)
    alignment = _safe_read_json(os.path.join(recipe, "alignment_dsid.json")) or {}
    metas = alignment.get("page_meta_by_page") if isinstance(alignment.get("page_meta_by_page"), list) else None
    if not metas:
        return list(range(total_pages))
    out: List[int] = []
    for i, m in enumerate(metas):
        if i >= total_pages:
            break
        if isinstance(m, dict) and str(m.get("type") or "") == "content":
            out.append(i)
    return out if out else list(range(total_pages))


def get_preview_insights_status(project_id: str, project_path: str) -> Dict[str, Any]:
    with _LOCK:
        st = _STATE.get(project_id)
        if st and st.get("status") in {"queued", "running"}:
            return dict(st)
    ps = _paths(project_path)
    ready = {
        "metrics": os.path.exists(ps["metrics"]),
        "coach": os.path.exists(ps["coach"]),
        "questions": os.path.exists(ps["questions"]),
    }
    stale = _is_stale(project_path, _DEFAULT_LANG) if any(ready.values()) else True
    saved = _safe_read_json(ps["status"]) or {}
    return {
        "status": "done" if all(ready.values()) and not stale else ("stale" if any(ready.values()) else "missing"),
        "ready": ready,
        "stale": bool(stale),
        "lang": str(saved.get("lang") or _DEFAULT_LANG),
        "input_mtimes": saved.get("input_mtimes") if isinstance(saved.get("input_mtimes"), dict) else _input_mtimes(project_path),
        "updated_at": saved.get("updated_at"),
        "llm": saved.get("llm") if isinstance(saved.get("llm"), dict) else {},
        "error": saved.get("error"),
    }


def _run_prepare(project_id: str, project_record: Dict[str, Any], include_llm: bool, force: bool, lang: str) -> None:
    project_path = str((project_record or {}).get("path") or "")
    ps = _paths(project_path)
    os.makedirs(ps["dir"], exist_ok=True)

    with _LOCK:
        _STATE[project_id] = {
            "status": "running",
            "stage": "metrics",
            "progress": {"current": 0, "total": 1},
            "error": None,
            "started_at": time.time(),
        }

    try:
        stale = _is_stale(project_path, lang)
        if not force and not stale and os.path.exists(ps["metrics"]) and os.path.exists(ps["coach"]) and os.path.exists(ps["questions"]):
            with _LOCK:
                _STATE[project_id] = {"status": "done", "stage": "done", "progress": {"current": 1, "total": 1}, "error": None}
            return

        metrics = compute_preview_metrics(project_record)
        if not metrics.get("ok"):
            raise RuntimeError(str(metrics.get("error") or "metrics_failed"))
        _atomic_write_json(
            ps["metrics"],
            {"_meta": {"version": 1, "lang": str(lang or ""), "input_mtimes": _input_mtimes(project_path)}, "data": metrics},
        )

        per_slide = metrics.get("per_slide") if isinstance(metrics, dict) else None
        total_pages = len(per_slide) if isinstance(per_slide, list) else 0
        if total_pages <= 0:
            raise RuntimeError("no_pages")

        pages = _content_pages(project_path, total_pages)
        llm_coach_ok = bool(_build_client("PREVIEW_COACH"))
        llm_q_ok = bool(_build_client("AUDIENCE_QA"))
        llm_enabled = bool(include_llm)

        coach_by_page: Dict[str, List[str]] = {}
        coach_err: Dict[str, str] = {}
        questions_by_page: Dict[str, List[str]] = {}
        questions_err: Dict[str, str] = {}

        with _LOCK:
            _STATE[project_id] = {
                "status": "running",
                "stage": "llm" if llm_enabled else "persist",
                "progress": {"current": 0, "total": len(pages) * (2 if llm_enabled else 0)},
                "error": None,
                "started_at": _STATE.get(project_id, {}).get("started_at"),
            }

        for i in pages:
            coach_by_page[str(i)] = []
            questions_by_page[str(i)] = []

        if llm_enabled and (llm_coach_ok or llm_q_ok):
            cur = 0
            tot = len(pages) * (2 if (llm_coach_ok and llm_q_ok) else 1)
            for i in pages:
                if llm_coach_ok:
                    try:
                        coach_by_page[str(i)] = generate_preview_coach_advice(project_record, int(i), metrics)
                    except Exception as e:
                        coach_err[str(i)] = str(e)
                        coach_by_page[str(i)] = []
                    cur += 1
                    with _LOCK:
                        s = _STATE.get(project_id) or {}
                        s["progress"] = {"current": cur, "total": tot}
                        _STATE[project_id] = s

                if llm_q_ok:
                    try:
                        questions_by_page[str(i)] = generate_audience_questions(project_record, int(i), metrics)
                    except Exception as e:
                        questions_err[str(i)] = str(e)
                        questions_by_page[str(i)] = []
                    cur += 1
                    with _LOCK:
                        s = _STATE.get(project_id) or {}
                        s["progress"] = {"current": cur, "total": tot}
                        _STATE[project_id] = s

        now = time.time()
        status_payload = {
            "version": 1,
            "updated_at": now,
            "lang": str(lang or ""),
            "input_mtimes": _input_mtimes(project_path),
            "pages": pages,
            "llm": {"enabled": bool(llm_enabled), "coach": bool(llm_coach_ok), "questions": bool(llm_q_ok)},
            "error": None,
        }
        _atomic_write_json(ps["coach"], {"version": 1, "updated_at": now, "lang": str(lang or ""), "by_page": coach_by_page, "errors_by_page": coach_err})
        _atomic_write_json(ps["questions"], {"version": 1, "updated_at": now, "lang": str(lang or ""), "by_page": questions_by_page, "errors_by_page": questions_err})
        _atomic_write_json(ps["status"], status_payload)

        with _LOCK:
            _STATE[project_id] = {"status": "done", "stage": "done", "progress": {"current": 1, "total": 1}, "error": None}
    except Exception as e:
        _atomic_write_json(
            ps["status"],
            {
                "version": 1,
                "updated_at": time.time(),
                "lang": str(lang or ""),
                "input_mtimes": _input_mtimes(project_path),
                "llm": {"enabled": bool(include_llm), "coach": False, "questions": False},
                "error": str(e),
            },
        )
        with _LOCK:
            _STATE[project_id] = {"status": "error", "stage": "error", "progress": {"current": 0, "total": 1}, "error": str(e)}


def start_prepare_preview_insights(project_id: str, project_record: Dict[str, Any], include_llm: bool = True, force: bool = False, lang: str = _DEFAULT_LANG) -> Dict[str, Any]:
    project_path = str((project_record or {}).get("path") or "")
    if not project_path or not os.path.isdir(project_path):
        return {"status": "error", "error": "Project path not found"}

    with _LOCK:
        st = _STATE.get(project_id)
        if st and st.get("status") in {"queued", "running"}:
            return dict(st)
        _STATE[project_id] = {"status": "queued", "stage": "queued", "progress": {"current": 0, "total": 1}, "error": None}

    th = threading.Thread(
        target=_run_prepare,
        args=(project_id, project_record, bool(include_llm), bool(force), str(lang or _DEFAULT_LANG)),
        daemon=True,
    )
    th.start()
    return {"status": "queued", "stage": "queued", "progress": {"current": 0, "total": 1}, "error": None}


def read_persisted_metrics(project_path: str) -> Optional[Dict[str, Any]]:
    ps = _paths(project_path)
    data = _safe_read_json(ps["metrics"])
    if not data or not isinstance(data.get("data"), dict):
        return None
    return dict(data["data"])


def read_persisted_by_page(project_path: str, kind: str) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    ps = _paths(project_path)
    p = ps.get(kind)
    data = _safe_read_json(p) if p else None
    by_page = data.get("by_page") if isinstance(data, dict) else None
    errs = data.get("errors_by_page") if isinstance(data, dict) else None
    return (dict(by_page) if isinstance(by_page, dict) else {}, dict(errs) if isinstance(errs, dict) else {})
