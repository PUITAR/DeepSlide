#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arXiv downloader (v3): strict per-field count + optional source download.

Fixes your issue:
- With high --workers, earlier versions submitted many in-flight downloads at once.
  Even after reaching per_field, already-submitted tasks would keep running, so you'd
  see >per_field PDFs in that field directory.
- v3 only submits at most (remaining_needed) tasks, so it will NOT overshoot.

Notes:
- By default it downloads PDFs only. Use --with-src to download source tarballs too.
- Source tarball is saved as source.tar.gz (arXiv "src" endpoint). Not every paper has
  an available source; failures are logged but the PDF may still succeed.
- Use --self-test and --proxy if you need to force Clash/proxy.
"""

import argparse
import json
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, install_opener, ProxyHandler, urlopen
from xml.etree import ElementTree as ET

USER_AGENT = "DeepSlide-ArxivDownloader/1.3"
BASE_API = "https://export.arxiv.org/api/query"


@dataclass
class FieldConfig:
    index: int
    name: str
    slug: str
    codes: List[str]


class Progress:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_len = 0

    def log(self, msg: str):
        if not self.enabled:
            return
        with self._lock:
            sys.stderr.write(msg + "\n")
            sys.stderr.flush()

    def bar(self, prefix: str, current: int, total: int):
        if not self.enabled:
            return
        total = max(total, 1)
        width = 24
        filled = int(width * min(max(current, 0), total) / total)
        bar = "[" + ("#" * filled) + ("-" * (width - filled)) + "]"
        msg = f"{prefix} {bar} {current}/{total}"
        with self._lock:
            sys.stderr.write("\r" + msg + (" " * max(0, self._last_len - len(msg))))
            sys.stderr.flush()
            self._last_len = len(msg)
            if current >= total:
                sys.stderr.write("\n")
                sys.stderr.flush()
                self._last_len = 0

    def flush_line(self):
        if not self.enabled:
            return
        with self._lock:
            if self._last_len > 0:
                sys.stderr.write("\n")
                sys.stderr.flush()
                self._last_len = 0


def slugify(name: str) -> str:
    normalized = name.strip().lower()
    out = []
    prev_dash = False
    for ch in normalized:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif ch in (" ", "-", "_", "/"):
            if not prev_dash:
                out.append("-")
                prev_dash = True
        else:
            continue
    s = "".join(out).strip("-")
    return s or "field"


def configure_proxy(proxy: str, progress: Progress):
    if not proxy:
        return
    handler = ProxyHandler({"http": proxy, "https": proxy})
    opener = build_opener(handler)
    install_opener(opener)
    progress.log(f"[proxy] using {proxy}")


def open_url(url: str, method: str = "GET", timeout: float = 12.0):
    headers = {"User-Agent": USER_AGENT, "Connection": "close"}
    req = Request(url, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        return urlopen(req, context=ctx, timeout=timeout)
    except Exception:
        insecure_ctx = ssl._create_unverified_context()
        return urlopen(req, context=insecure_ctx, timeout=timeout)


def parse_category_md(path: Path) -> List[FieldConfig]:
    lines = path.read_text(encoding="utf-8").splitlines()
    fields: List[FieldConfig] = []
    for line in lines:
        line = line.strip()
        if not line or not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        try:
            idx = int(parts[1])
        except ValueError:
            continue
        name = parts[2].strip().strip("*").strip()
        codes_cell = parts[3]

        codes: List[str] = []
        buf = ""
        in_bt = False
        for ch in codes_cell:
            if ch == "`":
                if in_bt and buf.strip():
                    codes.append(buf.strip())
                    buf = ""
                in_bt = not in_bt
            else:
                if in_bt:
                    buf += ch
        if not codes:
            raw = codes_cell.replace("`", "")
            for seg in raw.split(","):
                seg = seg.strip()
                if seg:
                    codes.append(seg)

        codes = [c.strip() for c in codes if c.strip()]
        if not codes:
            continue
        slug = f"{idx:02d}-{slugify(name)}"
        fields.append(FieldConfig(index=idx, name=name, slug=slug, codes=codes))
    return fields


def expand_codes(codes: List[str]) -> List[str]:
    group_map = {
        "astro-ph": [
            "astro-ph.CO",
            "astro-ph.EP",
            "astro-ph.GA",
            "astro-ph.HE",
            "astro-ph.IM",
            "astro-ph.SR",
        ],
        "cond-mat": [
            "cond-mat.dis-nn",
            "cond-mat.mes-hall",
            "cond-mat.mtrl-sci",
            "cond-mat.other",
            "cond-mat.quant-gas",
            "cond-mat.soft",
            "cond-mat.stat-mech",
            "cond-mat.str-el",
            "cond-mat.supr-con",
        ],
        "q-bio": [
            "q-bio.BM",
            "q-bio.CB",
            "q-bio.GN",
            "q-bio.MN",
            "q-bio.NC",
            "q-bio.OT",
            "q-bio.PE",
            "q-bio.QM",
            "q-bio.SC",
            "q-bio.TO",
        ],
        "q-fin": [
            "q-fin.CP",
            "q-fin.EC",
            "q-fin.GN",
            "q-fin.MF",
            "q-fin.PM",
            "q-fin.PR",
            "q-fin.RM",
            "q-fin.ST",
            "q-fin.TR",
        ],
    }

    expanded: List[str] = []
    for code in codes:
        if code in group_map:
            expanded.extend(group_map[code])
        else:
            expanded.append(code)
    return expanded


def build_search_query(codes: List[str]) -> str:
    if not codes:
        return ""
    expanded = expand_codes(codes)
    if len(expanded) == 1:
        return f"cat:{expanded[0]}"
    return " OR ".join([f"cat:{c}" for c in expanded])


def fetch_candidates(codes: List[str], max_results: int, timeout: float, api_min_interval: float, api_state: dict):
    expanded_codes = expand_codes(codes)
    q = build_search_query(expanded_codes)
    if not q:
        return []

    with api_state["lock"]:
        now = time.time()
        gap = now - api_state["last_ts"]
        if gap < api_min_interval:
            time.sleep(api_min_interval - gap)
        api_state["last_ts"] = time.time()

    params = {
        "search_query": q,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = f"{BASE_API}?{urlencode(params)}"
    with open_url(url, timeout=timeout) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = []
    seen = set()
    for entry in root.findall("atom:entry", ns):
        eid_node = entry.find("atom:id", ns)
        title_node = entry.find("atom:title", ns)
        if eid_node is None or title_node is None:
            continue
        eid = (eid_node.text or "").strip()
        title = " ".join((title_node.text or "").strip().split())
        if "/abs/" in eid:
            arxiv_id = eid.split("/abs/")[-1]
        else:
            arxiv_id = eid.rsplit("/", 1)[-1]
        if not arxiv_id or arxiv_id in seen:
            continue
        seen.add(arxiv_id)

        authors = []
        for a in entry.findall("atom:author", ns):
            nn = a.find("atom:name", ns)
            if nn is not None and nn.text:
                authors.append(nn.text.strip())

        cats = []
        for c in entry.findall("atom:category", ns):
            term = c.attrib.get("term")
            if term:
                cats.append(term)

        if expanded_codes and not any(cat in expanded_codes for cat in cats):
            continue

        entries.append({"id": arxiv_id, "title": title, "authors": authors, "categories": cats})
    return entries


def download_file(url: str, path: Path, timeout: float, retries: int, backoff: float) -> Tuple[bool, Optional[str]]:
    last_err = None
    for attempt in range(retries + 1):
        try:
            with open_url(url, method="GET", timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                if not (200 <= status < 300):
                    raise RuntimeError(f"http_status={status}")
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".part")
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                tmp.replace(path)
            return True, None
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as e:
            last_err = str(e) or repr(e)
            if attempt < retries:
                time.sleep((backoff ** attempt) * 0.5)
    return False, last_err


def ensure_existing(field_dir: Path, arxiv_id: str, with_src: bool):
    paper_dir = field_dir / arxiv_id
    pdf = paper_dir / "paper.pdf"
    src = (paper_dir / "source.tar.gz") if with_src else None
    if pdf.is_file() and (not with_src or (src is not None and src.is_file())):
        return True, paper_dir, pdf, src
    return False, paper_dir, pdf, src


def download_one(entry: dict, field: FieldConfig, dataset_root: Path, field_dir: Path,
                 timeout: float, retries: int, backoff: float, with_src: bool, progress: Progress) -> Tuple[bool, dict]:
    arxiv_id = entry["id"]
    existed, paper_dir, pdf_path, src_path = ensure_existing(field_dir, arxiv_id, with_src)

    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    src_url = f"https://arxiv.org/src/{arxiv_id}?mod=src&download=1" if with_src else None

    local_dir_rel = str(paper_dir.relative_to(dataset_root))

    if existed:
        meta = {
            "field_no": field.index,
            "field_name": field.name,
            "field_slug": field.slug,
            "primary_codes": list(field.codes),
            "arxiv_id": arxiv_id,
            "title": entry["title"],
            "authors": entry["authors"],
            "categories": entry.get("categories", []),
            "local_dir": local_dir_rel,
            "files": {"pdf": str(pdf_path.relative_to(dataset_root)),
                      "src": str(src_path.relative_to(dataset_root)) if (with_src and src_path is not None) else None},
            "urls": {"abs": abs_url, "pdf": pdf_url, "src": src_url},
            "downloaded": {"pdf": True, "src": (src_path is not None and src_path.is_file()) if with_src else False},
            "status": "ok_cached",
        }
        return True, meta

    paper_dir.mkdir(parents=True, exist_ok=True)

    progress.log(f"  -> trying {arxiv_id} (pdf{' +src' if with_src else ''})")
    pdf_ok, pdf_err = download_file(pdf_url, pdf_path, timeout=timeout * 3, retries=retries, backoff=backoff)

    src_ok, src_err = True, None
    if with_src and src_url and src_path is not None:
        src_ok, src_err = download_file(src_url, src_path, timeout=timeout * 3, retries=retries, backoff=backoff)

    ok = pdf_ok and (src_ok if with_src else True)
    meta = {
        "field_no": field.index,
        "field_name": field.name,
        "field_slug": field.slug,
        "primary_codes": list(field.codes),
        "arxiv_id": arxiv_id,
        "title": entry["title"],
        "authors": entry["authors"],
        "categories": entry.get("categories", []),
        "local_dir": local_dir_rel,
        "files": {"pdf": str(pdf_path.relative_to(dataset_root)) if pdf_path.is_file() else None,
                  "src": str(src_path.relative_to(dataset_root)) if (with_src and src_path is not None and src_path.is_file()) else None},
        "urls": {"abs": abs_url, "pdf": pdf_url, "src": src_url},
        "downloaded": {"pdf": pdf_path.is_file(),
                       "src": (src_path is not None and src_path.is_file()) if with_src else False},
        "status": "ok" if ok else "failed",
        "errors": {"pdf": pdf_err, "src": src_err} if not ok else {},
    }
    if not ok:
        progress.log(f"     !! failed {arxiv_id}: {meta.get('errors')}")
    return ok, meta


def self_test(progress: Progress, timeout: float):
    tests = [
        ("arxiv.org", "https://arxiv.org/"),
        ("export.arxiv.org/api/query", "https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=1"),
    ]
    for name, url in tests:
        progress.log(f"[self-test] GET {name} ...")
        try:
            with open_url(url, timeout=timeout) as resp:
                status = getattr(resp, "status", 200)
                progress.log(f"[self-test] {name}: ok status={status}")
        except Exception as e:
            progress.log(f"[self-test] {name}: FAILED -> {e}")
            progress.log("Hint: if your browser uses Clash/Proxy, set HTTPS_PROXY/HTTP_PROXY or use --proxy.")
            return False
    return True


def process_field(field: FieldConfig, dataset_root: Path, local_root: Path, per_field: int, max_results_factor: int,
                 timeout: float, dry_run: bool, workers: int, retries: int, backoff: float, with_src: bool,
                 api_min_interval: float, api_state: dict, progress: Progress):
    field_dir = local_root / field.slug
    field_dir.mkdir(parents=True, exist_ok=True)

    max_results = max(per_field * max_results_factor, per_field)
    candidates = fetch_candidates(field.codes, max_results=max_results, timeout=timeout, api_min_interval=api_min_interval, api_state=api_state)

    progress.log(f"[{field.index:02d}] {field.name} ({', '.join(field.codes)}) candidates={len(candidates)}")

    accepted = 0
    meta_entries: List[dict] = []
    skipped = 0

    if dry_run:
        for e in candidates[:per_field]:
            meta_entries.append({"status": "dry_run_selected", "arxiv_id": e["id"], "field_no": field.index})
            accepted += 1
            progress.bar(f"[{field.index:02d}] done", accepted, per_field)
        return meta_entries, {"accepted": accepted, "skipped": skipped, "total_candidates": len(candidates)}

    # IMPORTANT: strict submission to avoid overshoot.
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {}
        cursor = 0

        def submit(e: dict):
            fut = executor.submit(
                download_one,
                entry=e,
                field=field,
                dataset_root=dataset_root,
                field_dir=field_dir,
                timeout=timeout,
                retries=retries,
                backoff=backoff,
                with_src=with_src,
                progress=progress,
            )
            futures[fut] = e

        while accepted < per_field and (cursor < len(candidates) or futures):
            remaining = per_field - accepted

            # cap in-flight by remaining needed (STRICT) and by workers*2 (for throughput)
            in_flight_cap = min(max(1, workers * 2), remaining)

            while cursor < len(candidates) and len(futures) < in_flight_cap and accepted < per_field:
                submit(candidates[cursor])
                cursor += 1

            if not futures:
                break

            fut = next(as_completed(list(futures.keys()), timeout=None))
            _ = futures.pop(fut, None)
            try:
                ok, meta = fut.result()
            except Exception as e:
                ok, meta = False, {"status": "failed", "errors": {"exception": str(e)}}

            meta_entries.append(meta)
            if ok:
                accepted += 1
                progress.bar(f"[{field.index:02d}] done", accepted, per_field)
            else:
                skipped += 1

        # At this point accepted == per_field (or no more candidates).
        # Cancel NOT-yet-started futures (best effort).
        for fut in list(futures.keys()):
            fut.cancel()

    if accepted < per_field:
        progress.log(f"[{field.index:02d}] warning: only accepted {accepted}/{per_field}, skipped={skipped}")

    return meta_entries, {"accepted": accepted, "skipped": skipped, "total_candidates": len(candidates)}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--per-field", type=int, default=5)
    p.add_argument("--max-results-factor", type=int, default=3)
    p.add_argument("--timeout", type=float, default=12.0)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--backoff", type=float, default=1.7)
    p.add_argument("--with-src", action="store_true")
    p.add_argument("--api-min-interval", type=float, default=3.2)
    p.add_argument("--field-nos", type=str, default="")
    p.add_argument("--max-fields", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--local-dir", type=str, default=".cache")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--proxy", type=str, default="", help="Force proxy, e.g. http://127.0.0.1:7890")
    p.add_argument("--self-test", action="store_true", help="Test connectivity and exit.")
    return p.parse_args()


def main():
    args = parse_args()
    progress = Progress(enabled=not args.quiet)

    if args.proxy:
        configure_proxy(args.proxy, progress)

    if args.self_test:
        ok = self_test(progress, timeout=args.timeout)
        sys.exit(0 if ok else 2)

    script_dir = Path(__file__).resolve().parent
    dataset_root = script_dir

    local_root = Path(args.local_dir)
    if not local_root.is_absolute():
        local_root = dataset_root / local_root
    local_root.mkdir(parents=True, exist_ok=True)

    category_path = dataset_root / "category.md"
    if not category_path.is_file():
        raise FileNotFoundError(f"category.md not found at {category_path}")

    fields = parse_category_md(category_path)
    selected: Optional[set] = None
    if args.field_nos.strip():
        selected = set(int(x.strip()) for x in args.field_nos.split(",") if x.strip())
    if selected is not None:
        fields = [f for f in fields if f.index in selected]
    if args.max_fields and args.max_fields > 0:
        fields = fields[: args.max_fields]

    progress.log(f"dataset_root={dataset_root}")
    progress.log(f"local_root={local_root}")
    progress.log(
        f"workers={args.workers} per_field={args.per_field} with_src={args.with_src} "
        f"dry_run={args.dry_run} timeout={args.timeout}s retries={args.retries} max_results_factor={args.max_results_factor}"
    )

    api_state = {"last_ts": 0.0, "lock": threading.Lock()}

    all_meta: List[dict] = []
    total_fields = len(fields)

    for i, field in enumerate(fields, start=1):
        meta, _stat = process_field(
            field=field,
            dataset_root=dataset_root,
            local_root=local_root,
            per_field=args.per_field,
            max_results_factor=args.max_results_factor,
            timeout=args.timeout,
            dry_run=args.dry_run,
            workers=args.workers,
            retries=args.retries,
            backoff=args.backoff,
            with_src=args.with_src,
            api_min_interval=args.api_min_interval,
            api_state=api_state,
            progress=progress,
        )
        all_meta.extend(meta)
        progress.bar("overall", i, total_fields)

    metadata_path = dataset_root / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(all_meta, f, ensure_ascii=False, indent=2)

    ok_cnt = len([m for m in all_meta if m.get("status") in ("ok", "ok_cached")])
    progress.flush_line()
    print(json.dumps({"ok": ok_cnt, "metadata": str(metadata_path), "local_root": str(local_root)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


'''
1) 只要 PDF（最快，先拿到 100 篇）
python arxiv_downloader_fast_v3.py --per-field 5 --workers 8

2) 需要 PDF + LaTeX 源码包（会慢一些）
python arxiv_downloader_fast_v3.py --per-field 5 --workers 8 --with-src
'''