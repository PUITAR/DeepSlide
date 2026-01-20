import os
import uuid
import zipfile
import tarfile
import re
from typing import Optional, Tuple
from latex_merger import merge_latex_file
import pypandoc

def save_uploaded_file(uploaded_file, base_dir: str) -> str:
    os.makedirs(base_dir, exist_ok=True)
    fname = getattr(uploaded_file, "name", None) or "upload"
    ext = os.path.splitext(fname)[1]
    uid = uuid.uuid4().hex
    out_path = os.path.join(base_dir, f"{uid}{ext}")
    with open(out_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return out_path

def extract_archive(archive_path: str, extract_dir: str) -> str:
    os.makedirs(extract_dir, exist_ok=True)
    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_dir)
        return extract_dir
    try:
        if tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path, "r:*") as t:
                t.extractall(extract_dir)
            return extract_dir
    except tarfile.TarError:
        pass
    return extract_dir

def _contains_documentclass(tex_path: str) -> bool:
    try:
        with open(tex_path, "r", encoding="utf-8") as f:
            content = f.read()
        return "\\documentclass" in content
    except Exception:
        return False

def find_main_tex(root_dir: str) -> Optional[str]:
    candidates = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".tex"):
                full = os.path.join(dirpath, fn)
                if _contains_documentclass(full):
                    candidates.append(full)
    if not candidates:
        return None
    for p in candidates:
        n = os.path.basename(p).lower()
        if n in ("main.tex", "paper.tex", "root.tex"):
            return p
    return sorted(candidates)[0]

def merge_project_to_main(base_dir: str, main_tex_path: str, output_name: str = "merged_main.tex") -> str:
    # Use the directory of main_tex_path as the base for merging if possible?
    # Usually inputs are relative to main.tex
    # But if base_dir is the extract root, and main.tex is inside a subdir (e.g. root/paper/main.tex)
    # Then inputs in main.tex like \input{sec/intro} mean root/paper/sec/intro.tex
    
    # So the merge base should be the directory containing main.tex
    merge_base = os.path.dirname(main_tex_path)
    main_filename = os.path.basename(main_tex_path)
    
    # rel = os.path.relpath(main_tex_path, base_dir) # This might be wrong if we want to start from main's dir
    
    # Call merge with merge_base as root, and main_filename as the relative path (just the file)
    merged = merge_latex_file(main_filename, merge_base)
    
    # Write output to base_dir (the extract root) or merge_base?
    # Let's write to base_dir so it's easily found, BUT images might be broken if we move the merged file.
    # Actually, if we just want content, path of merged file doesn't matter much for analysis.
    # But for compiling it matters. Here we mainly use it for analysis (Divider).
    
    out_path = os.path.join(base_dir, output_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(merged)
    return out_path

def extract_abstract_from_text(text: str) -> Optional[str]:
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"\\section\*\{\s*Abstract\s*\}(.*?)(?:\\section|\\subsection|\\end\{document\})", text, re.DOTALL | re.IGNORECASE)
    if m2:
        return m2.group(1).strip()
    m3 = re.search(r"\\begin\{摘要\}(.*?)\\end\{摘要\}", text, re.DOTALL)
    if m3:
        return m3.group(1).strip()
    return None

def extract_title_from_text(text: str) -> Optional[str]:
    # Try to find \title{...}
    # We need to handle nested braces, but a simple regex might suffice for most cases
    # or match until the first unbalanced closing brace (hard with regex).
    # Let's try a greedy match that stops at the matching brace if possible, 
    # but python regex doesn't support recursive matching.
    # We'll assume the title doesn't contain unescaped closing braces or use a simpler approach.
    
    # Simple approach: \title{<content>}
    m = re.search(r"\\title\s*\{", text, re.IGNORECASE)
    if m:
        start = m.end()
        brace_count = 1
        i = start
        while i < len(text):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
            
            if brace_count == 0:
                return text[start:i].strip()
            i += 1
    return None

def extract_title_from_dir(root_dir: str) -> Optional[str]:
    main = find_main_tex(root_dir)
    if main:
        try:
            with open(main, "r", encoding="utf-8") as f:
                content = f.read()
            title = extract_title_from_text(content)
            if title:
                return title
        except Exception:
            pass
            
    # Fallback: search all tex files
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".tex"):
                full = os.path.join(dirpath, fn)
                if main and full == main: continue
                try:
                    with open(full, "r", encoding="utf-8") as f:
                        content = f.read()
                    title = extract_title_from_text(content)
                    if title:
                        return title
                except Exception:
                    continue
    return None

def extract_abstract_from_dir(root_dir: str) -> Optional[str]:
    main = find_main_tex(root_dir)
    targets = []
    if main:
        targets.append(main)
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".tex"):
                full = os.path.join(dirpath, fn)
                targets.append(full)
    seen = set()
    for p in targets:
        if p in seen:
            continue
        seen.add(p)
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            abs_text = extract_abstract_from_text(content)
            if abs_text:
                return abs_text
        except Exception:
            continue
    return None

def find_main_md(root_dir: str) -> Optional[str]:
    candidates = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".md"):
                full = os.path.join(dirpath, fn)
                candidates.append(full)
    if not candidates:
        return None
    for p in candidates:
        n = os.path.basename(p).lower()
        if n in ("main.md", "paper.md", "readme.md", "read_me.md"):
            return p
    return sorted(candidates)[0]

def find_main_docx(root_dir: str) -> Optional[str]:
    candidates = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fn in filenames:
            if fn.lower().endswith(".docx"):
                full = os.path.join(dirpath, fn)
                candidates.append(full)
    if not candidates:
        return None
    for p in candidates:
        n = os.path.basename(p).lower()
        if n in ("main.docx", "paper.docx", "report.docx"):
            return p
    return sorted(candidates)[0]

def convert_docx_to_tex(docx_path: str, media_path: str = None) -> str:
    # Use pypandoc to convert docx to latex
    # --standalone to ensure it's a complete document if needed, but Divider might handle fragments.
    # However, for Divider to work, we usually want \documentclass etc.
    args = ['--standalone']
    if media_path:
        args.extend(['--extract-media', media_path])
    
    output = pypandoc.convert_file(docx_path, 'latex', extra_args=args)
    
    # Post-process to fix absolute paths
    if media_path:
        # Pandoc might use absolute paths if media_path is absolute.
        # We want relative paths (e.g., media/image.png) if possible, 
        # or at least paths that work when the tex is compiled in docx_path's dir.
        # Usually extract-media puts files in media_path/media/
        
        # If media_path is absolute, output will have \includegraphics{/abs/path/media/img.png}
        # We replace media_path with "." or just strip it if we assume compilation root is media_path.
        
        # Normalize paths for replacement
        abs_media = os.path.abspath(media_path)
        # We want to replace "abs_media/" with "" so that it becomes relative to the project root
        # But we need to be careful about trailing slashes.
        
        # Replace absolute path with relative path (assuming compilation happens at media_path)
        # Windows/Linux path separators might differ, but pypandoc output usually uses forward slashes in LaTeX?
        # Actually LaTeX uses forward slashes.
        
        abs_media_str = abs_media.replace(os.sep, '/')
        if not abs_media_str.endswith('/'):
            abs_media_str += '/'
            
        output = output.replace(abs_media_str, '')
        
        # Also try without trailing slash just in case
        output = output.replace(abs_media.replace(os.sep, '/'), '')
        
    return output

def convert_md_to_tex(md_content: str) -> str:
    lines = md_content.split('\n')
    new_lines = []
    
    in_code_block = False
    
    # List state: None, 'ul', 'ol'
    list_state = None
    
    # Try to find a title from the first header
    title_found = False
    
    for line in lines:
        stripped_line = line.strip()
        
        # Code block handling
        if stripped_line.startswith('```'):
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
            
        # List Handling
        # Unordered list: - or * or +
        ul_match = re.match(r'^\s*[-*+]\s+(.*)', line)
        # Ordered list: 1. 
        ol_match = re.match(r'^\s*\d+\.\s+(.*)', line)
        
        if ul_match or ol_match:
            new_list_type = 'ul' if ul_match else 'ol'
            content = ul_match.group(1) if ul_match else ol_match.group(1)
            
            if list_state != new_list_type:
                # Close previous list if any
                if list_state == 'ul':
                    new_lines.append('\\end{itemize}')
                elif list_state == 'ol':
                    new_lines.append('\\end{enumerate}')
                
                # Start new list
                if new_list_type == 'ul':
                    new_lines.append('\\begin{itemize}')
                else:
                    new_lines.append('\\begin{enumerate}')
                list_state = new_list_type
            
            # Process content inline (recursion for basic inline styles)
            content = _process_inline_markdown(content)
            new_lines.append(f'\\item {content}')
            continue
        else:
            # Not a list item
            if list_state:
                if list_state == 'ul':
                    new_lines.append('\\end{itemize}')
                elif list_state == 'ol':
                    new_lines.append('\\end{enumerate}')
                list_state = None

        # Blockquote
        if stripped_line.startswith('>'):
            content = stripped_line.lstrip('>').strip()
            content = _process_inline_markdown(content)
            new_lines.append(f'\\begin{{quote}}{content}\\end{{quote}}')
            continue

        # Headers
        header_match = re.match(r'^(#{1,4})\s+(.*)', line)
        if header_match:
            level = len(header_match.group(1))
            title_text = header_match.group(2).strip()
            # Escape title text? headers usually don't have crazy symbols but better safe
            # title_text = _process_inline_markdown(title_text) 
            # (Wait, processing might add \textbf etc which is fine, but escaping % might be needed)
            
            # Treat the very first level-1 header as the document title
            if level == 1 and not title_found:
                new_lines.append(f'\\title{{{title_text}}}')
                new_lines.append('\\maketitle')
                new_lines.append(f'\\section{{{title_text}}}')
                title_found = True
            else:
                if level == 1:
                    new_lines.append(f'\\section{{{title_text}}}')
                elif level == 2:
                    new_lines.append(f'\\subsection{{{title_text}}}')
                elif level == 3:
                    new_lines.append(f'\\subsubsection{{{title_text}}}')
                elif level == 4:
                    new_lines.append(f'\\paragraph{{{title_text}}}')
            continue
            
        # Images
        img_pattern = r'!\[(.*?)\]\((.*?)\)'
        if re.search(img_pattern, line):
            def repl(m):
                alt = m.group(1)
                src = m.group(2)
                return (
                    f"\\begin{{figure}}[htbp]\n"
                    f"\\centering\n"
                    f"\\includegraphics[width=0.8\\textwidth]{{{src}}}\n"
                    f"\\caption{{{alt}}}\n"
                    f"\\end{{figure}}"
                )
            line = re.sub(img_pattern, repl, line)
            new_lines.append(line)
            continue
        
        # Normal line
        line = _process_inline_markdown(line)
        new_lines.append(line)
        
    # Close any open list at the end
    if list_state:
        if list_state == 'ul':
            new_lines.append('\\end{itemize}')
        elif list_state == 'ol':
            new_lines.append('\\end{enumerate}')

    body = '\n'.join(new_lines)
    
    tex = (
        "\\documentclass{article}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{amsmath}\n"
        "\\usepackage[utf8]{inputenc}\n"
        "\\usepackage{hyperref}\n"
        "\\usepackage{url}\n"
        "\\begin{document}\n"
        f"{body}\n"
        "\\end{document}"
    )
    return tex

def _process_inline_markdown(text: str) -> str:
    # 1. Escape special characters (simple approach)
    # We must be careful not to escape Markdown characters * [ ] ( )
    # Safe to escape: % (comment), & (alignment), # (macro param - but used for headers, handled before), _ (subscript), $ (math), { } (grouping)
    # However, if we escape _ here, we break image filenames if processed later?
    # No, images are processed before this function is called for the whole line, BUT here we call it for list content.
    # Let's assume text doesn't contain block-level image syntax if we are here (images handled in main loop).
    
    # We should preserve inline code first to avoid escaping inside it.
    code_placeholders = []
    def code_repl(m):
        code_placeholders.append(m.group(1))
        return f"__CODE_BLOCK_{len(code_placeholders)-1}__"
    
    text = re.sub(r'`(.*?)`', code_repl, text)
    
    # Now escape special chars
    # We only escape % and & for now to be safe. _ is risky if users write filenames.
    # But usually filenames are in links/images.
    text = text.replace('%', '\\%').replace('&', '\\&')
    # text = text.replace('_', '\\_') # Disabling _ escape to avoid breaking things like variable_name in non-code text which might be annoying, but less annoying than breaking latex.
    
    # 2. Links: [text](url) -> \href{url}{text}
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\\href{\2}{\1}', text)
    
    # 3. Bold: **text** -> \textbf{text}
    text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
    
    # 4. Italic: *text* -> \textit{text}
    text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)
    
    # 5. Restore inline code: \texttt{code}
    # We use \texttt for inline code.
    def restore_repl(m):
        idx = int(m.group(1))
        content = code_placeholders[idx]
        # Escape special chars inside code? Verbatim is better but \texttt requires escaping.
        # Minimal escaping for \texttt
        content = content.replace('\\', '\\textbackslash').replace('{', '\\{').replace('}', '\\}').replace('%', '\\%').replace('#', '\\#').replace('&', '\\&').replace('_', '\\_')
        return f"\\texttt{{{content}}}"
        
    text = re.sub(r'__CODE_BLOCK_(\d+)__', restore_repl, text)
    
    return text
