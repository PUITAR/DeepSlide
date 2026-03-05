import base64
import csv
import math
import os
import re
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP
from filelock import FileLock
from mcp.types import ImageContent
from PIL import Image
from pptagent.model_utils import _get_lid_model
from pptagent.utils import ppt_to_images
from pptagent_pptx import Presentation
from pydantic import BaseModel

from deeppresenter.utils.config import DeepPresenterConfig
from deeppresenter.utils.log import error, info, set_logger, warning
from deeppresenter.utils.webview import convert_html_to_pptx

mcp = FastMCP(name="Task")

LID_MODEL = _get_lid_model()
CONFIG = DeepPresenterConfig.load_from_file(os.getenv("CONFIG_FILE"))


def _rewrite_image_link(match: re.Match[str], md_dir: Path) -> str:
    alt_text = match.group(1)
    target = match.group(2).strip()
    if not target:
        return match.group(0)
    parts = re.match(r"([^\s]+)(.*)", target)
    if not parts:
        return match.group(0)
    local_path = parts.group(1).strip("\"'")
    rest = parts.group(2)
    p = Path(local_path)
    if not p.is_absolute() and (md_dir / local_path).exists():
        p = md_dir / local_path
    if not p.exists():
        return match.group(0)

    updated_alt = alt_text
    try:
        with Image.open(p) as img:
            width, height = img.size
        if width > 0 and height > 0 and not re.search(r"\b\d+:\d+\b", updated_alt):
            factor = math.gcd(width, height)
            ratio = f"{width // factor}:{height // factor}"
            updated_alt = f"{updated_alt}, {ratio}" if updated_alt else ratio
    except OSError:
        pass

    # ? since slides were placed in an independent folder, we convert image path to absolute path to avoid broken links
    new_path = p.resolve().as_posix()
    return f"![{updated_alt}]({new_path}{rest})"


class Todo(BaseModel):
    id: str
    content: str
    status: Literal["pending", "in_progress", "completed", "skipped"]


LOCAL_TODO_CSV_PATH = Path("todo.csv")
LOCAL_TODO_LOCK_PATH = Path(".todo.csv.lock")


def _load_todos() -> list[Todo]:
    """Load todos from CSV file."""
    if not LOCAL_TODO_CSV_PATH.exists():
        return []

    lock = FileLock(LOCAL_TODO_LOCK_PATH)
    with lock:
        with open(LOCAL_TODO_CSV_PATH, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [Todo(**row) for row in reader]


def _save_todos(todos: list[Todo]) -> None:
    """Save todos to CSV file."""
    lock = FileLock(LOCAL_TODO_LOCK_PATH)
    with lock:
        with open(LOCAL_TODO_CSV_PATH, "w", encoding="utf-8", newline="") as f:
            if todos:
                fieldnames = ["id", "content", "status"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for todo in todos:
                    writer.writerow(todo.model_dump())


@mcp.tool()
def todo_create(todo_content: str) -> str:
    """
    Create a new todo item and add it to the todo list.

    Args:
        todo_content (str): The content/description of the todo item

    Returns:
        str: Confirmation message with the created todo's ID
    """
    todos = _load_todos()
    new_id = str(len(todos))
    new_todo = Todo(id=new_id, content=todo_content, status="pending")
    todos.append(new_todo)
    _save_todos(todos)
    return f"Todo {new_id} created"


@mcp.tool()
def todo_update(
    idx: int,
    todo_content: str = None,
    status: Literal["completed", "in_progress", "skipped"] = None,
) -> str:
    """
    Update an existing todo item's content or status.

    Args:
        idx (int): The index of the todo item to update
        todo_content (str, optional): New content for the todo item
        status (Literal["completed", "in_progress", "skipped"], optional): New status for the todo item

    Returns:
        str: Confirmation message with the updated todo's ID
    """
    todos = _load_todos()
    if idx < 0 or idx >= len(todos):
        return f"Invalid todo index: {idx}"

    if todo_content is not None:
        todos[idx].content = todo_content
    if status is not None:
        todos[idx].status = status
    _save_todos(todos)
    return "Todo updated successfully"


@mcp.tool()
def todo_list() -> str | list[Todo]:
    """
    Get the current todo list or check if all todos are completed.

    Returns:
        str | list[Todo]: Either a completion message if all todos are done/skipped,
                         or the current list of todo items
    """
    todos = _load_todos()
    if not todos or all(todo.status in ["completed", "skipped"] for todo in todos):
        LOCAL_TODO_CSV_PATH.unlink(missing_ok=True)
        return "All todos completed"
    else:
        return todos


# @mcp.tool()
def ask_user(question: str) -> str:
    """
    Ask the user a question when encounters an unclear requirement.
    """
    print(f"User input required: {question}")
    return input("Your answer: ")


@mcp.tool()
def thinking(thought: str):
    """This tool is for explicitly reasoning about the current task state and next actions."""
    info(f"Thought: {thought}")
    return thought


@mcp.tool(exclude_args=["agent_name"])
def finalize(outcome: str, agent_name: str = "") -> str:
    """
    When all tasks are finished, call this function to finalize the loop.
    Args:
        outcome (str): The path to the final outcome file or directory.
    """
    # here we conduct some final checks on agent's outcome
    path = Path(outcome)
    if not path.exists():
        return f"Outcome {outcome} does not exist"
    if agent_name == "Research":
        md_dir = path.parent
        if not (path.is_file() and path.suffix == ".md"):
            return "Outcome file should be a markdown file"
        with open(path, encoding="utf-8") as f:
            content = f.read()

        try:
            content = re.sub(
                r"!\[(.*?)\]\((.*?)\)",
                lambda match: _rewrite_image_link(match, md_dir),
                content,
            )
            shutil.copyfile(path, md_dir / ("." + path.name))
            path.write_text(content, encoding="utf-8")
        except Exception as e:
            error(f"Failed to rewrite image links: {e}")

    elif agent_name == "PPTAgent":
        if not (path.is_file() and path.suffix == ".pptx"):
            return "Outcome file should be a pptx file"
        prs = Presentation(str(path))
        if len(prs.slides) <= 0:
            return "PPTX file should contain at least one slide"
    elif agent_name == "Design":
        html_files = list(path.glob("*.html"))
        if len(html_files) <= 0:
            return "Outcome path should be a directory containing HTML files"
        if not all(f.stem.startswith("slide_") for f in html_files):
            return "All HTML files should start with 'slide_'"
    else:
        warning(f"Unverifiable agent: {agent_name}")

    if LOCAL_TODO_CSV_PATH.exists():
        LOCAL_TODO_CSV_PATH.unlink()
    if LOCAL_TODO_LOCK_PATH.exists():
        LOCAL_TODO_LOCK_PATH.unlink()

    info(f"Agent {agent_name} finalized the outcome: {outcome}")
    return outcome


@mcp.tool()
async def inspect_slide(
    html_file: str,
    aspect_ratio: Literal["16:9", "4:3", "A1", "A2", "A3", "A4"] = "16:9",
) -> ImageContent | str:
    """
    Read the HTML file as an image.

    Returns:
        ImageContent: The slide as an image content
        str: Error message if inspection fails
    """
    html_path = Path(html_file).absolute()
    if not (html_path.exists() and html_path.suffix == ".html"):
        return f"HTML path {html_path} does not exist or is not an HTML file"
    try:
        pptx_path = await convert_html_to_pptx(html_path, aspect_ratio=aspect_ratio)
    except Exception as e:
        return e

    if CONFIG.design_agent.is_multimodal and CONFIG.heavy_reflect:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            await ppt_to_images(str(pptx_path), str(output_dir))
            image_path = output_dir / "slide_0001.jpg"
            if not image_path.exists():
                error(f"Image not found: {image_path}")
            image_data = image_path.read_bytes()
        base64_data = (
            f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}"
        )
        return ImageContent(
            type="image",
            data=base64_data,
            mimeType="image/jpeg",
        )
    else:
        return "This slide is valid."


@mcp.tool()
def inspect_manuscript(md_file: str) -> dict:
    """
    Inspect the markdown manuscript for general statistics and image asset validation.
    Args:
        md_file (str): The path to the markdown file
    """
    md_path = Path(md_file)
    if not md_path.exists():
        return {"error": f"file does not exist: {md_file}"}
    if not md_file.lower().endswith(".md"):
        return {"error": f"file is not a markdown file: {md_file}"}

    with open(md_file, encoding="utf-8") as f:
        markdown = f.read()

    pages = [p for p in markdown.split("\n---\n") if p.strip()]
    result = defaultdict(list)
    result["num_pages"] = len(pages)
    label = LID_MODEL.predict(markdown[:1000].replace("\n", " "))
    result["language"] = label[0][0].replace("__label__", "")

    seen_images = set()
    for match in re.finditer(r"!\[(.*?)\]\((.*?)\)", markdown):
        label, path = match.group(1), match.group(2)
        path = path.split()[0].strip("\"'")

        if path in seen_images:
            continue
        seen_images.add(path)

        if re.match(r"https?://", path):
            result["warnings"].append(
                f"External link detected: {match.group(0)}, consider downloading to local storage."
            )
            continue

        if not (md_path.parent / path).exists() and not Path(path).exists():
            result["warnings"].append(f"Image file does not exist: {path}")

        if not label.strip():
            result["warnings"].append(f"Image {path} is missing alt text.")

        count = markdown.count(path)
        if count > 1:
            result["warnings"].append(
                f"Image {path} used {count} times in the whole presentation manuscript."
            )

    if len(result["warnings"]) == 0:
        result["success"].append(
            "Image asset validation passed: all referenced images exist."
        )

    return result


if __name__ == "__main__":
    assert len(sys.argv) == 2, "Usage: python task.py <workspace>"
    work_dir = Path(sys.argv[1])
    assert work_dir.exists(), f"Workspace {work_dir} does not exist."
    os.chdir(work_dir)
    set_logger(f"task-{work_dir.stem}", work_dir / ".history" / "task.log")

    mcp.run(show_banner=False)
