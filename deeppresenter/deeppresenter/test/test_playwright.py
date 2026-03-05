import tempfile
from pathlib import Path

import pytest

from deeppresenter.utils.webview import PlaywrightConverter

HTML = """
<html>
  <head><title>Test Page</title></head>
  <body><h1>Hello, World!</h1><p>This is a test page.</p></body>
</html>
"""


@pytest.mark.asyncio
async def test_pdf_export():
    async with PlaywrightConverter() as converter:
        # Create a temporary HTML file
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp_html:
            tmp_html.write(HTML.encode("utf-8"))
            tmp_html_path = tmp_html.name

        # Define output PDF path
        output_pdf_path = Path(tempfile.mkstemp(suffix=".pdf")[1])

        # Convert HTML to PDF
        await converter.convert_to_pdf(
            html_files=[tmp_html_path],
            output_pdf=output_pdf_path,
            aspect_ratio="normal",
        )

        # Check if PDF file is created
        assert output_pdf_path.exists()
        assert output_pdf_path.stat().st_size > 0
