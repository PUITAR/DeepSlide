import re

class Frame(str):

    logic_node_name: str = ""

    def __new__(cls, content: str):
        return super().__new__(cls, (content or ""))

    def is_valid(self) -> bool:
        text = str(self)
        if not text:
            print(f"Empty frame: {text}")
            return False
        if "\\begin{frame}" not in text or "\\end{frame}" not in text:
            print(f"Frame missing begin/end frame: {text}")
            return False
        if text.count("\\begin{frame}") != 1 or text.count("\\end{frame}") != 1:
            print(f"Frame has multiple begin/end frame: {text}")
            return False
        # basic environment pairing check: figure/itemize pairs if present
        for env in ["figure", "itemize", "columns", "column", "table", "block"]:
            if text.count(f"\\begin{{{env}}}") != text.count(f"\\end{{{env}}}"):
                print(f"Frame unbalanced {env} environment: {text}")
                return False
        # check unbalanced braces
        if text.count("{") != text.count("}"):
            print(f"Frame unbalanced braces: {text}")
            return False
            
        return True

    @staticmethod
    def from_figure(path: str, caption: str = None, width: float = 1.0) -> "Frame":
        w = str(width)
        parts = [
            "\\begin{frame}\n",
            "    \\begin{figure}\n",
            "        \\centering\n",
            f"        \\includegraphics[width={w}\\linewidth]{{{path}}}\n",
        ]
        if caption:
            parts.append(f"        \\caption{{{caption}}}\n")
        parts.extend([
            "    \\end{figure}\n",
            "\\end{frame}\n",
        ])
        return Frame("".join(parts))
