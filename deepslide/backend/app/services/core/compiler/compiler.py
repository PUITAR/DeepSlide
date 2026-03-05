from .tex_compile import (
    compile_content,
    replace_content,
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
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

class Compiler:

    def __init__(self, max_try: int = 3):
        self.max_try = max_try
        
        env_path = os.path.join(os.path.dirname(__file__), '../../../../../../config/env/.env')
        
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            # Try finding env in project root
            # /home/ym/DeepSlide/deepslide-v3/.env
            env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../.env"))
            if os.path.exists(env_path):
                load_dotenv(env_path)
            pass
        
        cfg = resolve_text_llm_env("COMPILER")
        api_key = cfg.api_key
        if not api_key:
            logger.warning("LLM API Key not found. Compressor will not work properly.")
            self.llm_model = None
            self.llm = None
            return

        platform_type = cfg.platform_type
        model_type = cfg.model_type
        base_url = cfg.api_url

        # Initialize LLM
        try:
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
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            self.llm = None
        
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
        
        print(Fore.BLUE + f"🔧 Attempting fix for: {msg} in {file}:{line}" + Fore.RESET)

        # --- Priority 1: Fast Heuristics ---

        # 1. & -> \&
        if "Misplaced alignment tab character &" in msg:
            if self._fast_fix_misplaced_ampersand(base_dir, line if file == 'content.tex' else None):
                return True

        # 2. Undefined control sequence
        if "Undefined control sequence" in msg:
             if self._fast_fix_textrightarrow_typo(base_dir, line if file == 'content.tex' else None):
                 return True
             if self._fast_fix_bbm_package(base_dir):
                 return True
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

        if "Missing \\endcsname inserted" in msg:
            if self._fast_fix_unescape_cite_keys(base_dir, line if file == 'content.tex' else None):
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
                    print(Fore.GREEN + f"⚡ Fast Fix applied: Added \\usepackage{{capt-of}} to base.tex" + Fore.RESET)
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
                print(Fore.GREEN + "⚡ Fast Fix applied: Added \\usepackage{booktabs} to base.tex" + Fore.RESET)
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
                print(Fore.GREEN + "⚡ Fast Fix applied: Un-commented \\end{pgfonlayer}}} in base.tex" + Fore.RESET)
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
                            print(Fore.GREEN + f"⚡ Fast Fix: Removed corrupted base.toc" + Fore.RESET)
                        except: pass

            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False
            title_path = os.path.join(base_dir, "title.tex")
            if not os.path.exists(title_path): return False

            fixed_any = False
            
            def needs_fix(text):
                return bool(re.search(r'(?<!\\)&', text))

            def fix_line(text):
                return re.sub(r'(?<!\\)&', r'\\&', text)

            # fix content bug
            with open(content_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num is not None:
                idx = line_num - 1
                if 0 <= idx < len(lines):
                    if needs_fix(lines[idx]):
                        lines[idx] = fix_line(lines[idx])
                        fixed_any = True
                        print(Fore.GREEN + f"⚡ Fast Fix applied: Replaced & with \\& on line {line_num}" + Fore.RESET)
            else:
                for idx, line in enumerate(lines):
                    if needs_fix(line):
                        if re.match(r'^\s*\\(section|subsection|frametitle|caption|item)', line):
                            lines[idx] = fix_line(line)
                            fixed_any = True
                        elif " & " in line and not line.strip().endswith(r'\\'):
                            lines[idx] = fix_line(line)
                            fixed_any = True

            # fix title bug
            with open(title_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num is not None:
                idx = line_num - 1
                if 0 <= idx < len(lines):
                    if needs_fix(lines[idx]):
                        lines[idx] = fix_line(lines[idx])
                        fixed_any = True
                        print(Fore.GREEN + f"⚡ Fast Fix applied: Replaced & with \\& on line {line_num}" + Fore.RESET)
            else:
                for idx, line in enumerate(lines):
                    if needs_fix(line):
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
        Action: Escape _ to \\_ if found in text.
        """
        try:
            # Cleanup .toc first (common source of Missing $)
            toc_path = os.path.join(base_dir, "base.toc")
            if os.path.exists(toc_path):
                try:
                    os.remove(toc_path)
                    print(Fore.GREEN + f"⚡ Fast Fix: Removed potential corrupted base.toc (Math Error)" + Fore.RESET)
                except: pass

            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return False
            title_path = os.path.join(base_dir, "title.tex")
            if not os.path.exists(title_path): return False

            fixed_any = False
            
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
            ENV_END_RE = re.compile(r"^\s*\\end\{([^}]+)\}")

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
                    m = ENV_END_RE.match(line)
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

                        cmd_token = code[i:j]
                        out.append(cmd_token)
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

                        def _consume_optional_brackets(start_idx: int) -> int:
                            k2 = start_idx
                            while k2 < len(code) and code[k2].isspace():
                                k2 += 1
                            while k2 < len(code) and code[k2] == "[":
                                depth = 0
                                while k2 < len(code):
                                    ch2 = code[k2]
                                    if ch2 == "\\":
                                        k2 += 2
                                        continue
                                    if ch2 == "[":
                                        depth += 1
                                    elif ch2 == "]":
                                        depth -= 1
                                        if depth == 0:
                                            k2 += 1
                                            break
                                    k2 += 1
                                while k2 < len(code) and code[k2].isspace():
                                    k2 += 1
                            return k2

                        if cmd in SKIP_BRACED_COMMANDS:
                            k = _consume_optional_brackets(i)
                            if k < len(code) and code[k] == "{":
                                parsed = _parse_balanced_braces(code, k)
                                if parsed:
                                    _, end_idx = parsed
                                    out.append(code[k:end_idx])
                                    i = end_idx
                            continue

                        if cmd in SKIP_FIRST_ARG_COMMANDS:
                            k = _consume_optional_brackets(i)
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
                        if in_math():
                            out.append("_")
                        else:
                            out.append(r"\_")
                        i += 1
                        continue

                    out.append(ch)
                    i += 1

                return "".join(out) + comment

            def _advance_state_only(line: str) -> None:
                _process_underscore_line(line, escape=False)

            def fix_underscore(text: str) -> str:
                return _process_underscore_line(text, escape=True)

            def needs_fix(text: str) -> bool:
                return "_" in text

            # fix content bug
            with open(content_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num is not None:
                scan_state = _make_initial_state()
                idx = line_num - 1
                if 0 <= idx < len(lines):
                    if needs_fix(lines[idx]):
                        for pre_i in range(idx):
                            _advance_state_only(lines[pre_i])
                        new_line = fix_underscore(lines[idx])
                        if new_line != lines[idx]:
                            lines[idx] = new_line
                            fixed_any = True
                            print(Fore.GREEN + f"⚡ Fast Fix applied: Replaced _ with \\_ on line {line_num}" + Fore.RESET)
            else:
                # Global scan
                scan_state = _make_initial_state()
                for idx, line in enumerate(lines):
                    if needs_fix(line):
                        new_line = fix_underscore(line)
                        if new_line != line:
                            lines[idx] = new_line
                            fixed_any = True
                            print(Fore.GREEN + f"⚡ Fast Fix applied: Replaced _ with \\_ on line {idx+1} (Smart)" + Fore.RESET)
                    else:
                        _advance_state_only(line)

            # yangming title may have such problem
            # fix title bug
            with open(title_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if line_num is not None:
                scan_state = _make_initial_state()
                idx = line_num - 1
                if 0 <= idx < len(lines):
                    if needs_fix(lines[idx]):
                        for pre_i in range(idx):
                            _advance_state_only(lines[pre_i])
                        new_line = fix_underscore(lines[idx])
                        if new_line != lines[idx]:
                            lines[idx] = new_line
                            fixed_any = True
                            print(Fore.GREEN + f"⚡ Fast Fix applied: Replaced _ with \\_ on line {line_num}" + Fore.RESET)
            else:
                # Global scan
                scan_state = _make_initial_state()
                for idx, line in enumerate(lines):
                    if needs_fix(line):
                        new_line = fix_underscore(line)
                        if new_line != line:
                            lines[idx] = new_line
                            fixed_any = True
                            print(Fore.GREEN + f"⚡ Fast Fix applied: Replaced _ with \\_ on line {idx+1} (Smart)" + Fore.RESET)
                    else:
                        _advance_state_only(line)

            if fixed_any:
                with open(content_path, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return True
        except Exception:
            pass
        return False

    def _fast_fix_unescape_cite_keys(self, base_dir: str, line_num: Optional[int]) -> bool:
        try:
            content_path = os.path.join(base_dir, "content.tex")
            title_path = os.path.join(base_dir, "title.tex")

            cite_re = re.compile(r"(\\cite[a-zA-Z*]*)(\s*(?:\[[^\]]*\]\s*)*)\{([^}]*)\}")
            bibitem_re = re.compile(r"(\\bibitem)(\s*(?:\[[^\]]*\]\s*)*)\{([^}]*)\}")

            def fix_line(s: str) -> str:
                def repl(m: re.Match) -> str:
                    keys = m.group(3)
                    fixed_keys = keys.replace(r"\_", "_")
                    if fixed_keys == keys:
                        return m.group(0)
                    return f"{m.group(1)}{m.group(2)}{{{fixed_keys}}}"

                s2 = cite_re.sub(repl, s)
                s3 = bibitem_re.sub(repl, s2)
                return s3

            fixed_any = False

            if os.path.exists(content_path):
                with open(content_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                if line_num is not None and 0 <= line_num - 1 < len(lines):
                    idx = line_num - 1
                    new_line = fix_line(lines[idx])
                    if new_line != lines[idx]:
                        lines[idx] = new_line
                        fixed_any = True
                else:
                    for i, line in enumerate(lines):
                        new_line = fix_line(line)
                        if new_line != line:
                            lines[i] = new_line
                            fixed_any = True
                if fixed_any:
                    with open(content_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

            title_fixed = False
            if os.path.exists(title_path):
                with open(title_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    new_line = fix_line(line)
                    if new_line != line:
                        lines[i] = new_line
                        title_fixed = True
                if title_fixed:
                    with open(title_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

            if fixed_any or title_fixed:
                print(Fore.GREEN + "⚡ Fast Fix applied: Repaired escaped underscores in citation keys" + Fore.RESET)
                return True
        except Exception as e:
            logger.error(f"Fast fix cite key underscore failed: {e}")
        return False

    def _fast_fix_textrightarrow_typo(self, base_dir: str, line_num: Optional[int]) -> bool:
        try:
            content_path = os.path.join(base_dir, "content.tex")
            title_path = os.path.join(base_dir, "title.tex")

            fixed_any = False
            if os.path.exists(content_path):
                with open(content_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()

                if line_num is not None and 0 <= line_num - 1 < len(lines):
                    idx = line_num - 1
                    if r"\texightarrow" in lines[idx]:
                        lines[idx] = lines[idx].replace(r"\texightarrow", r"\textrightarrow")
                        fixed_any = True
                else:
                    for i, line in enumerate(lines):
                        if r"\texightarrow" in line:
                            lines[i] = line.replace(r"\texightarrow", r"\textrightarrow")
                            fixed_any = True

                if fixed_any:
                    with open(content_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

            title_fixed = False
            if os.path.exists(title_path):
                with open(title_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                for i, line in enumerate(lines):
                    if r"\texightarrow" in line:
                        lines[i] = line.replace(r"\texightarrow", r"\textrightarrow")
                        title_fixed = True
                if title_fixed:
                    with open(title_path, "w", encoding="utf-8") as f:
                        f.writelines(lines)

            if fixed_any or title_fixed:
                print(Fore.GREEN + "⚡ Fast Fix applied: Fixed \\texightarrow typo (\\textrightarrow)" + Fore.RESET)
                return True
        except Exception as e:
            logger.error(f"Fast fix textrightarrow typo failed: {e}")
        return False

    def _fast_fix_bbm_package(self, base_dir: str) -> bool:
        try:
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path):
                return False
            with open(content_path, "r", encoding="utf-8", errors="replace") as f:
                c = f.read()
            if r"\mathbbm" not in c:
                return False

            base_path = os.path.join(base_dir, "base.tex")
            if not os.path.exists(base_path):
                return False
            with open(base_path, "r", encoding="utf-8", errors="replace") as f:
                base = f.read()
            if r"\usepackage{bbm}" in base:
                return False

            new_base = re.sub(r"(\\documentclass.*?\]\{beamer\})", r"\1\n\\usepackage{bbm}", base, count=1)
            if new_base == base:
                new_base = base.replace(r"\begin{document}", r"\usepackage{bbm}" + "\n" + r"\begin{document}")
            if new_base != base:
                with open(base_path, "w", encoding="utf-8") as f:
                    f.write(new_base)
                print(Fore.GREEN + "⚡ Fast Fix applied: Added \\usepackage{bbm} to base.tex" + Fore.RESET)
                return True
        except Exception as e:
            logger.error(f"Fast fix bbm package failed: {e}")
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
            # This handles nested frames poorly, but Beamer frames shouldn't be nested.
            
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
                                print(Fore.GREEN + f"⚡ Fast Fix applied: Added [fragile] to frame at line {current_frame_start_idx+1}" + Fore.RESET)
                        
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
                print(Fore.GREEN + f"⚡ Fast Fix applied: {res}" + Fore.RESET)
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
                print(Fore.GREEN + "⚡ Fast Fix applied: Replaced Unicode characters with '?'" + Fore.RESET)
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
        print(Fore.BLUE + "🤖 Launching Compiler Agent..." + Fore.RESET)
        
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
Your target is to compile the BEAMER slide successfully, DO NOT change the document class to `article`.
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
        
        max_steps = 20 # Increased for compile/verify loop
        step = 0
        
        while step < max_steps:
            try:
                response = agent.step(usr_msg)
                content = response.msg.content
                
                # Print agent's thought process
                if content:
                    print(Fore.YELLOW + f"\n🤖 [Agent Thought]\n{content}" + Style.RESET_ALL)
                
                if "FIXED" in content:
                    print(Fore.GREEN + "✅ Agent reported fix applied." + Fore.RESET)
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
        print(Fore.CYAN + "🔍 Pre-checking image paths..." + Fore.RESET)
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
                
                print(Fore.YELLOW + f"⚠️ Image not found: {raw_path}. Searching..." + Fore.RESET)
                
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
                    print(Fore.GREEN + f"✅ Restored {raw_path} -> {new_rel_path}" + Fore.RESET)
                else:
                    print(Fore.RED + f"❌ Could not find image: {filename}" + Fore.RESET)
            
            for old, new in replacements.items():
                new_content = new_content.replace(f"{{{old}}}", f"{{{new}}}")
            
            if new_content != content:
                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(Fore.GREEN + "📝 Updated content.tex with fixed image paths." + Fore.RESET)
                
        except Exception as e:
            print(Fore.RED + f"Pre-check images error: {e}" + Fore.RESET)

    def run(self, base_dir: str, source_dir: str = None):
        """
        Compile the LaTeX document in the `base_dir`.
        """
        self._pre_check_images(base_dir, source_dir=source_dir)

        for i in range(self.max_try):
            print(Fore.CYAN + f"\n[Try {i+1}] LaTeX compile..." + Fore.RESET)

            # 1. Compile
            result = compile_content(base_dir)

            # 2. Success?
            if result.get("success"):
                print(Fore.GREEN + "✅ Compile success" + Fore.RESET)
                return result

            # 3. Handle Errors
            errors = result.get("errors", [])
            valid_errors = [e for e in errors if e.get('message')]
            if not valid_errors:
                print(Fore.RED + "Unknown error occurred (no log output)." + Fore.RESET)
                break

            error_summary = "\n".join([f"Error: {e.get('message')} (file={e.get('file')}, line {e.get('line')})" for e in valid_errors])
            print(Fore.RED + error_summary + Fore.RESET)

            print(Fore.BLUE + "🤖 Attempting autonomous fix..." + Fore.RESET)
            if self._attempt_fix(base_dir, valid_errors):
                continue # Retry loop
            else:
                print(Fore.RED + "❌ Fix attempt failed." + Fore.RESET)

        # Final attempt
        result = compile_content(base_dir)
        if result.get("success"):
            print(Fore.GREEN + "✅ Compile success" + Fore.RESET)
        
        return result
