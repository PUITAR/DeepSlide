import os
import re
import zipfile
import tarfile
import shutil
import logging
import uuid
import subprocess
from typing import Optional, Dict, Any
from fastapi import UploadFile

try:
    import pypandoc
except Exception:
    pypandoc = None

from app.services.core.latex_merger import merge_latex_file
from app.services.core.rough_divider import RoughDivider
from app.services.core.chapter_node import ChapterNode

logger = logging.getLogger(__name__)

class ProjectAnalyzerService:
    def __init__(self, upload_dir: str = "uploads", projects_dir: str = "projects"):
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        env_upload_dir = os.getenv("DEEPSLIDE_V3_UPLOADS_DIR")
        env_projects_dir = os.getenv("DEEPSLIDE_V3_PROJECTS_DIR")

        resolved_upload_dir = env_upload_dir or upload_dir
        resolved_projects_dir = env_projects_dir or projects_dir
        if not os.path.isabs(resolved_upload_dir):
            resolved_upload_dir = os.path.join(root_dir, resolved_upload_dir)
        if not os.path.isabs(resolved_projects_dir):
            resolved_projects_dir = os.path.join(root_dir, resolved_projects_dir)

        self.upload_dir = os.path.abspath(resolved_upload_dir)
        self.projects_dir = os.path.abspath(resolved_projects_dir)
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.projects_dir, exist_ok=True)

    async def save_upload_file(self, file: UploadFile) -> str:
        original = os.path.basename(file.filename or "upload")
        unique = f"{uuid.uuid4().hex}_{original}"
        file_path = os.path.join(self.upload_dir, unique)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return file_path

    def materialize_upload(self, file_path: str, project_id: str, original_filename: str = "upload") -> str:
        try:
            return self.extract_file(file_path, project_id)
        except Exception:
            pass

        name = str(project_id or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name or "\x00" in name:
            raise ValueError("Invalid project id")
        if not re.fullmatch(r"[0-9a-fA-F-]{32,36}", name):
            raise ValueError("Project id must be a UUID")

        project_path = os.path.join(self.projects_dir, name)
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        os.makedirs(project_path, exist_ok=True)

        safe_name = os.path.basename(str(original_filename or "upload"))
        if not safe_name:
            safe_name = os.path.basename(file_path) or "upload"
        dst = os.path.join(project_path, safe_name)
        shutil.copy2(file_path, dst)
        return project_path

    def extract_file(self, file_path: str, project_name: str) -> str:
        name = str(project_name or "").strip()
        if not name or "/" in name or "\\" in name or ".." in name or "\x00" in name:
            raise ValueError("Invalid project id")
        if not re.fullmatch(r"[0-9a-fA-F-]{32,36}", name):
            raise ValueError("Project id must be a UUID")

        extract_path = os.path.join(self.projects_dir, name)
        
        # Clean up existing directory if it exists
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)
        os.makedirs(extract_path, exist_ok=True)

        # 1) Try Python built-in unpacker first (zip, tar, gztar, bztar, xztar)
        try:
            shutil.unpack_archive(file_path, extract_path)
            return extract_path
        except Exception:
            pass

        # 2) Try zip/tar explicit detection as a fallback
        try:
            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    zip_ref.extractall(extract_path)
                return extract_path
        except Exception:
            pass

        try:
            if tarfile.is_tarfile(file_path):
                with tarfile.open(file_path, "r:*") as tar_ref:
                    tar_ref.extractall(extract_path)
                return extract_path
        except Exception:
            pass

        # 3) Try 7z as a universal extractor for rar/7z/iso/etc (if installed)
        if shutil.which("7z"):
            try:
                proc = subprocess.run(
                    ["7z", "x", file_path, f"-o{extract_path}", "-y"],
                    capture_output=True,
                    text=True,
                )
                if proc.returncode == 0:
                    return extract_path
                logger.warning(f"7z extraction failed: {(proc.stderr or proc.stdout or '')[:2000]}")
            except Exception as e:
                logger.warning(f"7z execution failed: {e}")

        raise ValueError("Unsupported file format or extraction failed")

        return extract_path

    def find_source_file(self, project_path: str) -> tuple[Optional[str], Optional[str]]:
        """
        Finds the main source file (tex, md, docx, pptx).
        Returns (full_path, file_type) where file_type is one of 'tex', 'md', 'docx', 'pptx'.
        """
        # 1. Check for TeX
        tex = self.find_main_tex(project_path)
        if tex:
            return tex, "tex"
            
        # 2. Check for Markdown
        md = self._find_main_by_ext(project_path, ".md", ["main.md", "paper.md", "readme.md", "read_me.md"])
        if md:
            return md, "md"
            
        # 3. Check for Word
        docx = self._find_main_by_ext(project_path, ".docx", ["main.docx", "paper.docx", "report.docx"])
        if docx:
            return docx, "docx"
            
        # 4. Check for PPT
        pptx = self._find_main_by_ext(project_path, ".pptx", ["main.pptx", "presentation.pptx", "slides.pptx"])
        if pptx:
            return pptx, "pptx"
            
        return None, None

    def _find_main_by_ext(self, root_dir: str, ext: str, preferred_names: list) -> Optional[str]:
        candidates = []
        for dirpath, _, filenames in os.walk(root_dir):
            for fn in filenames:
                if fn.lower().endswith(ext):
                    candidates.append(os.path.join(dirpath, fn))
        
        if not candidates:
            return None
            
        for p in candidates:
            if os.path.basename(p).lower() in preferred_names:
                return p
        return sorted(candidates)[0]

    def find_main_tex(self, project_path: str) -> Optional[str]:
        # Heuristic to find the main tex file
        candidates = []
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.endswith('.tex'):
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            if r'\documentclass' in content:
                                candidates.append(full_path)
                    except Exception:
                        pass
        
        if not candidates:
            return None
        
        # Prefer 'main.tex' if it exists
        for cand in candidates:
            if os.path.basename(cand) == 'main.tex':
                return cand
        
        # Otherwise return the first candidate
        return candidates[0]

    def analyze_project(self, project_path: str, source_path: str, source_type: str = "tex") -> Dict[str, Any]:
        """
        Analyzes the project: merges LaTeX files and runs rough divider.
        Supports tex, md, docx, pptx.
        """
        base_dir = os.path.dirname(source_path)
        main_filename = os.path.basename(source_path)
        merged_content = ""
        
        if source_type == "tex":
            # 1. Merge LaTeX files
            merged_content = merge_latex_file(main_filename, base_dir)
        elif source_type in ("md", "docx", "pptx"):
            # Convert to TeX first
            merged_content = self._convert_to_tex(source_path, source_type, project_path)
        
        # 2. Divide into nodes
        divider = RoughDivider()
        nodes, feedback = divider.divide(merged_content, {})
        
        # Convert nodes to dict for JSON serialization
        nodes_data = [node.to_dict() for node in nodes]
        
        return {
            "main_file": main_filename,
            "base_dir": base_dir,
            "merged_content": merged_content,
            "nodes": nodes_data,
            "feedback": feedback,
            "source_type": source_type
        }

    def _convert_to_tex(self, source_path: str, source_type: str, project_root: str) -> str:
        if source_type == "md":
            try:
                with open(source_path, "r", encoding="utf-8") as f:
                    content = f.read()
                return self._convert_md_to_tex(content)
            except Exception as e:
                logger.error(f"MD conversion failed: {e}")
                return ""
        
        # Check for pandoc
        if not shutil.which("pandoc"):
            logger.error("Pandoc not found")
            return ""

        media_path = os.path.join(project_root, "media")
        os.makedirs(media_path, exist_ok=True)
        
        if source_type == "pptx":
            return self._convert_pptx_to_tex(source_path, media_path)
        elif source_type == "docx":
            return self._convert_docx_to_tex(source_path, media_path)
            
        return ""

    def _run_pandoc(self, input_path: str, to_format: str, extra_args: list = []) -> str:
        # Wrapper to support pypandoc or subprocess
        if pypandoc:
            try:
                return pypandoc.convert_file(input_path, to_format, extra_args=extra_args)
            except Exception as e:
                logger.warning(f"pypandoc failed, trying subprocess: {e}")
        
        # Fallback to subprocess
        cmd = ["pandoc", input_path, "-t", to_format] + extra_args
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if res.returncode != 0:
                logger.error(f"Pandoc error: {res.stderr}")
                return ""
            return res.stdout
        except Exception as e:
            logger.error(f"Pandoc subprocess failed: {e}")
            return ""

    def _convert_pptx_to_tex(self, pptx_path: str, media_path: str) -> str:
        # 1. Convert PPTX to Markdown
        args = ['--track-changes=accept', f'--extract-media={media_path}']
        md_content = self._run_pandoc(pptx_path, 'markdown', args)
        
        # 2. Filter Decorative Images
        def filter_images(match):
            # src = match.group(2)
            # Logic to filter images... simplified for now
            return match.group(0)

        # 3. Convert MD to TeX
        tex_content = self._convert_md_to_tex(md_content)
        
        # Post-process media paths
        abs_media = os.path.abspath(media_path).replace(os.sep, '/')
        if not abs_media.endswith('/'): abs_media += '/'
        tex_content = tex_content.replace(abs_media, '')
        
        return tex_content

    def _convert_docx_to_tex(self, docx_path: str, media_path: str) -> str:
        args = ['--standalone', f'--extract-media={media_path}']
        output = self._run_pandoc(docx_path, 'latex', args)
        
        # Post-process media paths
        abs_media = os.path.abspath(media_path).replace(os.sep, '/')
        if not abs_media.endswith('/'): abs_media += '/'
        output = output.replace(abs_media, '')
        
        return output

    def _convert_md_to_tex(self, md_content: str) -> str:
        # Use the custom logic from reference
        lines = md_content.split('\n')
        new_lines = []
        in_code_block = False
        in_notes_block = False
        list_state = None
        title_found = False
        
        for line in lines:
            stripped = line.strip()
            
            # Code block
            if stripped.startswith('```'):
                if in_code_block:
                    new_lines.append('\\end{verbatim}')
                    in_code_block = False
                else:
                    new_lines.append('\\begin{verbatim}')
                    in_code_block = True
                continue
            if in_code_block:
                new_lines.append(line)
                continue

            # Notes
            if stripped.startswith('::: notes') or stripped.startswith(':::notes'):
                new_lines.append('\\paragraph{Speaker Notes}')
                new_lines.append('\\begin{quote}')
                in_notes_block = True
                continue
            if in_notes_block:
                if stripped.startswith(':::') and not stripped.startswith('::: notes'):
                    new_lines.append('\\end{quote}')
                    in_notes_block = False
                    continue
            
            # Lists
            ul_match = re.match(r'^\s*[-*+]\s+(.*)', line)
            ol_match = re.match(r'^\s*\d+\.\s+(.*)', line)
            
            if ul_match or ol_match:
                new_type = 'ul' if ul_match else 'ol'
                content = ul_match.group(1) if ul_match else ol_match.group(1)
                
                if list_state != new_type:
                    if list_state == 'ul': new_lines.append('\\end{itemize}')
                    elif list_state == 'ol': new_lines.append('\\end{enumerate}')
                    
                    if new_type == 'ul': new_lines.append('\\begin{itemize}')
                    else: new_lines.append('\\begin{enumerate}')
                    list_state = new_type
                
                content = self._process_inline_md(content)
                new_lines.append(f'\\item {content}')
                continue
            else:
                if list_state:
                    if list_state == 'ul': new_lines.append('\\end{itemize}')
                    elif list_state == 'ol': new_lines.append('\\end{enumerate}')
                    list_state = None

            # Headers
            header_match = re.match(r'^(#{1,4})\s+(.*)', line)
            if header_match:
                level = len(header_match.group(1))
                txt = header_match.group(2).strip()
                if level == 1 and not title_found:
                    new_lines.append(f'\\title{{{txt}}}')
                    new_lines.append('\\maketitle')
                    new_lines.append(f'\\section{{{txt}}}')
                    title_found = True
                else:
                    cmd = {1: 'section', 2: 'subsection', 3: 'subsubsection', 4: 'paragraph'}.get(level, 'paragraph')
                    new_lines.append(f'\\{cmd}{{{txt}}}')
                continue

            # Images
            img_pattern = r'!\[(.*?)\]\((.*?)\)'
            if re.search(img_pattern, line):
                def repl(m):
                    alt, src = m.group(1), m.group(2)
                    return f"\\begin{{figure}}[htbp]\n\\centering\n\\includegraphics[width=0.8\\textwidth]{{{src}}}\n\\caption{{{alt}}}\n\\end{{figure}}"
                line = re.sub(img_pattern, repl, line)
                new_lines.append(line)
                continue

            # Normal
            new_lines.append(self._process_inline_md(line))

        if list_state:
             if list_state == 'ul': new_lines.append('\\end{itemize}')
             elif list_state == 'ol': new_lines.append('\\end{enumerate}')

        body = '\n'.join(new_lines)
        return "\\documentclass{article}\n\\usepackage{graphicx}\n\\begin{document}\n" + body + "\n\\end{document}"

    def _process_inline_md(self, text: str) -> str:
        # Simple inline MD processing
        # Escape special chars (%, &)
        text = text.replace('%', '\\%').replace('&', '\\&')
        # Bold
        text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
        # Italic
        text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)
        return text

project_analyzer = ProjectAnalyzerService()
