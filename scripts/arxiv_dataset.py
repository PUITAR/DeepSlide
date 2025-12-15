import argparse
import os
import re
import time
import json
import tarfile
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import ssl
from xml.etree import ElementTree as ET

BASE_API = "http://export.arxiv.org/api/query"
CATEGORIES = {
    "cv": "cs.CV",
    "nlp": "cs.CL",
    "optimization": "math.OC",
}

def open_url(url: str, headers=None):
    req = Request(url, headers=headers or {"User-Agent": "DeepSlide/1.0"})
    try:
        ctx = ssl.create_default_context()
        return urlopen(req, context=ctx)
    except Exception:
        ctx = ssl._create_unverified_context()
        return urlopen(req, context=ctx)

def fetch_feed(cat: str, count: int):
    params = {
        "search_query": f"cat:{cat}",
        "start": 0,
        "max_results": count,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = f"{BASE_API}?{urlencode(params)}"
    with open_url(url) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = []
    for entry in root.findall("atom:entry", ns):
        eid = entry.find("atom:id", ns).text.strip()
        title = entry.find("atom:title", ns).text.strip()
        authors = [a.find("atom:name", ns).text.strip() for a in entry.findall("atom:author", ns)]
        m = re.search(r"abs/(\d{4}\.\d{5}(v\d+)?)", eid)
        if not m:
            continue
        arxiv_id = m.group(1)
        entries.append({"id": arxiv_id, "title": title, "authors": authors})
    return entries

def download_source(arxiv_id: str, dest_dir: str):
    os.makedirs(dest_dir, exist_ok=True)
    src_url = f"https://arxiv.org/src/{arxiv_id}?mod=src&download=1"
    tar_path = os.path.join(dest_dir, f"{arxiv_id}.tar.gz")
    try:
        with open_url(src_url) as resp:
            data = resp.read()
        with open(tar_path, "wb") as f:
            f.write(data)
    except Exception:
        return src_url, None, None, False
    extracted_dir = os.path.join(dest_dir, arxiv_id)
    os.makedirs(extracted_dir, exist_ok=True)
    ok = False
    for mode in ["r:*", "r:gz", "r:bz2"]:
        try:
            with tarfile.open(tar_path, mode) as tf:
                tf.extractall(extracted_dir)
            ok = True
            break
        except Exception:
            continue
    return src_url, tar_path, extracted_dir, ok

def build_dataset(counts, out_root="data", delay=2.0, skip_existing=True):
    os.makedirs(out_root, exist_ok=True)
    meta = []
    for key, cat in CATEGORIES.items():
        n = counts.get(key, 0)
        if n <= 0:
            continue
        fetched = fetch_feed(cat, max(n * 3, n))
        got = 0
        for e in fetched:
            sample_dir = os.path.join(out_root, key)
            os.makedirs(sample_dir, exist_ok=True)
            id_dir = os.path.join(sample_dir, e["id"])
            if skip_existing and os.path.isdir(id_dir) and os.listdir(id_dir):
                meta.append({
                    "id": e["id"],
                    "title": e["title"],
                    "authors": e["authors"],
                    "category": key,
                    "source_url": f"https://arxiv.org/e-print/{e['id']}",
                    "dir": id_dir,
                    "downloaded": True,
                    "extracted": True,
                })
                got += 1
                if got >= n:
                    break
                continue
            src_url, tar_path, extracted_dir, extracted = download_source(e["id"], sample_dir)
            meta.append({
                "id": e["id"],
                "title": e["title"],
                "authors": e["authors"],
                "category": key,
                "source_url": src_url,
                "tar_path": tar_path,
                "dir": extracted_dir if extracted else sample_dir,
                "downloaded": tar_path is not None,
                "extracted": extracted,
            })
            if tar_path is not None:
                got += 1
            if got >= n:
                break
            time.sleep(delay)
    with open(os.path.join(out_root, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--cv", type=int, default=3)
    p.add_argument("--nlp", type=int, default=3)
    p.add_argument("--optimization", type=int, default=4)
    p.add_argument("--out", type=str, default="data")
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--no-skip", action="store_true")
    return p.parse_args()

def main():
    args = parse_args()
    counts = {"cv": args.cv, "nlp": args.nlp, "optimization": args.optimization}
    meta = build_dataset(counts, out_root=args.out, delay=args.delay, skip_existing=not args.no_skip)
    print(json.dumps({"samples": len(meta), "out": args.out}, ensure_ascii=False))

if __name__ == "__main__":
    main()
