import re

class Section(str):
    def __new__(cls, content: str):
        return super().__new__(cls, (content or ""))

    def is_valid(self) -> bool:
        s = str(self)
        if not s:
            print(f"Empty section: {s}")
            return False
        # must be a LaTeX section-like command
        if ("\\section" not in s) and ("\\subsection" not in s) and ("\\subsubsection" not in s):
            print(len(s))
            print(f"Invalid section format: {s}")
            return False
        # check braces pairing
        if s.count("{") != s.count("}"):
            print(f"Section unbalanced braces: {s}")
            return False

        return True
