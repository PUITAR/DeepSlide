import streamlit as st
import streamlit.components.v1 as components
import os
import sys
import json
import datetime
import functools
from typing import Any, Dict, Optional

# global tool logs
TOOL_LOGS: list[str] = []

# --- Path Setup ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if ROOT not in sys.path:
    sys.path.append(ROOT)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Helper Functions ---

def _components_html(body: str, height: int = 600, scrolling: bool = True, key: str | None = None):
    try:
        if key is None:
            return components.html(body, height=height, scrolling=scrolling)
        return components.html(body, height=height, scrolling=scrolling, key=key)
    except TypeError:
        return components.html(body, height=height, scrolling=scrolling)

def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    log_msg = f"[{ts}] {msg}"
    TOOL_LOGS.append(log_msg)
    print(log_msg)  # Also print to terminal for debugging

def _wrap_tools(tools):
    wrapped = []
    
    cache: dict[tuple, str] = {}
    per_tool_counts: dict[str, int] = {}
    total_count: int = 0
    PER_TOOL_LIMIT = 5
    TOTAL_LIMIT = 20
    
    def make_wrapper(fn):
        name = getattr(fn, "__name__", "tool")
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                TOOL_LOGS.append(f"[{ts}] call {name} args={args} kwargs={kwargs}")
                nonlocal total_count
                k = (name, json.dumps(args, ensure_ascii=False, default=str), json.dumps(kwargs, ensure_ascii=False, sort_keys=True, default=str))
                cnt = per_tool_counts.get(name, 0)
                
                if k in cache:
                    out = cache[k]
                    TOOL_LOGS.append(f"[{ts}] ret {name} (cached)")
                    return out
                if cnt >= PER_TOOL_LIMIT or total_count >= TOTAL_LIMIT:
                    out = "Tool budget exhausted"
                    TOOL_LOGS.append(f"[{ts}] ret {name} (budget)")
                    cache[k] = out
                    return out
                
                out = fn(*args, **kwargs)
                TOOL_LOGS.append(f"[{ts}] ret {name} -> {str(out)[:min(100, len(str(out)))]}...")
                per_tool_counts[name] = cnt + 1
                total_count += 1
                cache[k] = out if isinstance(out, str) else str(out)
                return out
            except Exception as e:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                TOOL_LOGS.append(f"[{ts}] error {name}: {e}")
                raise
        return wrapper
    for fn in tools:
        wrapped.append(make_wrapper(fn))
    return wrapped

def _init_state() -> None:
    if "collector" not in st.session_state:
        from ppt_requirements_collector import PPTRequirementsCollector
        st.session_state.collector = PPTRequirementsCollector()
    if "uploaded" not in st.session_state:
        st.session_state.uploaded = False
    if "app_state" not in st.session_state:
        st.session_state.app_state = "UPLOAD"
    if "logic_chain_json" not in st.session_state:
        st.session_state.logic_chain_json = None
    if "auto_generate_chain" not in st.session_state:
        st.session_state.auto_generate_chain = False
    if "edges_rec" not in st.session_state:
        from edges_recommender import EdgesRecommender
        st.session_state.edges_rec = EdgesRecommender()
    if "preview_state" not in st.session_state:
        st.session_state.preview_state = {
            "pdf_pages": [],
            "current_page": 0,
            "auto_play": False,
            "audio_ended": False
        }
    if "workflow_phase" not in st.session_state:
        st.session_state.workflow_phase = "EDITING"

def _requirements_json() -> dict:
    override = st.session_state.get("requirements_override")
    if override: return override
    req = st.session_state.collector.get_requirements()
    return req.get("conversation_requirements") or {}

BASE_TEX_TEMPLATE = r"""%!TeX encoding = UTF-8
%!TeX program = xelatex
\documentclass[notheorems, aspectratio=169]{beamer}
\usepackage{latexsym}
\usepackage{amsmath,amssymb}
\usepackage{mathtools}
\usepackage{color,xcolor}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{algorithm}
\usepackage{amsthm}
\usepackage{lmodern} 
\usepackage{listings}
\usepackage{tikz}
\mode<presentation>{
    \usetheme{Berkeley}
    \usecolortheme{dolphin}
    \useoutertheme{infolines}
    \useinnertheme{circles}
}
\input{title}
\begin{document}
\begin{frame}
    \titlepage
\end{frame}
\input{content.tex}
\end{document}
"""
