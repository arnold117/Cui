"""T5 metadata backfill for imported corpus entries (arXiv/DOI -> ~/.cui sidecars).

Fetch real title/authors/year/citations without API keys:
  - doi:*  -> OpenAlex works (filter=doi:)   [cited_by_count included]
  - arxiv:*-> arXiv export API (id_list)     [title/authors/year; no citations]
  - local:*-> no external source -> meta_pending

Writes one sidecar per entry: ~/.cui/materials/<safe>.meta.json
Fields: anchor, title, authors, year, citations (null when unknown), source, status.
status = ok | meta_pending (fetch failed or unavailable).

Usage (backend/, cui env): python scripts/t5_meta_backfill.py [--limit N] [--sleep 0.4]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

import httpx
import time as _time

DATA_ROOT = Path.home() / ".cui" / "materials"


def _safe(key: str) -> str:
    return key.replace("/", "_").replace(":", "_")


_HEADERS = {"User-Agent": "cui-v5-importer/0.1 (metadata backfill; mailto:arnold@invalid.local)"}


def _get(url: str, **kwargs) -> httpx.Response | None:
    for attempt in range(4):
        try:
            resp = httpx.get(url, headers=_HEADERS, timeout=25, **kwargs)
            if resp.status_code == 429:
                retry = float(resp.headers.get("Retry-After", 3 * (attempt + 1)))
                _time.sleep(min(retry, 12))
                continue
            return resp if resp.status_code == 200 else None
        except Exception:
            _time.sleep(2 * (attempt + 1))
    return None


def fetch_doi(doi: str) -> dict | None:
    resp = _get("https://api.openalex.org/works", params={"filter": f"doi:{doi}", "per-page": 1})
    if resp is None:
        return None
    data = resp.json()
    results = data.get("results") or []
    if not results:
        return None
    w = results[0]
    authors = [a["author"]["display_name"] for a in w.get("authorships") or [] if a.get("author")]
    return {"title": w.get("title"), "authors": authors[:12], "year": w.get("publication_year"), "citations": w.get("cited_by_count")}


def fetch_arxiv(arxiv_id: str) -> dict | None:
    resp = _get("https://export.arxiv.org/api/query", params={"id_list": arxiv_id, "max_results": 1})
    if resp is None:
        return None
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    entry = root.find("a:entry", ns)
    if entry is None:
        return None
    title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
    authors = [a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)]
    published = entry.findtext("a:published", default="", namespaces=ns) or ""
    return {"title": title, "authors": [a for a in authors if a][:12], "year": int(published[:4]) if published[:4].isdigit() else None, "citations": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--sleep", type=float, default=1.2)
    args = parser.parse_args(argv)

    anchors = sorted(p.name[: -len(".md")].replace("_", "/", 1).replace("_", "/") for p in DATA_ROOT.glob("*.md"))
    # the filename escaping is lossy for doi slashes; rebuild keys from source_locator files instead
    anchors = sorted(p.stem for p in DATA_ROOT.glob("*.md"))
    print(f"entries on disk: {len(anchors)}")
    stats = {"ok": 0, "pending": 0, "failed": 0}
    for i, safe in enumerate(anchors):
        if args.limit and i >= args.limit:
            break
        meta_path = DATA_ROOT / f"{safe}.meta.json"
        if meta_path.exists():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if existing.get("status") == "ok":
                continue
        if safe.startswith("arxiv_"):
            meta = fetch_arxiv(safe[len("arxiv_"):])
        elif safe.startswith("doi_"):
            doi = safe[len("doi_"):].replace("_", "/")
            meta = fetch_doi(doi)
        else:
            meta = None
        out = {"anchor": safe, "status": "ok" if meta else "meta_pending"}
        if meta:
            out.update(meta)
        else:
            out["title"] = None
            stats["failed"] += 1
        (DATA_ROOT / f"{safe}.meta.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        stats["ok" if meta else "pending"] += 1
        if i % 20 == 0:
            print(f"  {i + 1}/{len(anchors)} ok={stats['ok']} pending={stats['pending']}", flush=True)
        time.sleep(args.sleep)
    print(f"done: ok={stats['ok']} meta_pending={stats['pending']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
