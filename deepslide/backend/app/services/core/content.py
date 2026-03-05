from .frame import Frame
from .section import Section
from typing import List, Tuple

class Content(list):
    def is_valid(self) -> bool:
        for item in self:
            if hasattr(item, "is_valid") and not item.is_valid():
                print(f"Invalid item: {item}")
                return False
        return True

    def to_file(self, file_path_or_handle):
        if not self.is_valid():
            print("Warning: Content is not valid.")

        mapping: List[Tuple[int, int, str]] = []
        lines_so_far = 1
        
        def write_content(f):
            nonlocal lines_so_far
            for idx, item in enumerate(self):
                typ = "Frame" if isinstance(item, Frame) else ("Section" if isinstance(item, Section) else type(item).__name__)
                f.write(f"%% ITEM {idx} TYPE {typ}\n")
                lines_so_far += 1
                text = str(item)
                f.write(text)
                cnt = text.count("\n")
                start = lines_so_far
                end = lines_so_far + cnt - 1
                mapping.append((start, end, typ))
                lines_so_far = end + 1

        if isinstance(file_path_or_handle, str):
            with open(file_path_or_handle, "w", encoding="utf-8") as f:
                write_content(f)
        else:
            write_content(file_path_or_handle)
            
        return mapping

    def from_file(self, file_path: str) -> None:
        self.clear()
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                inside_frame = False
                frame_lines: list[str] = []
                for line in f:
                    if inside_frame:
                        frame_lines.append(line)
                        if "\\end{frame}" in line:
                            self.append(Frame("".join(frame_lines)))
                            inside_frame = False
                            frame_lines = []
                        continue
                    if "\\begin{frame}" in line:
                        inside_frame = True
                        frame_lines = [line]
                        continue
                    if "\\section" in line or "\\subsection" in line or "\\subsubsection" in line:
                        self.append(Section(line))
        except FileNotFoundError:
            pass

    def sections(self) -> List[Section]:
        return [item for item in self if isinstance(item, Section)]

    def frames(self) -> List[Frame]:
        return [item for item in self if isinstance(item, Frame)]
