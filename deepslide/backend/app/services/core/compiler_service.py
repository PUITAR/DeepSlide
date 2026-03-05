from .tex_compile import (
    compile_content,
    update_title,
    update_base,
)

from colorama import Fore, Style

from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from camel.agents import ChatAgent
from camel.toolkits import FunctionTool
from app.core.model_config import build_model_config
from app.core.agent_model_env import resolve_text_llm_env

from .compiler_tools import CompilerTools

from dotenv import load_dotenv
import os
import logging
import re
import json
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

class CompilerService:

    def __init__(self, max_try: int = 3):
        self.max_try = max_try
        
        # backend/app/services/core -> deepslide-v3 -> ../.env
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../.env'))
        
        if os.path.exists(env_path):
            load_dotenv(env_path)
        
        cfg = resolve_text_llm_env("COMPILER")
        api_key = cfg.api_key
        if not api_key:
            logger.warning("LLM API Key not found. Compressor will not work properly.")
            self.llm_model = None
            return

        platform_type = cfg.platform_type
        model_type = cfg.model_type
        base_url = cfg.api_url

        # Initialize LLM
        try:
            model_platform = ModelPlatformType(platform_type)
        except Exception:
            model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL

        create_kwargs = {
            "model_platform": model_platform,
            "model_type": model_type,
            "api_key": api_key,
            "model_config_dict": build_model_config(
                model_type=model_type,
                temperature=0.0,
                max_tokens=8192,
            ),
        }
        if base_url:
            create_kwargs["url"] = base_url

        self.llm = ModelFactory.create(**create_kwargs)

    def _ensure_dsid_support(self, base_dir: str) -> None:
        base_path = os.path.join(base_dir, "base.tex")
        if not os.path.exists(base_path):
            return
        try:
            with open(base_path, "r", encoding="utf-8", errors="ignore") as f:
                base_tex = f.read() or ""
        except Exception:
            return

        sentinel = "\\providecommand{\\deepslideid}[1]{}"
        desired_sig = "\\AtBeginEnvironment{frame}"

        def _build_inject() -> str:
            return (
                "\n"
                + "\\providecommand{\\deepslideid}[1]{}\n"
                + "\\providecommand{\\deepslideidvalue}{}\n"
                + "\\renewcommand{\\deepslideid}[1]{\\gdef\\deepslideidvalue{#1}}\n"
                + "\\makeatletter\n"
                + "\\@ifundefined{AtBeginEnvironment}{}{\\AtBeginEnvironment{frame}{\\gdef\\deepslideidvalue{}}}\n"
                + "\\makeatother\n"
                + "\\setbeamertemplate{footline}{\\hfill\\ifx\\deepslideidvalue\\empty\\else{\\color{black!10}\\fontsize{8}{8}\\selectfont DSID:\\deepslideidvalue}\\fi\\hspace{6pt}}\n"
            )

        if (
            sentinel in base_tex
            and desired_sig in base_tex
            and "DSID:" in base_tex
            and "\\AtBeginEnvironment{frame}{\\gdef\\deepslideidvalue{}" in base_tex
        ):
            return

        new_tex = base_tex
        try:
            new_tex = re.sub(
                r"\\newcommand\{\\deepslideid\}\[1\]\{[^\n]*\}\s*",
                "",
                new_tex,
                flags=re.MULTILINE,
            )
            new_tex = re.sub(
                r"\\providecommand\{\\deepslideid\}\[1\]\{\}\s*\\renewcommand\{\\deepslideid\}\[1\]\{[\s\S]*?\\end\{tikzpicture\}\s*\}\s*",
                "",
                new_tex,
                flags=re.MULTILINE,
            )
            new_tex = re.sub(
                r"\\providecommand\{\\deepslideid\}\[1\]\{\}\s*\\renewcommand\{\\deepslideid\}\[1\]\{[\s\S]*?\\AddToShipoutPictureFG\*\{[\s\S]*?\}\s*\}\s*",
                "",
                new_tex,
                flags=re.MULTILINE,
            )
            new_tex = re.sub(
                r"\\providecommand\{\\deepslideid\}\[1\]\{\}\s*\\renewcommand\{\\deepslideid\}\[1\]\{[\s\S]*?\\AddToShipoutPictureFG\{[\s\S]*?\}\s*\}\s*",
                "",
                new_tex,
                flags=re.MULTILINE,
            )
        except Exception:
            new_tex = base_tex

        inject = _build_inject()

        if "\\begin{document}" in new_tex:
            new_tex = new_tex.replace("\\begin{document}", inject + "\\begin{document}", 1)
        else:
            new_tex = new_tex + inject

        if new_tex != base_tex:
            with open(base_path, "w", encoding="utf-8") as f:
                f.write(new_tex)

    def _inject_dsid_into_content(self, base_dir: str) -> Dict[str, Any]:
        content_path = os.path.join(base_dir, "content.tex")
        if not os.path.exists(content_path):
            return {"success": False, "reason": "missing_content"}
        try:
            with open(content_path, "r", encoding="utf-8", errors="ignore") as f:
                tex = f.read() or ""
        except Exception:
            return {"success": False, "reason": "read_failed"}

        pat = re.compile(r"(\\begin\{frame\}(?:\[[^\]]*\])?)")
        out: List[str] = []
        pos = 0
        idx = 0
        changed = False
        for m in pat.finditer(tex):
            out.append(tex[pos : m.end()])
            idx += 1
            lookahead = tex[m.end() : m.end() + 240]
            if "\\deepslideid{" not in lookahead:
                out.append(f"\n\\deepslideid{{S{idx:04d}}}\n")
                changed = True
            pos = m.end()
        out.append(tex[pos:])
        new_tex = "".join(out)
        if changed and new_tex != tex:
            with open(content_path, "w", encoding="utf-8") as f:
                f.write(new_tex)
        return {"success": True, "frames": idx, "modified": bool(changed)}

    def _extract_dsid_index(self, page_text: str) -> Optional[int]:
        m = re.search(r"DSID\s*:\s*S\s*(\d{1,6})", str(page_text or ""), flags=re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    def _parse_title_from_title_tex(self, title_tex: str) -> str:
        m = re.search(r"\\title\{([^}]*)\}", str(title_tex or ""))
        if m:
            return " ".join(m.group(1).split()).strip()
        return ""

    def _classify_extra_page(self, page_text: str, page_index: int, page_count: int) -> Dict[str, Any]:
        t = str(page_text or "")
        low = t.lower()
        if page_index == 0:
            return {"type": "title", "label": ""}
        if "bibliograph" in low or "references" in low or "参考文献" in t:
            return {"type": "references", "label": "References"}
        if "outline" in low or "contents" in low or "table of contents" in low or "目录" in t:
            return {"type": "outline", "label": "Outline"}
        head = ""
        parts = [x for x in re.split(r"\s{2,}|\n", t) if x.strip()]
        if parts:
            head = parts[0].strip()
        if head and len(head) <= 64 and len(t.split()) <= 40:
            return {"type": "section", "label": head}
        if page_index == page_count - 1:
            return {"type": "ending", "label": ""}
        return {"type": "extra", "label": head[:64]}

    def _read_requirements_context(self, source_dir: Optional[str]) -> str:
        if not source_dir or not os.path.isdir(source_dir):
            return ""
        candidates = [
            os.path.join(source_dir, "need.txt"),
            os.path.join(source_dir, "requirements.txt"),
            os.path.join(source_dir, "requirements.md"),
            os.path.join(source_dir, "prompt.txt"),
        ]
        for p in candidates:
            try:
                if os.path.exists(p) and os.path.isfile(p):
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        return (f.read() or "").strip()[:2000]
            except Exception:
                continue
        return ""

    def _llm_generate_extra_page_speech(
        self,
        page_meta: Dict[str, Any],
        title: str,
        page_text: str,
        requirements_context: str,
    ) -> str:
        fallback_type = str(page_meta.get("type") or "")
        label = str(page_meta.get("label") or "").strip()

        if not getattr(self, "llm", None):
            if fallback_type == "title":
                return f"Hello everyone. Today I'll present {title or 'my research'} in a concise format, focusing on methods and results."
            if fallback_type == "outline":
                return "I will briefly cover the method first, then focus on the key experimental results and takeaways."
            if fallback_type == "section":
                return f"Next, I will move on to {label or 'the next section'}."
            if fallback_type == "references":
                return "The references are listed here. I’m happy to discuss details during Q&A."
            if fallback_type == "ending":
                return "In one sentence: this work proposes a method and validates its core contribution with experimental results."
            return "This is a brief transition slide; I will highlight the key point and move on."

        sys = (
            "You are a presentation narration assistant. "
            "Generate 1-2 spoken sentences for the CURRENT PDF page. "
            "The page may be a beamer-inserted extra page (title/outline/section divider/references). "
            "Requirements:\n"
            "- Output English only.\n"
            "- Concise and information-dense.\n"
            "- Do NOT mention DSID, LaTeX, beamer, or implementation details.\n"
            "- Do NOT include '<next>' or markdown.\n"
            "- If user requirements specify timing/sections, follow them.\n"
            "- For references pages, politely defer details to Q&A.\n"
        )
        payload = {
            "paper_title": title,
            "page_type": page_meta.get("type"),
            "page_label": page_meta.get("label"),
            "page_text_excerpt": str(page_text or "")[:600],
            "user_requirements_context": str(requirements_context or "")[:1200],
        }
        user = json.dumps(payload, ensure_ascii=False)

        try:
            sys_msg = BaseMessage.make_assistant_message(role_name="System", content=sys)
            user_msg = BaseMessage.make_user_message(role_name="User", content=user)
            agent = ChatAgent(system_message=sys_msg, model=self.llm)
            resp = agent.step(user_msg)
            out = str(resp.msg.content or "").strip()
            out = re.sub(r"\s+", " ", out)
            out = re.sub(r"<next>", " ", out, flags=re.IGNORECASE).strip()
            if not out:
                raise RuntimeError("empty")
            return out[:360]
        except Exception:
            return "This is a brief transition slide; I will highlight the key point and move on."

    def align_speech_to_pdf_pages(self, base_dir: str, source_dir: Optional[str] = None) -> Dict[str, Any]:
        pdf_path = os.path.join(base_dir, "base.pdf")
        speech_path = os.path.join(base_dir, "speech.txt")
        title_path = os.path.join(base_dir, "title.tex")

        if not os.path.exists(pdf_path):
            return {"success": False, "reason": "missing_pdf"}

        try:
            import fitz

            doc = fitz.open(pdf_path)
            page_texts: List[str] = []
            for i in range(doc.page_count):
                try:
                    page = doc.load_page(int(i))
                    txt = page.get_text("text") or ""
                except Exception:
                    txt = ""
                page_texts.append(" ".join(str(txt).split()))
            doc.close()
        except Exception:
            return {"success": False, "reason": "read_pdf_failed"}

        page_count = len(page_texts)

        speeches: List[str] = []
        try:
            with open(speech_path, "r", encoding="utf-8", errors="ignore") as f:
                speeches = [x.strip() for x in (f.read() or "").split("<next>")]
        except Exception:
            speeches = []

        title_tex = ""
        try:
            with open(title_path, "r", encoding="utf-8", errors="ignore") as f:
                title_tex = f.read() or ""
        except Exception:
            title_tex = ""
        title = self._parse_title_from_title_tex(title_tex)
        requirements_context = self._read_requirements_context(source_dir)

        dsid_by_page: List[Optional[int]] = []
        content_pages = 0
        for txt in page_texts:
            sid = self._extract_dsid_index(txt)
            dsid_by_page.append(sid)
            if sid is not None:
                content_pages += 1

        speech_by_page: List[str] = []
        already_page_aligned = len(speeches) == page_count
        extra_cache: Dict[str, str] = {}

        if already_page_aligned:
            base = list(speeches)
            if len(base) < page_count:
                base.extend([""] * (page_count - len(base)))
            base = base[:page_count]
            for i in range(page_count):
                if str(base[i]).strip():
                    speech_by_page.append(str(base[i]).strip())
                    continue
                if dsid_by_page[i] is not None:
                    speech_by_page.append("I will briefly walk through the key content on this slide and then move on.")
                else:
                    meta = self._classify_extra_page(page_texts[i], i, page_count)
                    cache_key = f"{meta.get('type')}|{meta.get('label')}"
                    if cache_key in extra_cache:
                        speech_by_page.append(extra_cache[cache_key])
                    else:
                        s = self._llm_generate_extra_page_speech(meta, title, page_texts[i], requirements_context)
                        extra_cache[cache_key] = s
                        speech_by_page.append(s)
        else:
            for i in range(page_count):
                sid = dsid_by_page[i]
                if sid is not None and 1 <= sid <= len(speeches) and str(speeches[sid - 1]).strip():
                    speech_by_page.append(str(speeches[sid - 1]).strip())
                else:
                    meta = self._classify_extra_page(page_texts[i], i, page_count)
                    cache_key = f"{meta.get('type')}|{meta.get('label')}"
                    if cache_key in extra_cache:
                        speech_by_page.append(extra_cache[cache_key])
                    else:
                        s = self._llm_generate_extra_page_speech(meta, title, page_texts[i], requirements_context)
                        extra_cache[cache_key] = s
                        speech_by_page.append(s)

        speech_by_page = [re.sub(r"<next>", " ", str(x or "")).strip() for x in speech_by_page]
        speech_str = "\n<next>\n".join(speech_by_page)
        try:
            with open(speech_path, "w", encoding="utf-8") as f:
                f.write(speech_str)
        except Exception:
            return {"success": False, "reason": "write_speech_failed"}

        alignment = {
            "success": True,
            "pages": page_count,
            "speech_pages": len(speech_by_page),
            "content_pages_with_dsid": content_pages,
            "dsid_by_page": dsid_by_page,
            "extra_pages": [i for i, sid in enumerate(dsid_by_page) if sid is None],
        }
        try:
            with open(os.path.join(base_dir, "alignment_dsid.json"), "w", encoding="utf-8") as f:
                json.dump(alignment, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return alignment
        
    def _attempt_fix(self, base_dir: str, errors: List[Dict[str, Any]]) -> bool:
        """
        Attempt to fix errors.
        Priority 1: Fast regex/heuristic fixes.
        Priority 2: AI Agent with tools.
        """
        if not errors: return False
        
        # Only process the first error to avoid cascading issues
        error = errors[0]
        msg = error.get('message', '')
        file = error.get('file', 'unknown')
        line = error.get('line', None)
        
        logger.info(f"🔧 Attempting fix for: {msg} in {file}:{line}")

        # --- Priority 1: Fast Heuristics ---

        # 1. & -> \&
        if "Misplaced alignment tab character &" in msg:
            if self._fast_fix_misplaced_ampersand(base_dir, line if file == 'content.tex' else None):
                return True

        # 2. Undefined control sequence
        if "Undefined control sequence" in msg:
             if self._fast_fix_booktabs(base_dir):
                 return True
             # Case A: \captionof -> \usepackage{capt-of}
             if self._fast_fix_captionof(base_dir):
                 return True
        
        # 3. Missing $ inserted (Math mode)
        if "Missing $ inserted" in msg:
            # Try fast fix on content.tex regardless of file reported (often reports base.tex/toc)
            if self._fast_fix_math_mode(base_dir, line if file == 'content.tex' else None):
                return True

        # 4. Lonely \item (Missing environment)
        if "Lonely \\item" in msg or "Something's wrong--perhaps a missing \\item" in msg:
            if self._fast_fix_itemize(base_dir, line if file == 'content.tex' else None):
                return True
        
        # 5. Fragile frame (Verbatim usage)
        if "File ended while scanning use of" in msg or "Forbidden control sequence found" in msg:
             # Often caused by verbatim in frame without [fragile]
             if self._fast_fix_fragile_frame(base_dir):
                 return True

        if "Illegal parameter number in definition" in msg and "parchment" in msg:
            if self._fast_fix_parchment_env(base_dir):
                return True

        # 6. Missing Image (Runtime error)
        # "File `xxx' not found" or "Unable to load picture"
        if "File" in msg and "not found" in msg or "Unable to load picture" in msg:
            if self._fast_fix_missing_image(base_dir, msg):
                return True
        
        # 7. Unicode errors
        if "Unicode char" in msg:
            if self._fast_fix_utf8(base_dir, msg):
                return True

        # --- Priority 2: AI Agent ---
        if getattr(self, 'llm', None):
            return self._fix_with_agent(base_dir, error)
        
        return False

    def _fast_fix_captionof(self, base_dir: str) -> bool:
        """Fix missing \\captionof by adding \\usepackage{capt-of} to base.tex."""
        try:
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False
            
            # Verify usage
            with open(content_path, 'r', encoding='utf-8') as f:
                if "captionof" not in f.read():
                    return False

            base_path = os.path.join(base_dir, "base.tex")
            if not os.path.exists(base_path): return False
            
            with open(base_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if r"\usepackage{capt-of}" in content or r"\usepackage{caption}" in content:
                return False
            
            # Insert package
            if r"\usepackage{capt-of}" not in content:
                new_content = re.sub(r'(\\documentclass.*?\]\{beamer\})', r'\1\n\\usepackage{capt-of}', content, count=1)
                if new_content == content:
                    new_content = content.replace(r'\begin{document}', r'\usepackage{capt-of}' + '\n' + r'\begin{document}')
                
                if new_content != content:
                    with open(base_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    logger.info("⚡ Fast Fix applied: Added \\usepackage{capt-of} to base.tex")
                    return True
        except Exception as e:
            logger.error(f"Fast fix captionof failed: {e}")
        return False

    def _fast_fix_booktabs(self, base_dir: str) -> bool:
        try:
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path):
                return False

            with open(content_path, "r", encoding="utf-8") as f:
                c = f.read()
            if "\\toprule" not in c and "\\midrule" not in c and "\\bottomrule" not in c:
                return False

            base_path = os.path.join(base_dir, "base.tex")
            if not os.path.exists(base_path):
                return False

            with open(base_path, "r", encoding="utf-8") as f:
                base = f.read()
            if r"\usepackage{booktabs}" in base:
                return False

            new_base = re.sub(r'(\\documentclass.*?\]\{beamer\})', r'\1\n\\usepackage{booktabs}', base, count=1)
            if new_base == base:
                new_base = base.replace(r"\begin{document}", r"\usepackage{booktabs}" + "\n" + r"\begin{document}")

            if new_base != base:
                with open(base_path, "w", encoding="utf-8") as f:
                    f.write(new_base)
                logger.info("⚡ Fast Fix applied: Added \\usepackage{booktabs} to base.tex")
                return True
        except Exception as e:
            logger.error(f"Fast fix booktabs failed: {e}")
        return False

    def _fast_fix_parchment_env(self, base_dir: str) -> bool:
        try:
            base_path = os.path.join(base_dir, "base.tex")
            if not os.path.exists(base_path):
                return False

            with open(base_path, "r", encoding="utf-8") as f:
                content = f.read()

            if "\\def\\parchmentframemiddle" not in content:
                return False

            new_content = re.sub(
                r'^\s*%\s*\\end\{pgfonlayer\}\}\}\s*$',
                r'  \\end{pgfonlayer}}}',
                content,
                flags=re.MULTILINE,
            )

            if new_content != content:
                with open(base_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                logger.info("⚡ Fast Fix applied: Un-commented \\end{pgfonlayer}}} in base.tex")
                return True
        except Exception as e:
            logger.error(f"Fast fix parchment env failed: {e}")
        return False

    def _fast_fix_misplaced_ampersand(self, base_dir: str, line_num: Optional[int]) -> bool:
        """Fix & -> \\& in content.tex."""
        try:
            # Cleanup .toc first
            toc_path = os.path.join(base_dir, "base.toc")
            if os.path.exists(toc_path):
                with open(toc_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if re.search(r'(?<!\\)&', f.read()):
                        try:
                            os.remove(toc_path)
                            logger.info("⚡ Fast Fix: Removed corrupted base.toc")
                        except: pass

            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False

            with open(content_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            fixed_any = False
            
            def needs_fix(text):
                return bool(re.search(r'(?<!\\)&', text))

            def fix_line(text):
                return re.sub(r'(?<!\\)&', r'\\&', text)

            if line_num is not None:
                idx = line_num - 1
                if 0 <= idx < len(lines):
                    if needs_fix(lines[idx]):
                        lines[idx] = fix_line(lines[idx])
                        fixed_any = True
                        logger.info(f"⚡ Fast Fix applied: Replaced & with \\& on line {line_num}")
            else:
                for idx, line in enumerate(lines):
                    if needs_fix(line):
                        if re.match(r'^\s*\\(section|subsection|frametitle|caption|item)', line):
                            lines[idx] = fix_line(line)
                            fixed_any = True
                        elif " & " in line and not line.strip().endswith(r'\\'):
                            lines[idx] = fix_line(line)
                            fixed_any = True

            if fixed_any:
                with open(content_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return True

        except Exception as e:
            logger.error(f"Fast fix ampersand failed: {e}")
        return False

    def _fast_fix_math_mode(self, base_dir: str, line_num: Optional[int]) -> bool:
        """
        Fix 'Missing $ inserted'.
        Common cause: using _ or ^ in text mode.
        Action: Normalize common math tokens in text mode (underscores, arrows).
        """
        try:
            # Cleanup .toc first (common source of Missing $)
            toc_path = os.path.join(base_dir, "base.toc")
            if os.path.exists(toc_path):
                try:
                    os.remove(toc_path)
                    logger.info("⚡ Fast Fix: Removed potential corrupted base.toc (Math Error)")
                except: pass

            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False
            if self._pre_sanitize_tex(base_dir):
                logger.info("⚡ Fast Fix applied: Pre-sanitize normalized arrows/underscores")
                return True
        except Exception:
            pass
        return False

    def _fast_fix_fragile_frame(self, base_dir: str) -> bool:
        """
        Fix 'File ended while scanning use of'.
        Common cause: Verbatim/lstlisting in frame without [fragile].
        """
        try:
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False

            with open(content_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            fixed_any = False
            
            # Naive state machine to track frames
            current_frame_start_idx = -1
            has_verbatim = False
            
            for i, line in enumerate(lines):
                if r'\begin{frame}' in line:
                    current_frame_start_idx = i
                    has_verbatim = False
                    # Check if already fragile
                    if '[fragile]' in line:
                        current_frame_start_idx = -1 # Ignore
                
                if current_frame_start_idx != -1:
                    if r'\begin{verbatim}' in line or r'\begin{lstlisting}' in line or r'\verb|' in line:
                        has_verbatim = True
                    
                    if r'\end{frame}' in line:
                        if has_verbatim:
                            # Apply fix to the start line
                            start_line = lines[current_frame_start_idx]
                            # Insert [fragile] after \begin{frame}
                            # Handle arguments like \begin{frame}{Title}
                            new_start_line = start_line.replace(r'\begin{frame}', r'\begin{frame}[fragile]', 1)
                            if new_start_line != start_line:
                                lines[current_frame_start_idx] = new_start_line
                                fixed_any = True
                                logger.info(f"⚡ Fast Fix applied: Added [fragile] to frame at line {current_frame_start_idx+1}")
                        
                        # Reset
                        current_frame_start_idx = -1
                        has_verbatim = False

            if fixed_any:
                with open(content_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return True
                
        except Exception as e:
            logger.error(f"Fast fix fragile failed: {e}")
        return False

    def _fast_fix_missing_image(self, base_dir: str, msg: str) -> bool:
        """
        Fix 'File ... not found' for images by creating a placeholder.
        """
        try:
            # Extract filename from msg
            match = re.search(r"File [`']([^']+)' not found", msg)
            if not match:
                match = re.search(r"file '([^']+)'", msg)
            
            if match:
                filename = match.group(1)
                # Call tool to create it
                ct = CompilerTools(base_dir)
                res = ct.create_image_placeholder(filename)
                logger.info(f"⚡ Fast Fix applied: {res}")
                return True
                
        except Exception as e:
            logger.error(f"Fast fix missing image failed: {e}")
        return False
        
    def _fast_fix_utf8(self, base_dir: str, msg: str) -> bool:
        """
        Fix Unicode errors.
        """
        try:
            # Simple fix: Replace non-ascii chars with ? or space in content.tex
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False
            
            with open(content_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Detect non-ascii
            # Regex for non-ascii
            new_content = re.sub(r'[^\x00-\x7F]+', '?', content)
            
            if new_content != content:
                with open(content_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                logger.info("⚡ Fast Fix applied: Replaced Unicode characters with '?'")
                return True
                
        except Exception as e:
            logger.error(f"Fast fix utf8 failed: {e}")
        return False

    def _fast_fix_itemize(self, base_dir: str, line_num: Optional[int]) -> bool:
        """
        Fix 'Lonely \\item'.
        Common cause: \\item used outside itemize/enumerate.
        """
        return False

    def _fix_with_agent(self, base_dir: str, error: Dict[str, Any]) -> bool:
        """
        Use an AI Agent with tools to diagnose and fix the error.
        """
        logger.info("🤖 Launching Compiler Agent...")

        def _clean_thought(text: str) -> str:
            if not text:
                return ""
            lines = []
            for ln in str(text).splitlines():
                if "additionalProperties" in ln:
                    continue
                if "\"type\": \"function\"" in ln or "'type': 'function'" in ln:
                    continue
                if "parameters" in ln and "required" in ln and "type" in ln:
                    continue
                lines.append(ln)
            out = "\n".join(lines).strip()
            if len(out) > 2200:
                return out[:2200] + "..."
            return out
        
        ct = CompilerTools(base_dir)
        
        tools = [
            FunctionTool(ct.read_file),
            FunctionTool(ct.write_file),
            FunctionTool(ct.list_files),
            FunctionTool(ct.grep_files),
            FunctionTool(ct.search_replace),
            FunctionTool(ct.run_python_script),
            FunctionTool(ct.create_image_placeholder),
            FunctionTool(ct.create_plot_image),
            FunctionTool(ct.check_balance),
            FunctionTool(ct.compile_pdf),
        ]
        
        sys_msg_content = """You are an expert LaTeX debugger.
Your goal is to fix the compilation error reported by the user.

You have access to file system tools and a compilation tool:
- `read_file(filename, start, end)`: Read file content.
- `write_file(filename, content)`: Overwrite the ENTIRE file.
- `search_replace(filename, old, new)`: Replace string occurrences.
- `list_files()`: List files in directory.
- `grep_files(pattern)`: Search for strings in files.
- `run_python_script(script_content)`: Execute Python code to manipulate files.
- `create_image_placeholder(filename)`: Create a dummy image if missing.
- `create_plot_image(filename, title, data_type)`: Create a chart (bar/line/scatter/pie) using python.
- `check_balance(filename)`: Check for unclosed environments or braces.
- `compile_pdf()`: Attempt to compile the PDF. Use this to verify your fixes.

Strategy:
1. THINK: Analyze the error message and the context.
2. OBSERVE: Use `grep_files`, `read_file`, or `check_balance` to locate the error.
   - NOTE: Log line numbers are often inaccurate for included files. Search for the code context.
3. ACT: Fix the error using the appropriate tools.
4. VERIFY: Call `compile_pdf()` to check if the error is resolved.
   - If `compile_pdf()` returns "SUCCESS", reply "FIXED".
   - If it fails, analyze the new error and repeat.
5. COMPLETE: If you cannot fix it after several attempts, explain why.

CRITICAL: Always output your thought process (THINK) before calling tools.
"""
        sys_msg = BaseMessage.make_assistant_message(
            role_name="Compiler Agent",
            content=sys_msg_content
        )
        
        agent = ChatAgent(system_message=sys_msg, model=self.llm, tools=tools)
        
        msg = error.get('message')
        file = error.get('file')
        line = error.get('line')
        
        prompt = f"""
LaTeX Compilation Error: {msg}
Reported File: {file}
Reported Line: {line}

Please diagnose and fix this error.
"""
        usr_msg = BaseMessage.make_user_message(role_name="User", content=prompt)
        
        max_steps = 15 
        step = 0
        
        while step < max_steps:
            try:
                response = agent.step(usr_msg)
                content = response.msg.content
                
                if content:
                    clean = _clean_thought(content)
                    if clean:
                        logger.info(f"\n🤖 [Agent Thought]\n{clean}")
                
                if "FIXED" in content:
                    logger.info("✅ Agent reported fix applied.")
                    return True
                
                if response.terminated:
                    break
                
                step += 1
                
            except Exception as e:
                logger.error(f"Agent step failed: {e}")
                break
                
        return False

    def _pre_check_images(self, base_dir: str, source_dir: str = None):
        """
        Pre-check all image paths in content.tex. 
        If an image path does not exist in base_dir, try to find it in the project and copy/fix it.
        """
        logger.info("🔍 Pre-checking image paths...")
        print("[pre_check_images] start")
        try:
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return
            
            with open(content_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Regex to find \includegraphics{path}
            img_pattern = re.compile(r'\\includegraphics(?:\[.*?\])?\{(?P<path>.*?)\}')
            
            matches = list(img_pattern.finditer(content))
            if not matches: return

            new_content = content
            replacements = {} # old_path -> new_path
            
            search_dirs = [
                os.path.join(base_dir),
                os.path.join(base_dir, "picture"),
            ]
            
            if source_dir and os.path.exists(source_dir):
                search_dirs.append(source_dir)
                for item in os.listdir(source_dir):
                    d = os.path.join(source_dir, item)
                    if os.path.isdir(d):
                        search_dirs.append(d)
            
            for m in matches:
                raw_path = m.group("path")
                if raw_path in replacements: continue # Already processed
                
                full_path = os.path.join(base_dir, raw_path)
                if os.path.exists(full_path): continue # OK
                
                logger.warning(f"⚠️ Image not found: {raw_path}. Searching...")
                print(f"[pre_check_images] missing {raw_path}")
                
                found_path = None
                filename = os.path.basename(raw_path)
                
                for d in search_dirs:
                    if not os.path.exists(d): continue
                    # 1. Exact match
                    p = os.path.join(d, filename)
                    if os.path.exists(p):
                        found_path = p
                        break
                    # 2. Recursive
                    for root, _, files in os.walk(d):
                        if filename in files:
                            found_path = os.path.join(root, filename)
                            break
                    if found_path: break
                
                if found_path:
                    dest_dir = os.path.join(base_dir, "picture")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, filename)
                    
                    if found_path != dest_path:
                        import shutil
                        shutil.copy2(found_path, dest_path)
                    
                    new_rel_path = f"picture/{filename}"
                    replacements[raw_path] = new_rel_path
                    logger.info(f"✅ Restored {raw_path} -> {new_rel_path}")
                    print(f"[pre_check_images] restored {raw_path} -> {new_rel_path}")
                else:
                    logger.error(f"❌ Could not find image: {filename}")
                    print(f"[pre_check_images] not_found {filename}")
            
            for old, new in replacements.items():
                new_content = new_content.replace(f"{{{old}}}", f"{{{new}}}")
            
            if new_content != content:
                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                logger.info("📝 Updated content.tex with fixed image paths.")
                print("[pre_check_images] updated content.tex")
                
        except Exception as e:
            logger.error(f"Pre-check images error: {e}")

    def _pre_sanitize_tex(self, base_dir: str) -> bool:
        content_path = os.path.join(base_dir, "content.tex")
        if not os.path.exists(content_path):
            return False
        try:
            with open(content_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return False

        MATH_ENVS = {
            "math",
            "displaymath",
            "equation",
            "equation*",
            "align",
            "align*",
            "aligned",
            "alignedat",
            "gather",
            "gather*",
            "multline",
            "multline*",
            "eqnarray",
            "eqnarray*",
            "flalign",
            "flalign*",
            "alignat",
            "alignat*",
            "split",
        }
        VERBATIM_ENVS = {
            "verbatim",
            "verbatim*",
            "Verbatim",
            "BVerbatim",
            "LVerbatim",
            "lstlisting",
            "minted",
        }
        SKIP_BRACED_COMMANDS = {
            "url",
            "path",
            "nolinkurl",
            "label",
            "ref",
            "eqref",
            "pageref",
            "autoref",
            "cref",
            "Cref",
            "cite",
            "citep",
            "citet",
            "parencite",
            "textcite",
            "footcite",
            "nocite",
            "bibitem",
        }
        SKIP_FIRST_ARG_COMMANDS = {"href"}
        VERB_LIKE_COMMANDS = {"verb", "lstinline"}

        def _make_initial_state() -> dict:
            return {
                "math_env_depth": 0,
                "verbatim_env_depth": 0,
                "in_dollar_math": False,
                "dollar_delim": "",
                "in_paren_math": False,
                "in_bracket_math": False,
            }

        def _parse_balanced_braces(s: str, open_brace_idx: int) -> Optional[tuple[str, int]]:
            if open_brace_idx >= len(s) or s[open_brace_idx] != "{":
                return None
            depth = 0
            i = open_brace_idx
            while i < len(s):
                ch = s[i]
                if ch == "\\":
                    i += 2
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return (s[open_brace_idx + 1 : i], i + 1)
                i += 1
            return None

        def _split_comment(line: str) -> tuple[str, str]:
            i = 0
            while i < len(line):
                if line[i] == "%":
                    if i > 0 and line[i - 1] == "\\":
                        i += 1
                        continue
                    return (line[:i], line[i:])
                i += 1
            return (line, "")

        scan_state = _make_initial_state()

        def _process_underscore_line(line: str, *, escape: bool) -> str:
            nonlocal scan_state

            if scan_state["verbatim_env_depth"] > 0:
                m = re.match(r"^\s*\\end\{([^}]+)\}", line)
                if m and m.group(1) in VERBATIM_ENVS:
                    scan_state["verbatim_env_depth"] = max(0, scan_state["verbatim_env_depth"] - 1)
                return line

            code, comment = _split_comment(line)
            out = []
            i = 0

            def in_math() -> bool:
                return (
                    scan_state["math_env_depth"] > 0
                    or scan_state["in_dollar_math"]
                    or scan_state["in_paren_math"]
                    or scan_state["in_bracket_math"]
                )

            def _consume_optional_brackets(s: str, start_idx: int) -> int:
                k = start_idx
                while k < len(s) and s[k].isspace():
                    k += 1
                while k < len(s) and s[k] == "[":
                    depth = 0
                    while k < len(s):
                        ch2 = s[k]
                        if ch2 == "\\":
                            k += 2
                            continue
                        if ch2 == "[":
                            depth += 1
                        elif ch2 == "]":
                            depth -= 1
                            if depth == 0:
                                k += 1
                                break
                        k += 1
                    while k < len(s) and s[k].isspace():
                        k += 1
                return k

            while i < len(code):
                ch = code[i]
                if ch == "\\":
                    if i + 1 >= len(code):
                        out.append(ch)
                        i += 1
                        continue

                    nxt = code[i + 1]
                    if nxt in ("(", ")", "[", "]"):
                        token = code[i : i + 2]
                        if token == r"\(":
                            scan_state["in_paren_math"] = True
                        elif token == r"\)":
                            scan_state["in_paren_math"] = False
                        elif token == r"\[":
                            scan_state["in_bracket_math"] = True
                        elif token == r"\]":
                            scan_state["in_bracket_math"] = False
                        out.append(token)
                        i += 2
                        continue

                    j = i + 1
                    if code[j].isalpha() or code[j] == "@":
                        while j < len(code) and (code[j].isalpha() or code[j] == "@"):
                            j += 1
                        cmd = code[i + 1 : j]
                    else:
                        cmd = code[j]
                        j += 1

                    out.append(code[i:j])
                    i = j

                    if cmd in ("begin", "end"):
                        k = i
                        while k < len(code) and code[k].isspace():
                            k += 1
                        if k < len(code) and code[k] == "{":
                            parsed = _parse_balanced_braces(code, k)
                            if parsed:
                                env_name, end_idx = parsed
                                out.append(code[k:end_idx])
                                i = end_idx
                                if cmd == "begin":
                                    if env_name in VERBATIM_ENVS:
                                        scan_state["verbatim_env_depth"] += 1
                                    if env_name in MATH_ENVS:
                                        scan_state["math_env_depth"] += 1
                                else:
                                    if env_name in VERBATIM_ENVS:
                                        scan_state["verbatim_env_depth"] = max(0, scan_state["verbatim_env_depth"] - 1)
                                    if env_name in MATH_ENVS:
                                        scan_state["math_env_depth"] = max(0, scan_state["math_env_depth"] - 1)
                        continue

                    if cmd in SKIP_BRACED_COMMANDS:
                        k = _consume_optional_brackets(code, i)
                        if k < len(code) and code[k] == "{":
                            parsed = _parse_balanced_braces(code, k)
                            if parsed:
                                _, end_idx = parsed
                                out.append(code[k:end_idx])
                                i = end_idx
                        continue

                    if cmd in SKIP_FIRST_ARG_COMMANDS:
                        k = _consume_optional_brackets(code, i)
                        if k < len(code) and code[k] == "{":
                            parsed = _parse_balanced_braces(code, k)
                            if parsed:
                                _, end_idx = parsed
                                out.append(code[k:end_idx])
                                i = end_idx
                        continue

                    if cmd in VERB_LIKE_COMMANDS:
                        k = i
                        if k < len(code) and code[k] == "*":
                            out.append("*")
                            k += 1
                            i = k
                        if i < len(code):
                            delim = code[i]
                            out.append(delim)
                            i += 1
                            start = i
                            while i < len(code) and code[i] != delim:
                                i += 1
                            out.append(code[start:i])
                            if i < len(code) and code[i] == delim:
                                out.append(delim)
                                i += 1
                        continue

                    continue

                if ch == "$":
                    if i + 1 < len(code) and code[i + 1] == "$":
                        token = "$$"
                        if scan_state["in_dollar_math"] and scan_state["dollar_delim"] == "$$":
                            scan_state["in_dollar_math"] = False
                            scan_state["dollar_delim"] = ""
                        elif not scan_state["in_dollar_math"]:
                            scan_state["in_dollar_math"] = True
                            scan_state["dollar_delim"] = "$$"
                        out.append(token)
                        i += 2
                    else:
                        token = "$"
                        if scan_state["in_dollar_math"] and scan_state["dollar_delim"] == "$":
                            scan_state["in_dollar_math"] = False
                            scan_state["dollar_delim"] = ""
                        elif not scan_state["in_dollar_math"]:
                            scan_state["in_dollar_math"] = True
                            scan_state["dollar_delim"] = "$"
                        out.append(token)
                        i += 1
                    continue

                if ch == "_" and escape:
                    out.append("_" if in_math() else r"\_")
                    i += 1
                    continue

                out.append(ch)
                i += 1

            return "".join(out) + comment

        in_block = False
        changed = False
        out: List[str] = []
        for ln in lines:
            t = str(ln)
            if not in_block and (
                r"\begin{verbatim}" in t
                or r"\begin{lstlisting}" in t
                or r"\begin{minted}" in t
                or r"\begin{Verbatim}" in t
            ):
                in_block = True
                out.append(t)
                continue
            if in_block:
                out.append(t)
                if (
                    r"\end{verbatim}" in t
                    or r"\end{lstlisting}" in t
                    or r"\end{minted}" in t
                    or r"\end{Verbatim}" in t
                ):
                    in_block = False
                continue

            t2 = t
            t2 = t2.replace("→", r"\ensuremath{\rightarrow}")
            t2 = t2.replace("←", r"\ensuremath{\leftarrow}")
            t2 = t2.replace("⇒", r"\ensuremath{\Rightarrow}")
            t2 = t2.replace("⇐", r"\ensuremath{\Leftarrow}")
            t2 = re.sub(
                r"\\(rightarrow|leftarrow|Rightarrow|Leftarrow|leftrightarrow|Leftrightarrow)\b",
                r"\\ensuremath{\\\1}",
                t2,
            )
            t2 = _process_underscore_line(t2, escape=True)
            if t2 != t:
                changed = True
            out.append(t2)

        if not changed:
            return False
        try:
            with open(content_path, "w", encoding="utf-8") as f:
                f.writelines(out)
            return True
        except Exception:
            return False

    def run(self, base_dir: str, source_dir: str = None):
        """
        Compile the LaTeX document in the `base_dir`.
        """
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(backend_root, base_dir)
        base_dir = os.path.abspath(base_dir)

        if source_dir is not None and not os.path.isabs(source_dir):
            source_dir = os.path.join(backend_root, source_dir)
        if source_dir is not None:
            source_dir = os.path.abspath(source_dir)

        if not os.path.exists(base_dir):
            return {"success": False, "errors": [{"message": f"Recipe directory not found: {base_dir}"}]}

        try:
            self._ensure_dsid_support(base_dir)
            self._inject_dsid_into_content(base_dir)
        except Exception:
            pass

        self._pre_check_images(base_dir, source_dir=source_dir)
        try:
            if self._pre_sanitize_tex(base_dir):
                logger.info("⚡ Pre-sanitize applied to content.tex")
        except Exception:
            pass

        for i in range(self.max_try):
            logger.info(f"\n[Try {i+1}] LaTeX compile...")

            # 1. Compile
            result = compile_content(base_dir)

            # 2. Success?
            if result.get("success"):
                logger.info("✅ Compile success")
                try:
                    result["alignment_dsid"] = self.align_speech_to_pdf_pages(base_dir, source_dir=source_dir)
                except Exception:
                    pass
                return result

            # 3. Handle Errors
            errors = result.get("errors", [])
            valid_errors = [e for e in errors if e.get('message')]
            if not valid_errors:
                logger.error("Unknown error occurred (no log output).")
                break

            error_summary = "\n".join([f"Error: {e.get('message')} (file={e.get('file')}, line {e.get('line')})" for e in valid_errors])
            logger.error(error_summary)

            logger.info("🤖 Attempting autonomous fix...")
            if self._attempt_fix(base_dir, valid_errors):
                continue # Retry loop
            else:
                logger.error("❌ Fix attempt failed.")

        # Final attempt
        result = compile_content(base_dir)
        if result.get("success"):
            logger.info("✅ Compile success")
        
        return result
