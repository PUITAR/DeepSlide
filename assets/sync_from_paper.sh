#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/DeepSlide-Arxiv"
DST_DIR="${ROOT_DIR}/assets"

mkdir -p "${DST_DIR}/paper" "${DST_DIR}/icons"

cp -f "${SRC_DIR}/pic/"*.jpg "${DST_DIR}/paper/" 2>/dev/null || true
cp -f "${SRC_DIR}/pic/"*.pdf "${DST_DIR}/paper/" 2>/dev/null || true
cp -f "${SRC_DIR}/sys_prompts.pdf" "${DST_DIR}/paper/" 2>/dev/null || true
cp -f "${SRC_DIR}/attn_logo/"*.png "${DST_DIR}/icons/" 2>/dev/null || true
cp -f "${SRC_DIR}/api_logo/"*.png "${DST_DIR}/icons/" 2>/dev/null || true

python3 - <<'PY' || true
from __future__ import annotations

from pathlib import Path

try:
    import fitz  # PyMuPDF
except Exception:
    print("[assets] PyMuPDF not found. Skip pdf->png conversion. Install pymupdf and re-run.")
    raise SystemExit(0)

repo_root = Path(__file__).resolve().parent.parent
paper_dir = repo_root / "assets" / "paper"

pdfs = sorted(paper_dir.glob("*.pdf"))
if not pdfs:
    print("[assets] No PDF found in assets/paper. Skip conversion.")
    raise SystemExit(0)

for pdf_path in pdfs:
    try:
        doc = fitz.open(str(pdf_path))
        if doc.page_count <= 0:
            continue
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=200, alpha=False)
        out_path = pdf_path.with_suffix(".png")
        pix.save(str(out_path))
        doc.close()
    except Exception as e:
        print(f"[assets] Failed to convert {pdf_path.name}: {e}")
        continue

print(f"[assets] Converted {len(pdfs)} pdf(s) to png (first page, 200 dpi).")
PY

rm -f "${DST_DIR}/paper/"*.pdf 2>/dev/null || true

echo "Synced paper assets:"
echo "- ${DST_DIR}/paper (jpg/png)"
echo "- ${DST_DIR}/icons (png)"
