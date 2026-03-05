import os
import subprocess
import logging
import re
import random
import functools
from typing import List, Optional, Dict, Any
from .tex_compile import compile_content

logger = logging.getLogger(__name__)


def _safe_preview(value: Any, limit: int = 200) -> str:
    try:
        s = str(value)
    except Exception:
        return "<unprintable>"
    if len(s) > limit:
        return s[:limit] + "..."
    return s


def _safe_args(args: Dict[str, Any], limit: int = 400) -> str:
    safe = {}
    for k, v in (args or {}).items():
        if k in {"content", "script_content"}:
            try:
                safe[k] = f"<len={len(str(v))}>"
            except Exception:
                safe[k] = "<unprintable>"
        else:
            safe[k] = v
    return _safe_preview(safe, limit=limit)

# Simple logging wrapper instead of colorama for backend logs
def log_tool_usage(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        arg_str = ", ".join([repr(a) for a in args[1:]] + [f"{k}={v!r}" for k, v in kwargs.items()])
        logger.info(f"[tool] call {func.__name__} args={_safe_preview(arg_str, limit=400)}")
        try:
            result = func(*args, **kwargs)
            logger.info(f"[tool] result {func.__name__} output={_safe_preview(result)}")
            return result
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            raise e
    return wrapper

class CompilerTools:
    def __init__(self, base_dir: str):
        backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(backend_root, base_dir)
        self.base_dir = os.path.abspath(base_dir)

    def read_file(self, filename: str, start_line: int = 1, end_line: int = -1) -> str:
        """
        Read the content of a file from the project directory.
        
        Args:
            filename (str): The name of the file to read (relative to base_dir).
            start_line (int, optional): The starting line number (1-based). Defaults to 1.
            end_line (int, optional): The ending line number (1-based). Defaults to -1 (end of file).
            
        Returns:
            str: The content of the file or an error message.
        """
        logger.info(f"[tool] call read_file args={_safe_args({'filename': filename, 'start_line': start_line, 'end_line': end_line})}")
        try:
            path = os.path.join(self.base_dir, filename)
            if not os.path.exists(path):
                return f"Error: File {filename} does not exist."
            
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            if start_line < 1: start_line = 1
            if end_line == -1 or end_line > len(lines):
                end_line = len(lines)
            
            selected_lines = lines[start_line-1 : end_line]
            content = "".join(selected_lines)
            res = f"--- {filename} (Lines {start_line}-{end_line}) ---\n{content}\n--- End of File ---"
            logger.info(f"[tool] result read_file output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error reading file: {e}"

    def write_file(self, filename: str, content: str) -> str:
        """
        Write content to a file in the project directory. Overwrites the file if it exists.
        
        Args:
            filename (str): The name of the file to write.
            content (str): The content to write to the file.
            
        Returns:
            str: A success message or an error message.
        """
        logger.info(f"[tool] call write_file args={_safe_args({'filename': filename, 'content': content})}")
        try:
            path = os.path.join(self.base_dir, filename)
            os.makedirs(os.path.dirname(path) or self.base_dir, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            res = f"Successfully wrote to {filename}."
            logger.info(f"[tool] result write_file output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error writing file: {e}"

    def list_files(self) -> str:
        """
        List all files in the project directory.
        
        Returns:
            str: A list of filenames separated by newlines.
        """
        logger.info(f"[tool] call list_files args={{}}")
        try:
            if not os.path.isdir(self.base_dir):
                return f"Error: Base directory {self.base_dir} does not exist."
            files = []
            for f in os.listdir(self.base_dir):
                if os.path.isfile(os.path.join(self.base_dir, f)):
                    files.append(f)
            res = "\n".join(files)
            logger.info(f"[tool] result list_files output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error listing files: {e}"

    def grep_files(self, pattern: str) -> str:
        """
        Search for a regex pattern in all .tex, .bib, and .sty files in the project directory.
        
        Args:
            pattern (str): The regular expression pattern to search for.
            
        Returns:
            str: A list of matches with file names and line numbers, or "No matches found."
        """
        logger.info(f"[tool] call grep_files args={_safe_args({'pattern': pattern})}")
        try:
            if not os.path.isdir(self.base_dir):
                return f"Error: Base directory {self.base_dir} does not exist."
            results = []
            files = [f for f in os.listdir(self.base_dir) if f.endswith(".tex") or f.endswith(".bib") or f.endswith(".sty")]
            
            for fname in files:
                path = os.path.join(self.base_dir, fname)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    for i, line in enumerate(lines):
                        if re.search(pattern, line):
                            results.append(f"{fname}:{i+1}: {line.strip()[:100]}")
                except Exception:
                    continue
            
            if not results:
                res = "No matches found."
            else:
                res = "\n".join(results[:50])
            logger.info(f"[tool] result grep_files output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error executing grep: {e}"

    def search_replace(self, filename: str, old_str: str, new_str: str) -> str:
        """
        Replace occurrences of a string in a file.
        
        Args:
            filename (str): The name of the file to modify.
            old_str (str): The string to search for.
            new_str (str): The string to replace it with.
            
        Returns:
            str: A success message or an error message.
        """
        logger.info(f"[tool] call search_replace args={_safe_args({'filename': filename, 'old': old_str, 'new': new_str})}")
        try:
            path = os.path.join(self.base_dir, filename)
            if not os.path.exists(path):
                return f"Error: File {filename} does not exist."
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_str not in content:
                res = f"String '{old_str}' not found in {filename}."
                logger.info(f"[tool] result search_replace output={_safe_preview(res)}")
                return res
            
            new_content = content.replace(old_str, new_str)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            res = f"Successfully replaced occurrences in {filename}."
            logger.info(f"[tool] result search_replace output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error in search_replace: {e}"

    def run_python_script(self, script_content: str) -> str:
        """
        Execute a temporary Python script in the project directory.
        
        Args:
            script_content (str): The Python code to execute.
            
        Returns:
            str: The stdout and stderr of the script execution.
        """
        logger.info(f"[tool] call run_python_script args={_safe_args({'script_content': script_content})}")
        try:
            if not os.path.exists(self.base_dir):
                parent_dir = os.path.dirname(self.base_dir)
                if self.base_dir.endswith(os.sep + "recipe") and os.path.isdir(parent_dir):
                    os.makedirs(self.base_dir, exist_ok=True)
                else:
                    return f"Error: Base directory {self.base_dir} does not exist."

            script_name = "temp_agent_script.py"
            script_path = os.path.join(self.base_dir, script_name)
            
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            result = subprocess.run(
                ["python", script_name],
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10
            )
            
            if os.path.exists(script_path):
                os.remove(script_path)
                
            output = f"Stdout:\n{result.stdout}\nStderr:\n{result.stderr}"
            if result.returncode == 0:
                res = f"Script executed successfully.\n{output}"
            else:
                res = f"Script failed with code {result.returncode}.\n{output}"
            logger.info(f"[tool] result run_python_script output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error running python script: {e}"

    def create_image_placeholder(self, filename: str) -> str:
        """
        Create a placeholder image file if it does not exist.
        
        Args:
            filename (str): The path to the image file to create.
            
        Returns:
            str: A message indicating whether the image was created or already exists.
        """
        logger.info(f"[tool] call create_image_placeholder args={_safe_args({'filename': filename})}")
        try:
            path = os.path.join(self.base_dir, filename)
            if os.path.exists(path):
                res = f"Image {filename} already exists."
                logger.info(f"[tool] result create_image_placeholder output={_safe_preview(res)}")
                return res
            
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            
            try:
                from PIL import Image
                img = Image.new('RGB', (256, 256), color = (226, 232, 240))
                img.save(path)
                res = f"Created placeholder image at {filename} using PIL."
            except ImportError:
                import base64
                png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8fP78HwAFhQJ4Q9c+GQAAAABJRU5ErkJggg=="
                with open(path, "wb") as f:
                    f.write(base64.b64decode(png_base64))
                res = f"Created placeholder image at {filename} (1x1 pixel)."
            
            logger.info(f"[tool] result create_image_placeholder output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error creating placeholder: {e}"

    def create_plot_image(self, filename: str, title: str = "Data Plot", data_type: str = "bar") -> str:
        """
        Create a plot image using matplotlib.
        
        Args:
            filename (str): The path to the image file to create.
            title (str, optional): The title of the plot. Defaults to "Data Plot".
            data_type (str, optional): The type of plot ('bar', 'line', 'scatter', 'pie'). Defaults to "bar".
            
        Returns:
            str: A message indicating the result.
        """
        logger.info(f"[tool] call create_plot_image args={_safe_args({'filename': filename, 'title': title, 'data_type': data_type})}")
        try:
            path = os.path.join(self.base_dir, filename)
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            
            import matplotlib.pyplot as plt
            import numpy as np
            
            plt.figure(figsize=(6, 4))
            
            if data_type == 'bar':
                x = ['A', 'B', 'C', 'D']
                y = [random.randint(10, 100) for _ in range(4)]
                plt.bar(x, y, color='skyblue')
            elif data_type == 'line':
                x = np.linspace(0, 10, 20)
                y = np.sin(x) + np.random.normal(0, 0.1, 20)
                plt.plot(x, y, '-o')
            elif data_type == 'scatter':
                x = np.random.rand(20)
                y = np.random.rand(20)
                plt.scatter(x, y)
            elif data_type == 'pie':
                x = [30, 20, 40, 10]
                plt.pie(x, labels=['A', 'B', 'C', 'D'])
            
            plt.title(title)
            plt.tight_layout()
            plt.savefig(path)
            plt.close()
            
            res = f"Created {data_type} plot at {filename}."
            logger.info(f"[tool] result create_plot_image output={_safe_preview(res)}")
            return res
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return self.create_image_placeholder(filename)

    def check_balance(self, filename: str) -> str:
        """
        Check for unclosed LaTeX environments and unbalanced braces in a file.
        
        Args:
            filename (str): The name of the file to check.
            
        Returns:
            str: A report of any balance issues found, or "No obvious balance errors found."
        """
        logger.info(f"[tool] call check_balance args={_safe_args({'filename': filename})}")
        try:
            path = os.path.join(self.base_dir, filename)
            if not os.path.exists(path): return "File not found."
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            stack = []
            
            for i, line in enumerate(lines):
                line = re.sub(r'([^\\])%.*', r'\1', line)
                if line.strip().startswith('%'): continue
                
                for match in re.finditer(r'\\(begin|end)\{([a-zA-Z0-9\*]+)\}', line):
                    cmd = match.group(1)
                    env = match.group(2)
                    
                    if cmd == 'begin':
                        stack.append((env, i + 1))
                    elif cmd == 'end':
                        if not stack:
                            return f"Mismatch: Found \\end{{{env}}} at line {i+1} but no matching \\begin."
                        last_env, last_line = stack.pop()
                        if last_env != env:
                            return f"Mismatch: Found \\end{{{env}}} at line {i+1} but expected \\end{{{last_env}}} (started at line {last_line})."
                            
            if stack:
                env, line = stack[-1]
                return f"Unclosed Environment: \\begin{{{env}}} at line {line} is never closed."
            
            content = "".join(lines)
            clean = content.replace(r'\{', '').replace(r'\}', '')
            open_count = clean.count('{')
            close_count = clean.count('}')
            
            if open_count != close_count:
                res = f"Brace Mismatch: Found {open_count} '{{' and {close_count} '}}'. Check for unclosed groups."
                logger.info(f"[tool] result check_balance output={_safe_preview(res)}")
                return res
                
            res = "No obvious balance errors found."
            logger.info(f"[tool] result check_balance output={_safe_preview(res)}")
            return res
            
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error checking balance: {e}"

    def compile_pdf(self) -> str:
        """
        Attempt to compile the project to PDF.
        
        Returns:
            str: A success message or a failure message with error details.
        """
        logger.info(f"[tool] call compile_pdf args={{}}")
        try:
            result = compile_content(self.base_dir)
            
            if result.get("success"):
                res = "SUCCESS: PDF compiled successfully."
                logger.info(f"[tool] result compile_pdf output={_safe_preview(res)}")
                return res
            else:
                errors = result.get("errors", [])
                error_msgs = "\n".join([f"{e.get('file')}:{e.get('line')} - {e.get('message')}" for e in errors])
                res = f"FAILURE: Compilation failed.\nErrors:\n{error_msgs}"
                logger.info(f"[tool] result compile_pdf output={_safe_preview(res)}")
                return res
                
        except Exception as e:
            logger.error(f"   -> Error: {e}")
            return f"Error during compilation: {e}"
