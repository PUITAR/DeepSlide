import os
import logging
from typing import Dict, Any, List, Optional
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.agents import ChatAgent
from camel.messages import BaseMessage
from dotenv import load_dotenv
from app.core.agent_model_env import resolve_text_llm_env
from app.core.model_config import sanitize_model_config
import json
import re
import fitz
from app.services.llm_timeout import safe_agent_step

from .core.ppt_core import extract_frame_by_index, replace_frame_in_content, parse_resp_for_editor
from .core.compiler_service import CompilerService
from .core.slide_graph_generator import SlideGraphGenerator
from .core.compressor import Compressor
from .core.data_types import LogicFlow, LogicNode, LogicEdge
from .core.chapter_node import ChapterNode

logger = logging.getLogger(__name__)

from .vlm_beautify import beautify_frame_from_image

class EditorService:
    def __init__(self):
        # Initialize AI for editor modifications
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env"))
        if os.path.exists(env_path):
            load_dotenv(env_path)
            
        cfg = resolve_text_llm_env("EDITOR")
        api_key = cfg.api_key
        platform_type = cfg.platform_type
        model_type = cfg.model_type
        base_url = cfg.api_url
        
        if api_key:
            try:
                model_platform = ModelPlatformType(platform_type)
            except Exception:
                model_platform = ModelPlatformType.OPENAI_COMPATIBLE_MODEL

            create_kwargs = {
                "model_platform": model_platform,
                "model_type": model_type,
                "api_key": api_key,
                "model_config_dict": sanitize_model_config(model_type, {"temperature": 0.0}),
            }
            if base_url:
                create_kwargs["url"] = base_url

            self.model = ModelFactory.create(**create_kwargs)
        else:
            self.model = None

    def _ensure_dsid_support(self, recipe_dir: str) -> None:
        base_path = os.path.join(recipe_dir, "base.tex")
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

    def _inject_dsid_into_content(self, recipe_dir: str) -> Dict[str, Any]:
        content_path = os.path.join(recipe_dir, "content.tex")
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

    def _extract_pdf_page_texts(self, pdf_path: str) -> List[str]:
        doc = fitz.open(pdf_path)
        texts: List[str] = []
        for i in range(doc.page_count):
            try:
                page = doc.load_page(int(i))
                txt = page.get_text("text") or ""
            except Exception:
                txt = ""
            texts.append(" ".join(str(txt).split()))
        doc.close()
        return texts

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

    def _make_extra_page_speech(self, page_meta: Dict[str, Any], title: str) -> str:
        t = str(page_meta.get("type") or "")
        label = str(page_meta.get("label") or "").strip()
        if t == "title":
            if title:
                return f"大家好，我将用接下来的时间介绍《{title}》。我会重点讲方法与实验结果，最后用一句话总结核心贡献。"
            return "大家好，我将用接下来的时间介绍我的研究工作。我会重点讲方法与实验结果，最后用一句话总结核心贡献。"
        if t == "outline":
            return "我将先用约一分钟介绍方法，然后用约两分钟展示关键实验结果和结论。"
        if t == "section":
            if label:
                return f"下面进入{label}部分。"
            return "下面进入下一部分。"
        if t == "references":
            return "参考文献在这里列出。如需细节我可以在问答或会后展开。"
        if t == "ending":
            if title:
                return f"最后一句话总结：这项工作围绕《{title}》提出了方法并用实验结果验证了核心贡献。"
            return "最后一句话总结：这项工作提出了方法，并用实验结果验证了核心贡献。"
        return "这一页是过渡或补充信息，我会简要提示要点后进入下一页。"

    def align_speech_to_pdf_pages(self, project_path: str) -> Dict[str, Any]:
        recipe_dir = os.path.join(project_path, "recipe")
        pdf_path = os.path.join(recipe_dir, "base.pdf")
        speech_path = os.path.join(recipe_dir, "speech.txt")
        title_path = os.path.join(recipe_dir, "title.tex")

        if not os.path.exists(pdf_path):
            return {"success": False, "reason": "missing_pdf"}

        try:
            page_texts = self._extract_pdf_page_texts(pdf_path)
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

        dsid_by_page: List[Optional[int]] = []
        page_meta_by_page: List[Dict[str, Any]] = []
        content_pages = 0
        for i, txt in enumerate(page_texts):
            sid = self._extract_dsid_index(txt)
            dsid_by_page.append(sid)
            if sid is not None:
                content_pages += 1
                page_meta_by_page.append({"type": "content", "label": ""})
            else:
                try:
                    page_meta_by_page.append(self._classify_extra_page(txt, int(i), int(page_count)))
                except Exception:
                    page_meta_by_page.append({"type": "extra", "label": ""})

        speech_by_page: List[str] = []
        already_page_aligned = len(speeches) == page_count

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
                    speech_by_page.append("我将简要讲解这一页的关键内容，然后进入下一页。")
                else:
                    meta = self._classify_extra_page(page_texts[i], i, page_count)
                    speech_by_page.append(self._make_extra_page_speech(meta, title))
        else:
            for i in range(page_count):
                sid = dsid_by_page[i]
                if sid is not None and 1 <= sid <= len(speeches) and str(speeches[sid - 1]).strip():
                    speech_by_page.append(str(speeches[sid - 1]).strip())
                else:
                    meta = self._classify_extra_page(page_texts[i], i, page_count)
                    speech_by_page.append(self._make_extra_page_speech(meta, title))

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
            "page_meta_by_page": page_meta_by_page,
            "extra_pages": [i for i, sid in enumerate(dsid_by_page) if sid is None],
        }
        try:
            with open(os.path.join(recipe_dir, "alignment_dsid.json"), "w", encoding="utf-8") as f:
                json.dump(alignment, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return alignment

    def verify_pdf_content_alignment(self, project_path: str) -> Dict[str, Any]:
        recipe_dir = os.path.join(project_path, "recipe")
        pdf_path = os.path.join(recipe_dir, "base.pdf")
        content_path = os.path.join(recipe_dir, "content.tex")
        base_path = os.path.join(recipe_dir, "base.tex")
        speech_path = os.path.join(recipe_dir, "speech.txt")

        if not os.path.exists(pdf_path) or not os.path.exists(content_path):
            return {"success": False, "reason": "missing_files"}

        try:
            with open(content_path, "r", encoding="utf-8", errors="ignore") as f:
                tex = f.read()
        except Exception:
            return {"success": False, "reason": "read_content_failed"}

        speeches: List[str] = []
        try:
            with open(speech_path, "r", encoding="utf-8", errors="ignore") as f:
                speeches = (f.read() or "").split("<next>")
        except Exception:
            speeches = []

        base_tex = ""
        try:
            with open(base_path, "r", encoding="utf-8", errors="ignore") as f:
                base_tex = f.read() or ""
        except Exception:
            base_tex = ""

        def _tokenize(s: str) -> set[str]:
            toks = re.findall(r"[A-Za-z0-9]{3,}", str(s or ""))
            return set([t.lower() for t in toks])

        def _strip_tex(s: str) -> str:
            t = str(s or "")
            t = re.sub(r"%.*$", " ", t, flags=re.MULTILINE)
            t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
            t = re.sub(r"\{([^\}]*)\}", r"\1", t)
            t = re.sub(r"\$[^$]*\$", " ", t)
            t = re.sub(r"\s+", " ", t)
            return t.strip()

        frames = [m.group(1) for m in re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', tex, re.DOTALL)]

    def auto_enrich_citations(self, project_path: str, logic_chain: Optional[Dict[str, Any]] = None, max_refs_per_slide: int = 3) -> Dict[str, Any]:
        return {"success": False, "reason": "auto_enrich_citations_not_implemented", "updated_slide_ids": []}

        frame_sigs: List[Dict[str, Any]] = []
        for fr in frames:
            m = re.search(r"\\frametitle\{([^}]*)\}", fr)
            title = _strip_tex(m.group(1)) if m else ""
            plain = _strip_tex(fr)
            frame_sigs.append({"title": title, "tokens": _tokenize(title + " " + plain)})

        try:
            doc = fitz.open(pdf_path)
            pages_count = doc.page_count
            page_sigs: List[Dict[str, Any]] = []
            for i in range(pages_count):
                try:
                    page = doc.load_page(int(i))
                    txt = page.get_text("text") or ""
                except Exception:
                    txt = ""
                clean = " ".join(str(txt).split())
                page_sigs.append({"text": clean, "tokens": _tokenize(clean)})
            doc.close()
        except Exception:
            return {"success": False, "reason": "read_pdf_failed"}

        force_skip_pages: set[int] = set()
        if "\\maketitle" in base_tex and pages_count > 0:
            force_skip_pages.add(0)
        if "\\bibliography" in base_tex and pages_count > 0:
            force_skip_pages.add(pages_count - 1)

        F = len(frame_sigs)
        P = len(page_sigs)
        neg = -10**9
        dp = [[neg] * (F + 1) for _ in range(P + 1)]
        bt: List[List[tuple[int, int, int]]] = [[(0, 0, 0)] * (F + 1) for _ in range(P + 1)]
        dp[0][0] = 0

        def sim(pi: int, fi: int) -> int:
            p = page_sigs[pi]
            f = frame_sigs[fi]
            pt = p["tokens"]
            ft = f["tokens"]
            if not pt or not ft:
                base = 0.0
            else:
                inter = len(pt & ft)
                denom = max(1, min(len(pt), len(ft)))
                base = inter / float(denom)
            title = str(f.get("title") or "").strip()
            title_hit = False
            if title and title.lower() in str(p.get("text") or "").lower():
                base += 0.35
                title_hit = True
            if len(pt) >= 10 and len(ft) >= 10 and not title_hit and base < 0.08:
                return -700
            return int(base * 1000)

        for i in range(P + 1):
            for j in range(F + 1):
                cur = dp[i][j]
                if cur <= neg // 2:
                    continue

                if i < P:
                    sp = speeches[i] if len(speeches) == P and i < len(speeches) else ""
                    skip_cost = 0 if (i in force_skip_pages or "<add>" in str(sp)) else -650
                    v = cur + skip_cost
                    if v > dp[i + 1][j]:
                        dp[i + 1][j] = v
                        bt[i + 1][j] = (i, j, 1)

                if j < F:
                    v = cur - 900
                    if v > dp[i][j + 1]:
                        dp[i][j + 1] = v
                        bt[i][j + 1] = (i, j, 2)

                if i < P and j < F:
                    sp = speeches[i] if len(speeches) == P and i < len(speeches) else ""
                    if i not in force_skip_pages and "<add>" not in str(sp):
                        v = cur + sim(i, j)
                        if v > dp[i + 1][j + 1]:
                            dp[i + 1][j + 1] = v
                            bt[i + 1][j + 1] = (i, j, 3)

        mapping: List[Optional[int]] = [None] * P
        scores: List[Optional[int]] = [None] * P
        i, j = P, F
        while i > 0 or j > 0:
            pi, pj, act = bt[i][j]
            if act == 3:
                mapping[pi] = pj
                scores[pi] = sim(pi, pj)
            i, j = pi, pj
            if i == 0 and j == 0:
                break

        unmapped = [idx for idx, v in enumerate(mapping) if v is None]
        low = [idx for idx, sc in enumerate(scores) if sc is not None and sc < 0]
        return {
            "success": True,
            "pages": P,
            "frames": F,
            "speeches": len(speeches),
            "force_skip_pages": sorted(force_skip_pages),
            "unmapped_pages": unmapped,
            "low_score_pages": low,
            "page_to_frame": mapping,
            "scores": scores,
        }

    def get_editor_files(self, project_path: str) -> Dict[str, str]:
        """Read content.tex, speech.txt, title.tex, base.tex"""
        recipe_dir = os.path.join(project_path, "recipe")
        if not os.path.exists(recipe_dir):
            # Fallback if recipe folder doesn't exist, maybe in root
            recipe_dir = project_path

        files = {
            "content": "",
            "speech": "",
            "title": "",
            "base": ""
        }
        
        try:
            with open(os.path.join(recipe_dir, "content.tex"), "r") as f: files["content"] = f.read()
        except: pass
        try:
            with open(os.path.join(recipe_dir, "speech.txt"), "r") as f: files["speech"] = f.read()
        except: pass
        try:
            with open(os.path.join(recipe_dir, "title.tex"), "r") as f: files["title"] = f.read()
        except: pass
        try:
            with open(os.path.join(recipe_dir, "base.tex"), "r") as f: files["base"] = f.read()
        except: pass
        
        return files

    def save_editor_files(self, project_path: str, updates: Dict[str, str]) -> bool:
        recipe_dir = os.path.join(project_path, "recipe")
        if not os.path.exists(recipe_dir):
            os.makedirs(recipe_dir, exist_ok=True)
            
        try:
            if "content" in updates:
                with open(os.path.join(recipe_dir, "content.tex"), "w") as f: f.write(updates["content"])
            if "speech" in updates:
                with open(os.path.join(recipe_dir, "speech.txt"), "w") as f: f.write(updates["speech"])
            if "title" in updates:
                with open(os.path.join(recipe_dir, "title.tex"), "w") as f: f.write(updates["title"])
            if "base" in updates:
                with open(os.path.join(recipe_dir, "base.tex"), "w") as f: f.write(updates["base"])
            return True
        except Exception as e:
            logger.error(f"Error saving files: {e}")
            return False

    def compile(self, project_path: str) -> Dict[str, Any]:
        recipe_dir = os.path.join(project_path, "recipe")
        os.makedirs(recipe_dir, exist_ok=True)
        compiler = CompilerService()
        return compiler.run(recipe_dir, source_dir=project_path)

    def get_preview_pages(self, project_path: str) -> List[str]:
        """Convert PDF to images and return list of image filenames relative to project"""
        recipe_dir = os.path.join(project_path, "recipe")
        pdf_path = os.path.join(recipe_dir, "base.pdf")
        
        if not os.path.exists(pdf_path):
            return []

        preview_dir = os.path.join(recipe_dir, "preview_cache")
        os.makedirs(preview_dir, exist_ok=True)

        try:
            doc = fitz.open(pdf_path)
            pages: List[str] = []
            for pn in range(doc.page_count):
                page = doc.load_page(pn)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_filename = f"page_{pn}.png"
                img_path = os.path.join(preview_dir, img_filename)
                pix.save(img_path)
                pages.append(img_filename)
            doc.close()
            return pages
        except Exception as e:
            logger.error(f"Preview error: {e}")
            return []

    def beautify_pdf(self, project_path: str, rounds: int = 3) -> bool:
        recipe_dir = os.path.join(project_path, "recipe")
        pdf_path = os.path.join(recipe_dir, "base.pdf")
        os.makedirs(recipe_dir, exist_ok=True)

        compile_res = self.compile(project_path)
        if not compile_res.get("success"):
            return False

        preview_pages = self.get_preview_pages(project_path)
        preview_dir = os.path.join(recipe_dir, "preview_cache")
        content_path = os.path.join(recipe_dir, "content.tex")
        if not os.path.exists(content_path) or not os.path.exists(pdf_path):
            return False

        try:
            with open(content_path, "r", encoding="utf-8", errors="ignore") as f:
                full_tex = f.read()
        except Exception:
            return False

        speeches: List[str] = []
        speech_path = os.path.join(recipe_dir, "speech.txt")
        try:
            with open(speech_path, "r", encoding="utf-8", errors="ignore") as f:
                speeches = (f.read() or "").split("<next>")
        except Exception:
            speeches = []

        def _strip_tex(s: str) -> str:
            t = str(s or "")
            t = re.sub(r"%.*$", " ", t, flags=re.MULTILINE)
            t = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", " ", t)
            t = re.sub(r"\{([^\}]*)\}", r"\1", t)
            t = re.sub(r"\$[^$]*\$", " ", t)
            t = re.sub(r"\s+", " ", t)
            return t.strip()

        def _tokenize(s: str) -> set[str]:
            toks = re.findall(r"[A-Za-z0-9]{3,}", str(s or ""))
            return set([x.lower() for x in toks])

        def _frame_signature(frame_tex: str) -> Dict[str, Any]:
            t = str(frame_tex or "")
            m = re.search(r"\\frametitle\{([^}]*)\}", t)
            title = _strip_tex(m.group(1)) if m else ""
            plain = _strip_tex(t)
            return {"title": title, "tokens": _tokenize(title + " " + plain)}

        def _align_pages_to_frames(pdf_path: str, pages_count: int, frames_in: List[str]) -> List[Optional[int]]:
            frame_sigs = [_frame_signature(fr) for fr in frames_in]
            page_sigs: List[Dict[str, Any]] = []
            try:
                doc = fitz.open(pdf_path)
                for i in range(pages_count):
                    try:
                        page = doc.load_page(int(i))
                        txt = page.get_text("text") or ""
                    except Exception:
                        txt = ""
                    clean = " ".join(str(txt).split())
                    page_sigs.append({"text": clean, "tokens": _tokenize(clean)})
                doc.close()
            except Exception:
                page_sigs = [{"text": "", "tokens": set()} for _ in range(pages_count)]

            F = len(frame_sigs)
            P = len(page_sigs)
            neg = -10**9
            dp = [[neg] * (F + 1) for _ in range(P + 1)]
            bt: List[List[tuple[int, int, int]]] = [[(0, 0, 0)] * (F + 1) for _ in range(P + 1)]
            dp[0][0] = 0

            def sim(pi: int, fi: int) -> int:
                p = page_sigs[pi]
                f = frame_sigs[fi]
                pt = p["tokens"]
                ft = f["tokens"]
                if not pt or not ft:
                    base = 0.0
                else:
                    inter = len(pt & ft)
                    denom = max(1, min(len(pt), len(ft)))
                    base = inter / float(denom)
                title = str(f.get("title") or "").strip()
                title_hit = False
                if title and title.lower() in str(p.get("text") or "").lower():
                    base += 0.35
                    title_hit = True
                if len(pt) >= 10 and len(ft) >= 10 and not title_hit and base < 0.08:
                    return -700
                return int(base * 1000)

            for i in range(P + 1):
                for j in range(F + 1):
                    cur = dp[i][j]
                    if cur <= neg // 2:
                        continue

                    if i < P:
                        sp = speeches[i] if len(speeches) == P and i < len(speeches) else ""
                        skip_cost = 0 if (i in force_skip_pages or "<add>" in str(sp)) else -650
                        v = cur + skip_cost
                        if v > dp[i + 1][j]:
                            dp[i + 1][j] = v
                            bt[i + 1][j] = (i, j, 1)

                    if j < F:
                        v = cur - 900
                        if v > dp[i][j + 1]:
                            dp[i][j + 1] = v
                            bt[i][j + 1] = (i, j, 2)

                    if i < P and j < F:
                        sp = speeches[i] if len(speeches) == P and i < len(speeches) else ""
                        if i not in force_skip_pages and "<add>" not in str(sp):
                            v = cur + sim(i, j)
                            if v > dp[i + 1][j + 1]:
                                dp[i + 1][j + 1] = v
                                bt[i + 1][j + 1] = (i, j, 3)

            mapping: List[Optional[int]] = [None] * P
            i, j = P, F
            while i > 0 or j > 0:
                pi, pj, act = bt[i][j]
                if act == 3:
                    mapping[pi] = pj
                i, j = pi, pj
                if i == 0 and j == 0:
                    break
            return mapping

        modified_any = False
        rounds = max(1, min(8, int(rounds or 3)))

        base_tex = ""
        try:
            with open(os.path.join(recipe_dir, "base.tex"), "r", encoding="utf-8", errors="ignore") as f:
                base_tex = f.read() or ""
        except Exception:
            base_tex = ""

        force_skip_pages: set[int] = set()
        if "\\maketitle" in base_tex and preview_pages:
            force_skip_pages.add(0)
        if "\\bibliography" in base_tex and preview_pages:
            force_skip_pages.add(len(preview_pages) - 1)

        for _ in range(rounds):
            frames = list(re.finditer(r'(\\begin\{frame\}.*?\\end\{frame\})', full_tex, re.DOTALL))
            if not frames:
                break

            frame_texts = [m.group(1) for m in frames]
            page_to_frame = _align_pages_to_frames(pdf_path, len(preview_pages), frame_texts)

            modified_round = False
            for page_i in range(len(preview_pages)):
                frame_i = page_to_frame[page_i] if page_to_frame and page_i < len(page_to_frame) else None
                if frame_i is None:
                    continue
                if frame_i < 0 or frame_i >= len(frames):
                    continue
                img_path = os.path.join(preview_dir, preview_pages[page_i])
                if not os.path.exists(img_path):
                    continue
                frame, _ = extract_frame_by_index(full_tex, int(frame_i))
                if not frame:
                    continue
                new_frame = beautify_frame_from_image(img_path, frame, base_dir=recipe_dir)
                if new_frame and new_frame.strip() and new_frame.strip() != frame.strip():
                    full_tex = replace_frame_in_content(full_tex, int(frame_i), new_frame.strip())
                    modified_round = True

            if modified_round:
                modified_any = True
                try:
                    with open(content_path, "w", encoding="utf-8") as f:
                        f.write(full_tex)
                except Exception:
                    break
                compile_res = self.compile(project_path)
                if not compile_res.get("success"):
                    break
                preview_pages = self.get_preview_pages(project_path)
            else:
                break

        return modified_any

    def process_modification(self, project_path: str, instruction: str, page_idx: int) -> bool:
        if not self.model:
            logger.error("AI model not initialized")
            return False
            
        recipe_dir = os.path.join(project_path, "recipe")
        speeches: List[str] = []
        try:
            with open(os.path.join(recipe_dir, "speech.txt"), "r") as f:
                speeches = f.read().split("<next>")
        except: pass

        alignment: Dict[str, Any] = {}
        try:
            with open(os.path.join(recipe_dir, "alignment.json"), "r", encoding="utf-8", errors="ignore") as f:
                alignment = json.load(f) or {}
        except Exception:
            alignment = {}
        if not alignment.get("success"):
            try:
                alignment = self.verify_pdf_content_alignment(project_path)
                if alignment.get("success"):
                    try:
                        with open(os.path.join(recipe_dir, "alignment.json"), "w", encoding="utf-8") as f:
                            json.dump(alignment, f, ensure_ascii=False, indent=2)
                    except Exception:
                        pass
            except Exception:
                alignment = {}

        page_to_frame = alignment.get("page_to_frame") if isinstance(alignment.get("page_to_frame"), list) else []
        frame_idx: Optional[int] = None
        if isinstance(page_idx, int) and page_to_frame and 0 <= page_idx < len(page_to_frame):
            v = page_to_frame[page_idx]
            if isinstance(v, int):
                frame_idx = v
            else:
                for d in range(1, 6):
                    for cand in (page_idx - d, page_idx + d):
                        if 0 <= cand < len(page_to_frame) and isinstance(page_to_frame[cand], int):
                            frame_idx = int(page_to_frame[cand])
                            break
                    if frame_idx is not None:
                        break

        speech_idx = page_idx
        try:
            if alignment.get("success"):
                if isinstance(frame_idx, int) and len(speeches) == int(alignment.get("frames") or -1):
                    speech_idx = frame_idx
                elif len(speeches) == int(alignment.get("pages") or -1):
                    speech_idx = page_idx
                elif isinstance(frame_idx, int) and frame_idx < len(speeches):
                    speech_idx = frame_idx
        except Exception:
            speech_idx = page_idx
        
        allowed_actions = ["MODIFY_SLIDE_CONTENT", "MODIFY_SPEECH"]
        if page_idx == 0:
            allowed_actions.append("MODIFY_TITLE_CONTENT")
        if page_idx != 0 and frame_idx is None:
            allowed_actions = [a for a in allowed_actions if a != "MODIFY_SLIDE_CONTENT"]
            
        plan = self._plan_modifications(instruction, allowed_actions, page_idx, speech_idx, frame_idx, speeches, recipe_dir)
        
        success = False
        for step in plan:
            action = step.get("action")
            sub_instruction = step.get("instruction")
            if action == "MODIFY_TITLE_CONTENT":
                if self._modify_title(recipe_dir, sub_instruction): success = True
            elif action == "MODIFY_SLIDE_CONTENT":
                if self._modify_content(recipe_dir, page_idx, frame_idx, sub_instruction): success = True
            elif action == "MODIFY_SPEECH":
                if self._modify_speech(recipe_dir, speech_idx, sub_instruction, speeches): success = True
        return success

    def _plan_modifications(self, instruction, allowed_actions, page_idx, speech_idx, frame_idx, speeches, recipe_dir):
        current_speech = speeches[speech_idx] if speech_idx < len(speeches) else ""
        current_latex = ""
        try:
            if page_idx == 0:
                with open(os.path.join(recipe_dir, "title.tex"), "r") as f: current_latex = f.read()
            else:
                with open(os.path.join(recipe_dir, "content.tex"), "r") as f: full_tex = f.read()
                match, _ = extract_frame_by_index(full_tex, int(frame_idx or 0))
                if match: current_latex = match
        except: pass

        system_prompt = (
            "You are a Presentation Editor Planner. Break down the instruction into executable actions.\n"
            f"Allowed actions: {json.dumps(allowed_actions)}.\n"
            "Return a JSON list: [{\"action\": \"...\", \"instruction\": \"...\"}]"
        )
        user_prompt = f"""
        Instruction: "{instruction}"
        Current Speech: "{current_speech}"
        Current LaTeX:
        ```latex
        {current_latex}
        ```
        """
        agent = ChatAgent(system_message=BaseMessage.make_assistant_message("Assistant", system_prompt), model=self.model)
        try:
            response = safe_agent_step(agent, BaseMessage.make_user_message("User", user_prompt), timeout_seconds=30.0)
            if not response:
                return []
            resp = response.msg.content
            match = re.search(r'\[.*\]', resp, re.DOTALL)
            if match: return json.loads(match.group(0))
        except Exception as e:
            logger.error(f"Planning error: {e}")
        return []

    def _modify_title(self, recipe_dir, instruction):
        path = os.path.join(recipe_dir, "title.tex")
        try:
            with open(path, "r") as f: current = f.read()
            prompt = f"Original title.tex:\n```latex\n{current}\n```\nInstruction: {instruction}\nReturn ONLY modified latex code."
            agent = ChatAgent(system_message=BaseMessage.make_assistant_message("Assistant", "You are a LaTeX expert. Modify title info."), model=self.model)
            response = safe_agent_step(agent, BaseMessage.make_user_message("User", prompt), timeout_seconds=30.0)
            if not response:
                return False
            resp = response.msg.content
            new_content = parse_resp_for_editor(resp)
            if new_content:
                with open(path, "w") as f: f.write(new_content)
                return True
        except Exception as e:
            logger.error(f"Title mod error: {e}")
        return False

    def _modify_content(self, recipe_dir, page_idx, frame_idx, instruction):
        path = os.path.join(recipe_dir, "content.tex")
        try:
            if frame_idx is None:
                return False
            with open(path, "r") as f: full_tex = f.read()
            target_frame, _ = extract_frame_by_index(full_tex, int(frame_idx))
            if not target_frame: return False
            
            prompt = f"Original Frame:\n```latex\n{target_frame}\n```\nInstruction: {instruction}\nReturn ONLY modified frame block."
            agent = ChatAgent(system_message=BaseMessage.make_assistant_message("Assistant", "You are a LaTeX expert. Modify frame content."), model=self.model)
            response = safe_agent_step(agent, BaseMessage.make_user_message("User", prompt), timeout_seconds=40.0)
            if not response:
                return False
            resp = response.msg.content
            new_frame = parse_resp_for_editor(resp)
            if new_frame:
                new_full = replace_frame_in_content(full_tex, int(frame_idx), new_frame)
                with open(path, "w") as f: f.write(new_full)
                return True
        except Exception as e:
            logger.error(f"Content mod error: {e}")
        return False

    def _modify_speech(self, recipe_dir, page_idx, instruction, speeches):
        path = os.path.join(recipe_dir, "speech.txt")
        try:
            if page_idx >= len(speeches): return False
            current = speeches[page_idx]
            prompt = f"Original Speech:\n{current}\nInstruction: {instruction}\nReturn ONLY modified speech text."
            agent = ChatAgent(system_message=BaseMessage.make_assistant_message("Assistant", "You are a speech editor."), model=self.model)
            response = safe_agent_step(agent, BaseMessage.make_user_message("User", prompt), timeout_seconds=30.0)
            if not response:
                return False
            resp = response.msg.content
            new_speech = resp.strip()
            if new_speech:
                if "<add>" in current and "<add>" not in new_speech:
                    new_speech = "<add> " + new_speech
                speeches[page_idx] = new_speech
                with open(path, "w") as f: f.write("\n<next>\n".join(speeches))
                return True
        except Exception as e:
            logger.error(f"Speech mod error: {e}")
        return False

    def generate_slides(self, project: Dict[str, Any], progress_cb=None) -> bool:
        project_path = project["path"]
        recipe_dir = os.path.join(project_path, "recipe")
        os.makedirs(recipe_dir, exist_ok=True)
        
        # 1. Base Tex
        base_tex_path = os.path.join(recipe_dir, "base.tex")
        if not os.path.exists(base_tex_path):
            base_template = r"""%!TeX encoding = UTF-8
%!TeX program = xelatex
\documentclass[xcolor=x11names,UTF8]{beamer}
\usepackage{ragged2e}
\renewcommand{\raggedright}{\leftskip=0pt \rightskip=0pt plus 0cm}
\usepackage{natbib}
\usepackage{ctex}
\input{title}
\providecommand{\deepslideid}[1]{}
\providecommand{\deepslideidvalue}{}
\renewcommand{\deepslideid}[1]{\gdef\deepslideidvalue{#1}}
\makeatletter
\@ifundefined{AtBeginEnvironment}{}{\AtBeginEnvironment{frame}{\gdef\deepslideidvalue{}}}
\makeatother
\setbeamertemplate{footline}{\hfill\ifx\deepslideidvalue\empty\else{\color{black!10}\fontsize{8}{8}\selectfont DSID:\deepslideidvalue}\fi\hspace{6pt}}
\begin{document}
\maketitle
\input{content}
\begin{frame}
    \frametitle{References}
    \bibliographystyle{plain}
    \bibliography{ref}
\end{frame}
\end{document}
"""
            with open(base_tex_path, "w", encoding="utf-8") as f:
                f.write(base_template)
                
        # 2. Title Tex
        title_tex_path = os.path.join(recipe_dir, "title.tex")
        if not os.path.exists(title_tex_path):
            def _escape_latex(s: str) -> str:
                t = str(s or "")
                rep = {
                    "\\\\": r"\textbackslash{}",
                    "{": r"\{",
                    "}": r"\}",
                    "_": r"\_",
                    "%": r"\%",
                    "&": r"\&",
                    "#": r"\#",
                    "^": r"\^{}",
                    "~": r"\~{}",
                }
                for k, v in rep.items():
                    t = t.replace(k, v)
                return t

            safe_name = _escape_latex(project.get('name', 'Untitled'))
            title_content = f"\\title{{{safe_name}}}\n\\author{{DeepSlide}}\n\\date{{\\today}}"
            with open(title_tex_path, "w", encoding="utf-8") as f:
                f.write(title_content)
        
        # 3. Prepare Logic Flow
        nodes_data = project.get("nodes", [])
        edges_data = project.get("edges", [])
        
        logic_nodes = []
        for i, n in enumerate(nodes_data):
            logic_nodes.append(LogicNode(
                name=n.get("title", ""),
                description=n.get("summary", ""),
                duration=n.get("duration", "1 min"),
                keywords=[]
            ))
            
        logic_edges = []
        # Frontend edges are uuid based, Compressor doesn't use edges explicitly but logic_flow has them.
        # We need to map uuid to index if we want to be correct, but Compressor loop doesn't use edges.
        # So we can skip edges for now or map them if needed.
        
        logic_flow = LogicFlow(nodes=logic_nodes, edges=logic_edges)
        
        # 4. Prepare Content Tree (ChapterNodes)
        # Assuming analysis.nodes contains the content tree structure
        analysis_nodes = project.get("analysis", {}).get("nodes", [])
        chapter_nodes = []
        
        def dict_to_chapter_node(d):
            node = ChapterNode(
                node_id=d.get("node_id", ""),
                title=d.get("title", ""),
                content=d.get("content", ""),
                summary=d.get("summary", ""),
                # node_type handling skipped for brevity, defaults to section
            )
            # Recursively add children if available in dict structure (not in flat list)
            # Usually analysis_nodes is a flat list? RequirementsService usually works with flat list + children_ids
            # We'll just pass the flat list if they are all there.
            return node
            
        for n in analysis_nodes:
            chapter_nodes.append(dict_to_chapter_node(n))
            
        # 5. Run Compressor
        compressor = Compressor()
        # Find images in project path
        image_list = []
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    rel_path = os.path.relpath(os.path.join(root, file), recipe_dir)
                    image_list.append(rel_path)
                    
        content, speech = compressor.compress(logic_flow, chapter_nodes, image_list, output_dir=recipe_dir, progress_cb=progress_cb)
        
        # 6. Save
        content.to_file(os.path.join(recipe_dir, "content.tex"))
        
        speech_str = "\n<next>\n".join([str(s) for s in speech])
        with open(os.path.join(recipe_dir, "speech.txt"), "w", encoding="utf-8") as f:
            f.write(speech_str)
            
        return True

editor_service = EditorService()
