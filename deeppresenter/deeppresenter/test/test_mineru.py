from pathlib import Path

import httpx
import pytest

PDF_LINK = "https://arxiv.org/pdf/1706.03762"


@pytest.mark.asyncio
async def test_mineru_pdf_parsing(agent_env, workspace: Path, tool_call_helper) -> None:
    pdf_path = workspace / "attention_is_all_you_need.pdf"
    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
        resp = await client.get(PDF_LINK)
        assert resp.status_code == 200
        pdf_path.write_bytes(resp.content)

    output_dir = workspace / "mineru_output"
    tool_call = tool_call_helper(
        "convert_to_markdown",
        {"file_path": str(pdf_path), "output_folder": str(output_dir)},
    )
    result = await agent_env.tool_execute(tool_call)
    assert not result.is_error, f"MinerU conversion failed: {result.text}"

    md_file = output_dir.glob("*.md").__next__()
    assert "Attention Is All You Need" in md_file.read_text()
