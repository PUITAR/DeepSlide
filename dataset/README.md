# Dataset Downloader

Deterministic arXiv batch downloader based on `category.md`. By default, only PDFs are downloaded; use `--with-src` if source packages are needed.

## File Descriptions

- [arxiv_downloader.py](arxiv_downloader.py): Main program  
- [category.md](category.md): Research fields and arXiv category codes table (drives the download)  
- [metadata.json](metadata.json): Download result index (generated after execution)

## Features Overview

- Reads category codes for each research field from `category.md`  
- Downloads `--per-field` papers for each field  
- Verifies and downloads PDFs, optionally downloads source packages (src)  
- Writes a unified index to `metadata.json`

## Environment Requirements

- Python 3.8+ (standard library only, no third-party dependencies)  
- Access to arXiv (use a proxy if necessary)

## Usage

Run in the current directory:

```bash
python arxiv_downloader.py --per-field 5
```

Download PDFs only (default):

```bash
python arxiv_downloader.py --per-field 5
```

Download PDF + source package:

```bash
python arxiv_downloader.py --per-field 5 --with-src
```

Self-test network connectivity:

```bash
python arxiv_downloader.py --self-test
```

## Parameter Description

- `--per-field`: Number of papers to download per field (default: 5)  
- `--max-results-factor`: Multiplier for API candidate count (default: 3)  
- `--timeout`: Request timeout in seconds (default: 12.0)  
- `--workers`: Number of concurrent threads (default: 6)  
- `--retries`: Number of retry attempts on failure (default: 2)  
- `--backoff`: Backoff multiplier (default: 1.7)  
- `--with-src`: Download source package (src)  
- `--api-min-interval`: Minimum interval between API requests (default: 3.2 seconds)  
- `--field-nos`: Download only specified field numbers, comma-separated (e.g., `1,2,5`)  
- `--max-fields`: Process at most the first N fields  
- `--dry-run`: Select only, without downloading  
- `--local-dir`: Root download directory (default: `.cache`, relative to current directory)  
- `--quiet`: Disable progress output  
- `--proxy`: Force proxy (e.g., `http://127.0.0.1:7890`)  
- `--self-test`: Connectivity test then exit

## Output Structure

Default download directory is `.cache` (can be changed via `--local-dir`). Example structure:

```
.cache/
  01-artificial-intelligence/
    2401.01234/
      paper.pdf
      source.tar.gz
```

`field_slug` is generated from the number and field name; `source.tar.gz` is downloaded only when `--with-src` is enabled.

## metadata.json Description

After execution, [metadata.json](metadata.json) is generated. Example fields:

- `field_no` / `field_name` / `field_slug`  
- `primary_codes`: Primary category codes for the field  
- `arxiv_id` / `title` / `authors` / `categories`  
- `local_dir`: Path relative to this directory  
- `files`: Relative paths for `pdf` and `src`  
- `urls`: `abs` / `pdf` / `src` links  
- `downloaded`: Whether download succeeded  
- `status`: `ok` / `ok_cached` / `failed`

## category.md Description

`category.md` maintains research fields and their category codes in a table format. The program parses the "Primary arXiv Codes" column where codes are wrapped in backticks.

## Notes

- If network access is restricted, configure system proxy or use `--proxy`.  
- Setting `--workers` too high may trigger rate limiting; choose a moderate value.  
- `--with-src` significantly slows down the process, and not all papers have available source packages.