import os
import subprocess
import logging
import re
import random
import functools
from typing import List, Optional, Dict, Any
from colorama import Fore, Style
from tex_compile import compile_content

logger = logging.getLogger(__name__)

def log_tool_usage(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Extract self (instance) to get context if needed, but simple print is fine
        arg_str = ", ".join([repr(a) for a in args[1:]] + [f"{k}={v!r}" for k, v in kwargs.items()])
        print(Fore.MAGENTA + f"🛠️  [Tool Call] {func.__name__}({arg_str})" + Style.RESET_ALL)
        try:
            result = func(*args, **kwargs)
            # Truncate long results for display
            res_str = str(result)
            if len(res_str) > 200:
                res_str = res_str[:200] + "..."
            print(Fore.MAGENTA + f"   -> Result: {res_str}" + Style.RESET_ALL)
            return result
        except Exception as e:
            print(Fore.RED + f"   -> Error: {e}" + Style.RESET_ALL)
            raise e
    return wrapper

class CompilerTools:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    @log_tool_usage
    def read_file(self, filename: str, start_line: int = 1, end_line: int = -1) -> str:
        """
        Read the content of a file.
        filename: Relative path to the file (e.g., 'content.tex', 'base.tex').
        start_line: 1-based start line (inclusive).
        end_line: 1-based end line (inclusive). -1 for end of file.
        """
        try:
            path = os.path.join(self.base_dir, filename)
            if not os.path.exists(path):
                return f"Error: File {filename} does not exist."
            
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            
            if start_line < 1: start_line = 1
            if end_line == -1 or end_line > len(lines):
                end_line = len(lines)
            
            # Adjust to 0-based
            selected_lines = lines[start_line-1 : end_line]
            content = "".join(selected_lines)
            return f"--- {filename} (Lines {start_line}-{end_line}) ---\n{content}\n--- End of File ---"
        except Exception as e:
            return f"Error reading file: {e}"

    @log_tool_usage
    def write_file(self, filename: str, content: str) -> str:
        """
        Overwrite the ENTIRE content of a file. 
        CRITICAL: You must read the file first to ensure you don't lose existing code.
        filename: Relative path.
        content: The new full content.
        """
        try:
            path = os.path.join(self.base_dir, filename)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"Successfully wrote to {filename}."
        except Exception as e:
            return f"Error writing file: {e}"

    @log_tool_usage
    def list_files(self) -> str:
        """List all files in the directory."""
        try:
            files = []
            for f in os.listdir(self.base_dir):
                if os.path.isfile(os.path.join(self.base_dir, f)):
                    files.append(f)
            return "\n".join(files)
        except Exception as e:
            return f"Error listing files: {e}"

    @log_tool_usage
    def grep_files(self, pattern: str) -> str:
        """
        Search for a regex pattern in all files in the directory.
        pattern: The regex pattern to search for.
        """
        try:
            # Python implementation of grep to be cross-platform safe
            results = []
            files = [f for f in os.listdir(self.base_dir) if f.endswith(".tex") or f.endswith(".bib") or f.endswith(".sty")]
            
            for fname in files:
                path = os.path.join(self.base_dir, fname)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    for i, line in enumerate(lines):
                        if re.search(pattern, line):
                            results.append(f"{fname}:{i+1}: {line.strip()[:100]}") # Truncate long lines
                except Exception:
                    continue
            
            if not results:
                return "No matches found."
            return "\n".join(results[:50]) # Limit output
        except Exception as e:
            return f"Error executing grep: {e}"

    @log_tool_usage
    def search_replace(self, filename: str, old_str: str, new_str: str) -> str:
        """
        Replace occurrences of a string in a file.
        filename: Relative path.
        old_str: String to find (literal, not regex).
        new_str: String to replace with.
        """
        try:
            path = os.path.join(self.base_dir, filename)
            if not os.path.exists(path):
                return f"Error: File {filename} does not exist."
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if old_str not in content:
                return f"String '{old_str}' not found in {filename}."
            
            new_content = content.replace(old_str, new_str)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            return f"Successfully replaced occurrences in {filename}."
        except Exception as e:
            return f"Error in search_replace: {e}"

    @log_tool_usage
    def run_python_script(self, script_content: str) -> str:
        """
        Run a temporary Python script to perform complex file manipulations.
        The script runs in the compilation directory.
        script_content: Full python code.
        """
        try:
            script_name = "temp_agent_script.py"
            script_path = os.path.join(self.base_dir, script_name)
            
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # Run it
            result = subprocess.run(
                ["python", script_name],
                cwd=self.base_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10 # Short timeout
            )
            
            # Cleanup
            if os.path.exists(script_path):
                os.remove(script_path)
                
            output = f"Stdout:\n{result.stdout}\nStderr:\n{result.stderr}"
            if result.returncode == 0:
                return f"Script executed successfully.\n{output}"
            else:
                return f"Script failed with code {result.returncode}.\n{output}"
        except Exception as e:
            return f"Error running python script: {e}"

    @log_tool_usage
    def create_image_placeholder(self, filename: str) -> str:
        """
        Create a dummy placeholder image (PNG) if it doesn't exist.
        """
        try:
            path = os.path.join(self.base_dir, filename)
            if os.path.exists(path):
                return f"Image {filename} already exists."
            
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            
            try:
                from PIL import Image
                img = Image.new('RGB', (100, 100), color = 'red')
                img.save(path)
                return f"Created placeholder image at {filename} using PIL."
            except ImportError:
                import base64
                png_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
                with open(path, "wb") as f:
                    f.write(base64.b64decode(png_base64))
                return f"Created placeholder image at {filename} (1x1 pixel)."
                
        except Exception as e:
            return f"Error creating placeholder: {e}"

    @log_tool_usage
    def create_plot_image(self, filename: str, title: str = "Data Plot", data_type: str = "bar") -> str:
        """
        Create a synthetic plot image using Matplotlib.
        filename: Output filename (e.g., 'plot.png').
        title: Title of the chart.
        data_type: 'bar', 'line', 'scatter', or 'pie'.
        """
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
            
            return f"Created {data_type} plot at {filename}."
        except Exception as e:
            # Fallback to placeholder if matplotlib fails
            return self.create_image_placeholder(filename)

    @log_tool_usage
    def check_balance(self, filename: str) -> str:
        """
        Check for unbalanced braces {} or environments \begin \end in a file.
        Returns a report of the first mismatch found.
        """
        try:
            path = os.path.join(self.base_dir, filename)
            if not os.path.exists(path): return "File not found."
            
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            # Stack for braces and envs
            stack = []
            
            for i, line in enumerate(lines):
                # Remove comments
                line = re.sub(r'([^\\])%.*', r'\1', line)
                if line.strip().startswith('%'): continue
                
                # Check for braces (ignoring escaped ones)
                # This is a naive check; comprehensive LaTeX parsing is hard in regex.
                # Let's focus on Environments as they are the most common fatal error
                
                # Find \begin{...} and \end{...}
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
            
            # Check for braces count mismatch (global)
            content = "".join(lines)
            # Remove escaped braces
            clean = content.replace(r'\{', '').replace(r'\}', '')
            open_count = clean.count('{')
            close_count = clean.count('}')
            
            if open_count != close_count:
                return f"Brace Mismatch: Found {open_count} '{{' and {close_count} '}}'. Check for unclosed groups."
                
            return "No obvious balance errors found."
            
        except Exception as e:
            return f"Error checking balance: {e}"

    @log_tool_usage
    def compile_pdf(self) -> str:
        """
        Attempt to compile the LaTeX project to PDF.
        Returns the compilation status and logs.
        """
        try:
            # We use the existing compile_content function from tex_compile
            # Note: tex_compile usually handles the logic, but here we invoke it directly.
            # However, tex_compile expects to run in the current process or needs specific setup.
            # Let's assume we can call it.
            
            # Since compile_content is imported at module level, we can use it.
            # But we need to make sure we are in the right directory or pass the path.
            # compile_content(base_dir) is how it's called in Compiler.run
            
            result = compile_content(self.base_dir)
            
            if result.get("success"):
                return "SUCCESS: PDF compiled successfully."
            else:
                errors = result.get("errors", [])
                error_msgs = "\n".join([f"{e.get('file')}:{e.get('line')} - {e.get('message')}" for e in errors])
                return f"FAILURE: Compilation failed.\nErrors:\n{error_msgs}"
                
        except Exception as e:
            return f"Error during compilation: {e}"
