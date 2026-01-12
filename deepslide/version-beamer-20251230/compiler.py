from content import Content
from frame import Frame
from section import Section
from tex_compile import (
    compile_content,
    replace_content,
    update_title,
    update_base,
)

from colorama import Fore

# from camel.societies import RolePlaying
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
# from camel.toolkits import OpenAIFunction
from camel.agents import ChatAgent

from dotenv import load_dotenv
import os
import logging

from pprint import pprint

# 正则表达式提取标签中的内容
# 1. <content></content>
# 2. <title></title>
import re

from typing import Any

logger = logging.getLogger(__name__)

class Compiler:

    def __init__(self, max_try: int = 3):
        self.max_try = max_try

        # Initialize usr_prompt first to avoid AttributeError if early return happens
        print("DEBUG: Initializing Compiler and usr_prompt...")
        # usr_prompt_path = os.path.join(os.path.dirname(__file__), 'prompts/usr_prompt_compiler.md')
        self.usr_prompt = """[Error file]
{0}
[Error message]
{1}
[Error snippet]
{2}
"""
        print(f"DEBUG: Used default usr_prompt")
        
        # env_path = os.path.join(os.path.dirname(__file__), '../config/.env')
        env_path = os.path.join(os.path.dirname(__file__), '../../config/env/.env')
        
        if os.path.exists(env_path):
            load_dotenv(env_path)
        
        api_key = os.getenv('DEFAULT_MODEL_API_KEY') or os.getenv('LLM_API_KEY')
        if not api_key:
            logger.warning("LLM API Key not found. Compressor will not work properly.")
            self.llm_model = None
            self.agent = None # Ensure agent is explicitly None
            return

        model_type = os.getenv('DEFAULT_MODEL_TYPE', 'deepseek-chat')
        base_url = os.getenv('DEFAULT_MODEL_API_URL', 'https://api.deepseek.com')

        # tool list
        # TODO 后续考虑增加网络工具，从外部查询可能的解决方法
        from camel.toolkits import FunctionTool
        
        def list_files(path: str) -> str:
            """List files in the directory."""
            try:
                if not os.path.exists(path):
                    return f"Error: Path {path} does not exist."
                files = []
                for root, dirs, fnames in os.walk(path):
                    for fname in fnames:
                         files.append(os.path.relpath(os.path.join(root, fname), path))
                return "\n".join(files)
            except Exception as e:
                return f"Error: {e}"

        def copy_file(src: str, dst: str) -> str:
            """Copy a file from src to dst. Both paths should be absolute or relative to base_dir."""
            import shutil
            try:
                # If paths are relative, they might be relative to CWD.
                # Ideally, we should handle paths relative to base_dir, but tool doesn't know base_dir implicitly.
                # We will rely on Agent to provide full paths or relative paths correctly.
                # Or we can assume paths are relative to base_dir if they don't start with /
                
                # Check if src exists
                if not os.path.exists(src):
                     return f"Error: Source file {src} does not exist."
                
                dst_dir = os.path.dirname(dst)
                if dst_dir and not os.path.exists(dst_dir):
                    os.makedirs(dst_dir, exist_ok=True)
                
                shutil.copy2(src, dst)
                return f"Successfully copied {src} to {dst}"
            except Exception as e:
                return f"Error copying file: {e}"
        
        def find_file(filename: str, search_path: str) -> str:
             """Find a file by name in search_path (recursive). 
             If exact match fails, tries to match files starting with `filename` (useful for truncated log errors).
             Returns full path if found.
             """
             try:
                 # 1. Exact match
                 for root, dirs, files in os.walk(search_path):
                     if filename in files:
                         return os.path.join(root, filename)
                 
                 # 2. Partial match (starts with) - common in LaTeX log errors where filename is truncated
                 # Only if filename is long enough to be distinct (> 3 chars)
                 if len(filename) > 3:
                     for root, dirs, files in os.walk(search_path):
                         for f in files:
                             if f.startswith(filename):
                                 return os.path.join(root, f)
                                 
                 return "File not found."
             except Exception as e:
                 return f"Error finding file: {e}"
        
        def read_file(filepath: str, start_line: int = None, end_line: int = None) -> str:
            """Read content of a file. Optionally specify start_line and end_line (1-based).
            If no lines specified, reads first 2000 characters (truncated).
            """
            if not os.path.exists(filepath): return "File not found"
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    if start_line is None and end_line is None:
                        # Default behavior: Read with limit
                        content = f.read(2000)
                        if len(content) == 2000: content += "\n... (truncated)"
                        return content
                    
                    # Line based reading
                    f.seek(0)
                    lines = f.readlines()
                
                total_lines = len(lines)
                if start_line is None: start_line = 1
                if end_line is None: end_line = total_lines
                
                if start_line < 1: start_line = 1
                if end_line > total_lines: end_line = total_lines
                
                if start_line > end_line: return "Invalid line range."
                
                # Adjust to 0-based index
                content = "".join(lines[start_line-1:end_line])
                return f"File: {filepath} (Lines {start_line}-{end_line} of {total_lines})\n{content}"
            except Exception as e:
                return f"Error reading file: {e}"

        def write_file(filepath: str, content: str) -> str:
            """Write content to a file (overwrite)."""
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                return "Write success"
            except Exception as e:
                return f"Write error: {e}"
        
        def get_content_map(base_dir: str) -> str:
            """Get the mapping of content objects (frames/sections) with line numbers."""
            try:
                # Use local imports to avoid circular dependency or path issues if called as tool
                try:
                    from content import Content
                    from frame import Frame
                    from section import Section
                except ImportError:
                    # Fallback if running in a context where pwd is not version-1
                    import sys
                    sys.path.append(os.path.dirname(__file__))
                    from content import Content
                    from frame import Frame
                    from section import Section

                c = Content()
                c.from_file(os.path.join(base_dir, "content.tex"))
                
                # mapping = []
                lines_so_far = 1
                result = []
                from frame import Frame
                from section import Section
                for idx, item in enumerate(c):
                    typ = "Frame" if isinstance(item, Frame) else ("Section" if isinstance(item, Section) else type(item).__name__)
                    # Matches to_file logic:
                    # f.write(f"%% ITEM {idx} TYPE {typ}\n") -> 1 line
                    lines_so_far += 1 
                    
                    text = str(item)
                    cnt = text.count("\n")
                    start = lines_so_far
                    end = lines_so_far + cnt - 1
                    # lines_so_far = end + 1 # Logic from to_file seems to match this
                    # But wait, end + 1 is next line.
                    lines_so_far = end + 1
                    
                    result.append(f"Index {idx}: {typ} (Lines {start}-{end})")
                return "\n".join(result)
            except Exception as e:
                return f"Error: {e}"

        def update_content_object_tool(base_dir: str, idx: int, new_text: str) -> str:
            """Update a specific content object (Frame or Section) by index.
            Args:
                base_dir: Project base directory.
                idx: The index of the object to update (get this from get_content_map).
                new_text: The new LaTeX content for this object.
            """
            try:
                res = replace_content(base_dir, idx, new_text)
                if res: return "Update success"
                return "Update failed"
            except Exception as e:
                return f"Update error: {e}"

        def scan_latex_log(base_dir: str) -> str:
            """
            Scan the LaTeX log file to extract errors with file and line context.
            Returns a JSON-like string of errors.
            """
            log_path = os.path.join(base_dir, "base.log")
            if not os.path.exists(log_path):
                return "Log file not found."
            
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                
                errors = []
                # Regex for file entry: (./filename.tex or (/path/filename.tex
                # We need to track the file stack to know which file an error belongs to.
                file_stack = []
                
                # Regex to match file entry
                # Matches: (./content.tex  or  (/app/content.tex
                file_entry_pattern = re.compile(r'\((?P<path>[^)\s]+\.tex)')
                
                for i, line in enumerate(lines):
                    # 1. Update file stack
                    # Count ')' to pop stack
                    # This is imperfect because ')' appears in text, but LaTeX log structure usually balances them.
                    # A better heuristic: if line starts with ')' or ' )', pop.
                    
                    # Check for file entry
                    m = file_entry_pattern.search(line)
                    if m:
                        fpath = m.group('path')
                        fname = os.path.basename(fpath)
                        file_stack.append(fname)
                    
                    # Check for file exit (heuristic)
                    # Close parens can be anywhere. This is the hardest part of LaTeX log parsing.
                    # We will rely on the "file_entry" being recent for the error.
                    # Or simpler: if error line has "l.123", we look backwards for the last opened file.
                    
                    if line.strip().startswith('!') or "LaTeX Error" in line:
                        # Found an error
                        msg = line.strip()
                        line_num = None
                        context_lines = lines[i:min(i+10, len(lines))]
                        
                        # Find line number in context
                        for cline in context_lines:
                            lm = re.search(r'l\.(\d+)', cline)
                            if lm:
                                line_num = int(lm.group(1))
                                break
                        
                        # Guess file from stack
                        current_file = file_stack[-1] if file_stack else "unknown"
                        
                        # Heuristic: if file_stack is empty, try to find file in recent lines
                        if current_file == "unknown":
                            for j in range(max(0, i-20), i):
                                m = file_entry_pattern.search(lines[j])
                                if m:
                                    current_file = os.path.basename(m.group('path'))
                        
                        errors.append({
                            "error": msg,
                            "file": current_file,
                            "line": line_num,
                            "log_line_index": i
                        })
                        
                        if len(errors) >= 10: break # Limit number of errors
                
                if not errors:
                    return "No explicit errors found in log."
                
                import json
                return json.dumps(errors, indent=2)

            except Exception as e:
                return f"Error scanning log: {e}"

        tool_list = [
            FunctionTool(list_files),
            FunctionTool(copy_file),
            FunctionTool(find_file),
            FunctionTool(read_file),
            FunctionTool(write_file),
            FunctionTool(get_content_map),
            FunctionTool(update_content_object_tool),
            FunctionTool(scan_latex_log)
        ]

        # 初始化 LLM
        llm = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type=model_type,
            url=base_url,
            api_key=api_key,
            model_config_dict={
                # "tools": tool_list, # Moved tools to ChatAgent init
                "temperature": 0.0,
                "max_tokens": 8192
            },
        )

        sys_msg_content = r"""You are an intelligent LaTeX compiler error-diagnosis agent. Based on the error message and the faulty snippet:

- If the error comes from the content.tex, fix and return the corrected content wrapped in <content></content> tags. 
- If the error comes from the title.tex, fix and return the corrected title wrapped in <title></title> tags.
- If the error comes from the base.tex fix the error and return the corrected base wrapped in <base></base> tags.

Ensure the revised title/content complies with LaTeX syntax.

*Example 1*:
[Error file]
content

[Error message]
! Misplaced alignment tab character &.

[Error snippet]
\begin{frame}
\textbf{Basic Concepts for RL}:
    \begin{itemize}
        \item \textit{State}, \textit{Action}, \textit{Reward}
        \item  State Transition, Policy $\pi(a|s)$
        \begin{figure}
            \includegraphics[width=.8\linewidth]{picture/rlsys.png}
        \end{figure}
        \item Trajectory, Episode, Return (discounted)
        &s_{1}\xrightarrow[r=0]{a_{2}} s_{2}\xrightarrow[r=0]{a_{3}}
        \xrightarrow[r=0]{a_{3}} s_{8}\xrightarrow[r=1]{a_{2}}
        s_{9}\xrightarrow[r=1]{a_{5}} s_{9}\xrightarrow[r=1]{a_{5}} s_{9}\ldots \\
        &returns = r_1 + \gamma r_2 + \gamma^2 r_3 + \gamma^3 r_4 + \ldots
        \end{align*}
    \end{itemize}
\end{frame}

[Return]
<content>
\begin{frame}
\textbf{Basic Concepts for RL}:
    \begin{itemize}
        \item \textit{State}, \textit{Action}, \textit{Reward}
        \item  State Transition, Policy $\pi(a|s)$
        \begin{figure}
            \includegraphics[width=.8\linewidth]{picture/rlsys.png}
        \end{figure}
        \item Trajectory, Episode, Return (discounted)
        \begin{align*} %% 补充对齐环境
        &s_{1}\xrightarrow[r=0]{a_{2}} s_{2}\xrightarrow[r=0]{a_{3}}
        \xrightarrow[r=0]{a_{3}} s_{8}\xrightarrow[r=1]{a_{2}}
        s_{9}\xrightarrow[r=1]{a_{5}} s_{9}\xrightarrow[r=1]{a_{5}} s_{9}\ldots \\
        &returns = r_1 + \gamma r_2 + \gamma^2 r_3 + \gamma^3 r_4 + \ldots
        \end{align*}
    \end{itemize}
\end{frame}
</content>

*Example 2*:
[Error file]
title

[Error message]
! LaTeX Error: Missing \begin{document}.

[Error snippet]
\title{LLM Post-train Algorithms: A Survey}
\author{Ming Yang (Puitar)}
\institute{Fudan University}{yangm24@m.fudan.edu.cn}

[Return]
<title>
\title{LLM Post-train Algorithms: A Survey}
\author{Ming Yang (Puitar)}
\institute[Fudan University]{yangm24@m.fudan.edu.cn}
</title>

Now, the user has provided the following message:
"""

        sys_msg = BaseMessage.make_assistant_message(
            role_name="Compiler Agent",
            content=sys_msg_content
        )

        self.agent = ChatAgent(sys_msg, model=llm, tools=tool_list)

        # Removed redundant usr_prompt initialization here as it's done at the start of __init__

        # logger.info(f"usr_prompt: {self.usr_prompt}")
        # print(self.usr_prompt)
        # print(self.usr_prompt)



    def _fix_with_agent_analysis(self, base_dir: str, error_message: str) -> bool:
        # Prompt logic
        prompt = f"""
Compilation failed with error: {error_message}
Project directory: {base_dir}

Task:
1. **Analyze**: Use `scan_latex_log` to identify the specific file and line number of the error from 'base.log'. This tool is efficient and parses the log for you.
   - **Heuristic 1**: If the error context shows `l.xxx \\end{{frame}}`, the error is definitely inside a `frame` environment in `content.tex`.
   - **Heuristic 2**: If the error is about "Missing $ inserted" or "Undefined control sequence" near `\\title` or `\\author`, check `title.tex`.
   - **Heuristic 3**: If the log shows "File `...` not found", check the line number. If it's inside a frame, it's likely an image in `content.tex`. If it's in the preamble, it's `base.tex`, `title.tex` or `format.tex`.
   - **Heuristic 4**: Look for "Package hyperref Warning: Token not allowed in a PDF string" - this often points to special characters in `title.tex`.
2. **Locate**:
   - If the error is in 'content.tex', use `get_content_map` to find which object index corresponds to that line.
   - If the error is in other files (base.tex, title.tex, ref.bib, format.tex, etc.), identify the file path.
3. **Inspect**: Use `read_file(filepath, start_line=..., end_line=...)` to see the problematic code.
   - **CRITICAL**: Do NOT read the entire file if it is large. Read only the relevant lines around the error (e.g. error_line - 10 to error_line + 10).
   - If the error message mentions a specific string (e.g. "pg.jpg"), search for that string in the file.
4. **Fix**:
   - For 'content.tex', use `update_content_object_tool` to fix the specific frame/section.
   - For other files, use `write_file` to overwrite the fixed content.
   - If a file is missing, use `find_file` and `copy_file`.
5. **Report**: If you have successfully used a tool to fix the issue, reply with "Fix: [explanation]". 

**Do NOT read the entire 'base.log' directly as it is too large.** Use `scan_latex_log`.
"""
        user_msg = BaseMessage.make_user_message(role_name="User", content=prompt)
        
        # Increase timeout for complex analysis
        self.agent.step_timeout = 500
        
        # Track if any tool was successfully executed
        tool_executed = False
        
        # Loop
        for _ in range(8): # Give it more steps
             response = self.agent.step(user_msg)
             
             # Check for tool execution success
             # Expanded to include format.tex fixes which might use write_file
             if "Update success" in str(response.info) or "Write success" in str(response.info) or "Successfully copied" in str(response.info):
                  tool_executed = True
                  print(Fore.YELLOW + f"🔧 Agent successfully executed tool.\n" + Fore.RESET)
             
             # check termination or success
             if "Fix:" in str(response.msg.content):
                 if tool_executed:
                     print(Fore.YELLOW + f"🔧 {response.msg.content}\n" + Fore.RESET)
                     return True
                 else:
                     # Agent claimed fix but didn't use tool. 
                     print(Fore.RED + f"⚠️ Agent claimed fix but no tool modification detected. Ignoring: {response.msg.content}\n" + Fore.RESET)
                     
                     # Force retry if agent claims fix but didn't act
                     # We can append a message to force tool usage
                     user_msg = BaseMessage.make_user_message(role_name="User", content="You claimed a fix but did not use any tool to apply it. You MUST use `write_file`, `update_content_object_tool`, or `copy_file` to actually modify the file system. Please apply the fix now.")
                     continue
             
             if tool_executed:
                  print(Fore.YELLOW + f"🔧 Agent used tool to fix. Returning success.\n" + Fore.RESET)
                  return True
             
             if response.terminated:
                 break
        return False

    def _fix_title(self, base_dir: str, error_message: str) -> bool:
        try:
            curr_title = open(os.path.join(base_dir, 'title.tex'), 'r', encoding='utf-8').read()
            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=self.usr_prompt.format("title", error_message, curr_title)
            )

            response = self.agent.step(user_msg)
            correct_title = response.msg.content

            match = re.search(r'<title>(.*?)</title>', correct_title, re.DOTALL)
            if match:
                correct_title = match.group(1).strip()
            else:
                return False

            # 替换错误标题
            result = update_title(base_dir, correct_title)
            if result:
                print(
                    Fore.YELLOW + f"🔧 Fix: title\n" + Fore.RESET,
                    f"{correct_title}"
                )
                return True
        except Exception as e:
            logger.error(f"Error fixing title: {e}")
        return False

    def _fix_content(self, base_dir: str, error_message: str, obj_idx: int = None) -> bool:
        try:
            content = Content()
            content.from_file(os.path.join(base_dir, 'content.tex'))
            if obj_idx is not None and 0 <= obj_idx < len(content):
                snippet = content[obj_idx]
            else:
                snippet = open(os.path.join(base_dir, 'content.tex'), 'r', encoding='utf-8').read()
        except Exception as e_read:
            logger.error(f"Error reading content: {e_read}")
            return False

        try:
            # Enhanced prompt for file missing errors
            prompt_suffix = ""
            if "not found" in error_message.lower() or "unable to load" in error_message.lower():
                # Replace local path with Docker path for tool usage hint
                # Dynamic project root detection
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                docker_base_dir = base_dir.replace(project_root, "/app")
                local_search_dir = os.path.join(project_root, "deepslide", "tmp_uploads")
                
                prompt_suffix = f"\n\nHint: It seems like a file is missing. The compilation runs in a Docker container where `{project_root}` is mapped to `/app`. \nWhen using tools:\n- `list_files` in `{base_dir}` (local path) to see current files.\n- `find_file` in `{local_search_dir}` (local path) to find missing assets from the original upload.\n  - Note: Filenames in LaTeX error logs are often truncated. `find_file` supports partial matching, so try searching for the first part of the filename.\n- `copy_file` to copy found files to `{base_dir}`.\n\nIMPORTANT: \n1. **PRIORITY 1**: Try your best to FIND and COPY the missing file. If the path in LaTeX is wrong, fix the path in LaTeX or copy the file to the expected path.\n2. **PRIORITY 2**: Only if you have searched exhaustively and the file is definitely not in the project, replace the \\includegraphics command with a text placeholder like \\textbf{{[Image missing: filename]}}."

            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=self.usr_prompt.format("content", error_message, snippet) + prompt_suffix
            )

            # Increase timeout for file operations
            self.agent.step_timeout = 60 # wait up to 60s
            
            # Allow multiple steps for tool usage
            response = None
            for _ in range(5): # Allow up to 5 steps (thought/action loop)
                response = self.agent.step(user_msg)
                if response.terminated or "Fix:" in str(response.msg.content) or "<content>" in str(response.msg.content):
                    break
            
            if not response: return False
            
            correct_content = response.msg.content
            # get content from <content></content> wrapper
            match = re.search(r'<content>(.*?)</content>', correct_content, re.DOTALL)
            if match:
                correct_content = match.group(1).strip()
                # 4. 替换错误对象
                result = replace_content(base_dir, obj_idx, correct_content)
                if result:
                    print(
                        Fore.YELLOW + f"🔧 Fix: {obj_idx}-th object of content\n" + Fore.RESET,
                        f"{correct_content}"
                    )
                    return True
            else:
                # Check for tool usage success indication
                if "Successfully copied" in str(response.info) or "Successfully copied" in str(correct_content):
                     print(Fore.YELLOW + f"🔧 Fix: File copied/restored via tool.\n" + Fore.RESET)
                     return True
                
                return False

        except Exception as e:
            logger.error(f"Error fixing content: {e}")
        return False

    def _fix_base(self, base_dir: str, error_message: str) -> bool:
        try:
            curr_base = open(os.path.join(base_dir, 'base.tex'), 'r', encoding='utf-8').read()
            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=self.usr_prompt.format("base", error_message, curr_base)
            )

            response = self.agent.step(user_msg)
            correct_base = response.msg.content

            # get base from <base></base> wrapper
            match = re.search(r'<base>(.*?)</base>', correct_base, re.DOTALL)
            if match:
                correct_base = match.group(1).strip()
            else:
                return False

            # 替换错误base
            result = update_base(base_dir, correct_base)
            if result:
                print(
                    Fore.YELLOW + f"🔧 Fix: base\n" + Fore.RESET,
                    f"{correct_base}"
                )
                return True
        except Exception as e:
            logger.error(f"Error fixing base: {e}")
        return False


    def _fix_title(self, base_dir: str, error_message: str) -> bool:
        try:
            curr_title = open(os.path.join(base_dir, 'title.tex'), 'r', encoding='utf-8').read()
            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=self.usr_prompt.format("title", error_message, curr_title)
            )

            response = self.agent.step(user_msg)
            correct_title = response.msg.content

            match = re.search(r'<title>(.*?)</title>', correct_title, re.DOTALL)
            if match:
                correct_title = match.group(1).strip()
            else:
                return False

            # 替换错误标题
            result = update_title(base_dir, correct_title)
            if result:
                print(
                    Fore.YELLOW + f"🔧 Fix: title\n" + Fore.RESET,
                    f"{correct_title}"
                )
                return True
        except Exception as e:
            logger.error(f"Error fixing title: {e}")
        return False

    def _fix_content(self, base_dir: str, error_message: str, obj_idx: int = None) -> bool:
        try:
            content = Content()
            content.from_file(os.path.join(base_dir, 'content.tex'))
            if obj_idx is not None and 0 <= obj_idx < len(content):
                snippet = content[obj_idx]
            else:
                snippet = open(os.path.join(base_dir, 'content.tex'), 'r', encoding='utf-8').read()
        except Exception as e_read:
            logger.error(f"Error reading content: {e_read}")
            return False

        try:
            # Enhanced prompt for file missing errors
            prompt_suffix = ""
            if "not found" in error_message.lower() or "unable to load" in error_message.lower():
                prompt_suffix = f"\n\nHint: It seems like a file is missing. You can use tools to `list_files` in `{base_dir}` or `find_file` to locate it in parent directories (e.g. `/home/ym/DeepSlide/deepslide/tmp_uploads`), and then `copy_file` it to the correct location expected by the LaTeX code."

            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=self.usr_prompt.format("content", error_message, snippet) + prompt_suffix
            )

            # Increase timeout for file operations
            self.agent.step_timeout = 60 # wait up to 60s
            
            # Allow multiple steps for tool usage
            response = None
            for _ in range(5): # Allow up to 5 steps (thought/action loop)
                response = self.agent.step(user_msg)
                if response.terminated or "Fix:" in str(response.msg.content) or "<content>" in str(response.msg.content):
                    break
                # If tool called, we need to continue? 
                # Camel ChatAgent usually handles tool execution internally if configured.
                # But here we need to ensure it returns the final answer with <content> tag.
            
            if not response: return False
            
            correct_content = response.msg.content
            # get content from <content></content> wrapper
            match = re.search(r'<content>(.*?)</content>', correct_content, re.DOTALL)
            if match:
                correct_content = match.group(1).strip()
                # 4. 替换错误对象
                result = replace_content(base_dir, obj_idx, correct_content)
                if result:
                    print(
                        Fore.YELLOW + f"🔧 Fix: {obj_idx}-th object of content\n" + Fore.RESET,
                        f"{correct_content}"
                    )
                    return True
            else:
                # Maybe the agent fixed it by copying files (side effect) and didn't change content?
                # If the error was "File not found", and agent copied the file, we might not need to change content.
                # But the current architecture expects a content change to signal success?
                # Actually, if compile succeeds next time, that's what matters.
                # But _fix_content expects to return True if it did something useful.
                if "Successfully copied" in str(response.info) or "Successfully copied" in str(correct_content):
                     print(Fore.YELLOW + f"🔧 Fix: File copied/restored via tool.\n" + Fore.RESET)
                     return True
                
                return False

        except Exception as e:
            logger.error(f"Error fixing content: {e}")
        return False

    def _fix_base(self, base_dir: str, error_message: str) -> bool:
        try:
            curr_base = open(os.path.join(base_dir, 'base.tex'), 'r', encoding='utf-8').read()
            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=self.usr_prompt.format("base", error_message, curr_base)
            )

            response = self.agent.step(user_msg)
            correct_base = response.msg.content

            # get base from <base></base> wrapper
            match = re.search(r'<base>(.*?)</base>', correct_base, re.DOTALL)
            if match:
                correct_base = match.group(1).strip()
            else:
                return False

            # 替换错误base
            result = update_base(base_dir, correct_base)
            if result:
                print(
                    Fore.YELLOW + f"🔧 Fix: base\n" + Fore.RESET,
                    f"{correct_base}"
                )
                return True
        except Exception as e:
            logger.error(f"Error fixing base: {e}")
        return False

    def _pre_check_images(self, base_dir: str, source_dir: str = None):
        """
        Pre-check all image paths in content.tex. 
        If an image path does not exist in base_dir, try to find it in the project and copy/fix it.
        Args:
            base_dir: The compilation output directory.
            source_dir: Optional source directory (the original upload/extract folder) to search for missing assets.
        """
        print(Fore.CYAN + "🔍 Pre-checking image paths..." + Fore.RESET)
        try:
            content_path = os.path.join(base_dir, "content.tex")
            if not os.path.exists(content_path): return
            
            with open(content_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Regex to find \includegraphics{path}
            # Matches \includegraphics[...]{path} or \includegraphics{path}
            # Path can be anything inside {}
            img_pattern = re.compile(r'\\includegraphics(?:\[.*?\])?\{(?P<path>.*?)\}')
            
            matches = list(img_pattern.finditer(content))
            if not matches: return

            new_content = content
            replacements = {} # old_path -> new_path
            
            # Project root for searching
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
            # Fallback search dirs: ONLY current base_dir and its parent (tmp_base)
            # Do NOT scan all tmp_uploads to avoid cross-session conflicts and privacy issues
            
            search_dirs = [
                os.path.join(base_dir),
                os.path.join(base_dir, "picture"),
            ]
            
            # Add specific source directory if provided
            if source_dir and os.path.exists(source_dir):
                search_dirs.append(source_dir)
                # Also check subdirs of source_dir in case it has 'figures' or 'img'
                for item in os.listdir(source_dir):
                    d = os.path.join(source_dir, item)
                    if os.path.isdir(d):
                        search_dirs.append(d)
            
            # Remove the dangerous global scan of tmp_uploads
            
            for m in matches:
                raw_path = m.group("path")
                if raw_path in replacements: continue # Already processed
                
                # Check if exists
                full_path = os.path.join(base_dir, raw_path)
                if os.path.exists(full_path): continue # OK
                
                print(Fore.YELLOW + f"⚠️ Image not found: {raw_path}. Searching in project..." + Fore.RESET)
                
                # Search strategy: Local Recursive Only
                found_path = None
                filename = os.path.basename(raw_path)
                
                for d in search_dirs:
                    if not os.path.exists(d): continue
                    # 1. Exact match in dir
                    p = os.path.join(d, filename)
                    if os.path.exists(p):
                        found_path = p
                        break
                    # 2. Recursive search within allowed dirs (safe)
                    for root, _, files in os.walk(d):
                        if filename in files:
                            found_path = os.path.join(root, filename)
                            break
                    if found_path: break
                
                if found_path:
                    # Copy to local picture folder
                    dest_dir = os.path.join(base_dir, "picture")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, filename)
                    
                    if found_path != dest_path:
                        import shutil
                        shutil.copy2(found_path, dest_path)
                    
                    # Update LaTeX path
                    new_rel_path = f"picture/{filename}"
                    replacements[raw_path] = new_rel_path
                    print(Fore.GREEN + f"✅ Restored {raw_path} -> {new_rel_path}" + Fore.RESET)
                else:
                    print(Fore.RED + f"❌ Could not find image: {filename}" + Fore.RESET)
            
            # Apply replacements
            for old, new in replacements.items():
                new_content = new_content.replace(f"{{{old}}}", f"{{{new}}}")
            
            if new_content != content:
                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(Fore.GREEN + "📝 Updated content.tex with fixed image paths." + Fore.RESET)
                
        except Exception as e:
            print(Fore.RED + f"Pre-check images error: {e}" + Fore.RESET)

    def run(self, base_dir: str, helper: dict[str, Any] = None, source_dir: str = None):
        """
        Compile the LaTeX document in the `base_dir`.

        Compiling the project folder requires the following file structure:

        1. base.tex  
        - Type: File
        - Purpose: Global template style definition file.  
        - Forbidden: Writing main text directly here; arbitrarily deleting or modifying existing layout commands.  
        - Recommendation: If you need to adjust headers, footers, theme colors, or font sizes, do so here to keep the entire slide deck consistent.

        2. content.tex
        - Type: File
        - Purpose: The sole entry point for slide content.  
        - Forbidden: Piling up large blocks of formulas or figure code.  
        - Recommendation: Split logic by sections; keep each section to no more than 10 lines of main text.

        3. ref.bib  
        - Type: File
        - Purpose: Central bibliography data source.  
        - Forbidden: Fabricating reference entries; using non-standard BibTeX entry types.  
        - Recommendation: Add each new reference to this file immediately.

        4. picture/  
        - Type: Directory
        - Purpose: Root directory for all image assets.  
        - Forbidden: Placing images in the root or any other custom folder; using Chinese or special symbols in image filenames.  
        - Recommendation: Adjust images appropriately to ensure slide aesthetics after compilation.

        5. title.tex
        - Type: File
        - Purpose: Title slide content.  
        - Forbidden: Modifying title, author, or institute commands.  
        - Recommendation: Customize title, subtitle, author, and institute information here.
        
        Args:
            base_dir (str): The directory of the LaTeX document.

            helper (dict[str, Any], optional): The helper dictionary for the compiler to detect the error location. Defaults to None.
            {
                "file": "content",
                "line": ?,
                "idx": ?
            }

            source_dir (str, optional): The source directory to search for missing assets. Defaults to None.
        
        Returns:
            dict: The result of the compilation.
        """
        # 0. Pre-check images before compilation
        self._pre_check_images(base_dir, source_dir=source_dir)

        for i in range(self.max_try):
            print(Fore.CYAN + f"\n[Try {i+1}] LaTeX compile..." + Fore.RESET)

            # 1. 直接调用工具进行编译
            result = compile_content(base_dir, helper=helper)

            # 2. 成功了就返回
            if result.get("success"):
                print(Fore.GREEN + "✅ Compile success" + Fore.RESET)
                return result

            # 3. 打印错误并尝试修复
            errors = result.get("errors", [])
            error_summary = "\n".join([f"Error: {e.get('message')} (file={e.get('file')}, line {e.get('line')})" for e in errors])
            print(Fore.RED + error_summary + Fore.RESET)

            if not getattr(self, 'agent', None):
                print(Fore.YELLOW + "⚠️  Skipping AI fix because Agent is not initialized (LLM API Key missing)." + Fore.RESET)
                break 

            # Fully autonomous Agent Fix
            # Ignore specific parsing from tex_compile.py and let Agent decide based on logs
            print(Fore.BLUE + "🤖 Handing over to AI Agent for autonomous diagnosis and fix..." + Fore.RESET)
            # Pass the first error message as a hint, but the agent will scan the log
            hint_msg = errors[0].get('message') if errors else "Compilation failed"
            if self._fix_with_agent_analysis(base_dir, hint_msg):
                continue # Retry compilation loop if fix reported success

        # 完成所有尝试后，再次编译
        result = compile_content(base_dir, helper=helper)

        if result.get("success"):
            print(Fore.GREEN + "✅ Compile success" + Fore.RESET)
        
        return result
