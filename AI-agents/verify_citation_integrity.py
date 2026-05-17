#!/usr/bin/env python3
r"""
Verify ALIUS Bulletin citation integrity.

This is an audit tool, not a build dependency. It checks two different things:

1. The per-interview BibTeX library under ``Interviews/**.bib`` against DOI
   metadata using DOI content negotiation (Crosscite/DataCite/Crossref).
2. DOI/URL strings in reconstructed TeX against the off-repo original reference
   PDFs listed in ``%TEMP%\alius-original-reference-pdfs\manifest.json``.

Outputs are written to ``tmp/citation-verification`` by default so the original
PDFs and generated audit artifacts never become repository build assets.
"""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import difflib
import json
import os
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - report mode handles this cleanly.
    fitz = None


REPO = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    Path(os.environ.get("TEMP", ""))
    / "alius-original-reference-pdfs"
    / "manifest.json"
)
DEFAULT_OUT = REPO / "tmp" / "citation-verification"
USER_AGENT = "ALIUS Bulletin citation integrity audit (https://aliusresearch.org)"


def normalize_for_compare(text: str) -> str:
    text = latex_to_text(text)
    text = normalize_extraction_artifacts(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def latex_to_text(text: str) -> str:
    replacements = {
        r"{\`e}": "è",
        r"{\'e}": "é",
        r'{\"e}': "ë",
        r"{\`a}": "à",
        r"{\'a}": "á",
        r'{\"a}': "ä",
        r'{\"o}': "ö",
        r'{\"u}': "ü",
        r"\&": "&",
        r"\_": "_",
        r"\%": "%",
        r"\#": "#",
        r"\$": "$",
        r"\{": "{",
        r"\}": "}",
        r"``": "“",
        r"''": "”",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"\\[a-zA-Z]+(?:\{([^{}]*)\})?", lambda m: m.group(1) or "", text)
    return text


def normalize_extraction_artifacts(text: str) -> str:
    replacements = {
        "\u025c": "q",
        "\u0278": "t",
        "\u02ae": "Th",
        "\u02b0": "ff",
        "\u02b4": "ffi",
        "\u02be": "ft",
        "\u02bf": "fi",
        "\u02c0": "fl",
        "\u02c1": "fi",
        "\u02d9": "Th",
        "\u02ef": "gy",
        "\u068d": "-",
        "\u08bc": "ti",
        "\u099e": "ti",
        "ãNEUROSCI": "JNEUROSCI",
        "'ps://": "ttps://",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Stitch the common split produced by the source PDF: one span contains "h"
    # and the next begins with "'ps://".
    text = re.sub(r"\bh\s+ttps://", "https://", text)
    text = text.replace("bulle\u099en", "bulletin").replace("bulle\u08bcn", "bulletin")
    text = text.replace("https://doi.org/https://doi.org/", "https://doi.org/")
    text = text.replace("http://doi.org/http://doi.org/", "http://doi.org/")
    return text


def parse_bib_file(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    header = re.search(r"@\w+\s*\{\s*([^,\s]+)", text)
    if not header:
        return None
    fields: dict[str, str] = {}
    for name, value in re.findall(r"(?ms)^\s*([A-Za-z]+)\s*=\s*\{(.*?)\}\s*,?\s*$", text):
        fields[name.lower()] = re.sub(r"\s+", " ", value.strip())
    return {"key": header.group(1), "path": path, "fields": fields}


def author_families(author_field: str) -> list[str]:
    families: list[str] = []
    for part in re.split(r"\s+and\s+", author_field):
        part = latex_to_text(part.strip())
        if "," in part:
            family = part.split(",", 1)[0]
        else:
            family = part.split()[-1] if part.split() else ""
        if family:
            families.append(normalize_for_compare(family))
    return families


def csl_author_families(csl: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for author in csl.get("author") or []:
        family = author.get("family") or author.get("literal") or ""
        if family:
            families.append(normalize_for_compare(family))
    return families


def fetch_csl(doi: str, timeout: int = 25) -> dict[str, Any]:
    url = "https://doi.org/" + doi
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.citationstyles.csl+json",
            "User-Agent": USER_AGENT,
        },
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            return {
                "doi": doi,
                "status": "OK",
                "http_status": getattr(resp, "status", ""),
                "resolved_url": resp.geturl(),
                "elapsed_s": round(time.time() - start, 3),
                "csl": data,
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        return {
            "doi": doi,
            "status": "ERROR",
            "http_status": exc.code,
            "resolved_url": getattr(exc, "url", ""),
            "elapsed_s": round(time.time() - start, 3),
            "csl": {},
            "error": f"HTTPError: {exc}",
        }
    except Exception as exc:
        return {
            "doi": doi,
            "status": "ERROR",
            "http_status": "",
            "resolved_url": "",
            "elapsed_s": round(time.time() - start, 3),
            "csl": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def crossref_message_to_csl(message: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in message.get("author") or []:
        authors.append({"family": author.get("family", ""), "given": author.get("given", "")})
    issued = message.get("issued") or message.get("published-print") or message.get("published-online") or {}
    return {
        "title": (message.get("title") or [""])[0],
        "DOI": message.get("DOI", ""),
        "author": authors,
        "issued": issued,
        "container-title": (message.get("container-title") or [""])[0],
    }


def fetch_crossref(doi: str, timeout: int = 25) -> dict[str, Any]:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    start = time.time()
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body)
                return {
                    "doi": doi,
                    "status": "OK",
                    "http_status": getattr(resp, "status", ""),
                    "resolved_url": url,
                    "elapsed_s": round(time.time() - start, 3),
                    "csl": crossref_message_to_csl(data.get("message") or {}),
                    "error": "",
                }
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                time.sleep(1.5)
                continue
            return {
                "doi": doi,
                "status": "ERROR",
                "http_status": exc.code,
                "resolved_url": url,
                "elapsed_s": round(time.time() - start, 3),
                "csl": {},
                "error": f"HTTPError: {exc}",
            }
        except Exception as exc:
            return {
                "doi": doi,
                "status": "ERROR",
                "http_status": "",
                "resolved_url": url,
                "elapsed_s": round(time.time() - start, 3),
                "csl": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
    raise AssertionError("unreachable")


def fetch_doi_metadata(doi: str) -> dict[str, Any]:
    """Resolve metadata while avoiding DOI.org rate limits for Crossref DOIs."""

    doi_lower = doi.lower()
    if doi_lower.startswith("10.34700/") or doi_lower.startswith("10.5281/"):
        return fetch_csl(doi)
    result = fetch_crossref(doi)
    if result.get("status") == "OK":
        return result
    # Some valid DOIs are not Crossref-registered. Fall back to DOI content
    # negotiation for those, but keep 429s/errors transparent in the report.
    if result.get("http_status") in (404, 400):
        fallback = fetch_csl(doi)
        if fallback.get("status") == "OK":
            return fallback
    return result


def looks_incomplete_doi(doi: str) -> bool:
    return (
        doi.endswith("-")
        or doi.endswith("/")
        or "..." in doi
    )


def clean_doi(raw: str) -> str:
    raw = normalize_extraction_artifacts(latex_to_text(raw))
    raw = raw.replace("10.5281/10.5281/zenodo", "10.5281/zenodo")
    raw = raw.strip().strip("<>()[]{}.,;:")
    raw = re.sub(r"\\+$", "", raw)
    return raw


def extract_dois_and_urls(text: str) -> tuple[set[str], set[str]]:
    text = normalize_extraction_artifacts(latex_to_text(text))
    text = re.sub(r"(10\.\d{4,9}/)\s+", r"\1", text)
    text = re.sub(r"(doi\.org/10\.\d{4,9}/)\s+", r"\1", text, flags=re.I)
    for _ in range(4):
        text = re.sub(r"(10\.\d{4,9}/[^\s<>{}\\]*-)\s+([A-Za-z0-9])", r"\1\2", text, flags=re.I)
    doi_matches = re.findall(r"(?:doi:\s*|https?://(?:dx\.)?doi\.org/)(10\.\d{4,9}/[^\s<>{}\\]+)", text, flags=re.I)
    dois = {clean_doi(m) for m in doi_matches}
    dois = {d for d in dois if d}
    url_matches = re.findall(r"https?://[^\s<>{}\\]+", text, flags=re.I)
    urls = {u.strip().strip("<>()[]{}.,;:") for u in url_matches}
    return dois, urls


def tex_plain_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    pieces = re.findall(r"\\ALIUSPlacedTextContent\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}\{(.*?)\}", text)
    return " ".join(pieces)


def pdf_plain_text(path: Path) -> str:
    if fitz is None:
        return ""
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def verify_unique_dois(dois: set[str], max_workers: int) -> dict[str, dict[str, Any]]:
    todo = sorted(d for d in dois if not looks_incomplete_doi(d))
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_doi_metadata, doi): doi for doi in todo}
        for future in as_completed(futures):
            doi = futures[future]
            results[doi] = future.result()
    for doi in sorted(d for d in dois if looks_incomplete_doi(d)):
        results[doi] = {
            "doi": doi,
            "status": "MALFORMED",
            "http_status": "",
            "resolved_url": "",
            "elapsed_s": 0,
            "csl": {},
            "error": "DOI token appears incomplete in extracted text",
        }
    return results


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    repo = args.repo.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    bib_entries = [e for p in sorted((repo / "Interviews").glob("Issue*/*/*.bib")) if (e := parse_bib_file(p))]
    tex_paths = sorted((repo / "Interviews").glob("Issue*/*/*.tex"))

    # DOI universe: BibTeX entries plus DOI strings printed in the reconstructed articles.
    all_dois: set[str] = set()
    for entry in bib_entries:
        doi = entry["fields"].get("doi", "")
        if doi:
            all_dois.add(clean_doi(doi))
    tex_rows: list[dict[str, Any]] = []
    for tex in tex_paths:
        dois, urls = extract_dois_and_urls(tex_plain_text(tex))
        for doi in sorted(dois):
            all_dois.add(doi)
            tex_rows.append({"tex": tex.relative_to(repo).as_posix(), "kind": "doi", "value": doi})
        for url in sorted(urls):
            tex_rows.append({"tex": tex.relative_to(repo).as_posix(), "kind": "url", "value": url})

    doi_results = verify_unique_dois(all_dois, args.workers)

    bib_rows: list[dict[str, Any]] = []
    for entry in bib_entries:
        fields = entry["fields"]
        doi = clean_doi(fields.get("doi", ""))
        result = doi_results.get(doi, {})
        csl = result.get("csl") or {}
        bib_title = latex_to_text(fields.get("title", ""))
        csl_title = csl.get("title") or ""
        title_ratio = difflib.SequenceMatcher(None, normalize_for_compare(bib_title), normalize_for_compare(csl_title)).ratio() if csl_title else 0
        bib_families = author_families(fields.get("author", ""))
        csl_families = csl_author_families(csl)
        csl_family_set = set(csl_families)
        missing_bib_families = [name for name in bib_families if name and name not in csl_family_set]
        title_status = "OK" if normalize_for_compare(bib_title) and normalize_for_compare(bib_title) in normalize_for_compare(csl_title) else ("OK" if title_ratio >= 0.72 else "WARNING")
        author_status = "OK" if not missing_bib_families else "WARNING"
        bib_rows.append(
            {
                "key": entry["key"],
                "path": entry["path"].relative_to(repo).as_posix(),
                "doi": doi,
                "doi_status": result.get("status", "MISSING"),
                "resolved_url": result.get("resolved_url", ""),
                "bib_title": bib_title,
                "csl_title": csl_title,
                "title_status": title_status,
                "title_similarity": f"{title_ratio:.3f}",
                "bib_authors": fields.get("author", ""),
                "csl_authors": "; ".join(csl_families),
                "author_status": author_status,
                "missing_bib_families_in_csl": "; ".join(missing_bib_families),
                "error": result.get("error", ""),
            }
        )

    doi_rows: list[dict[str, Any]] = []
    for doi, result in sorted(doi_results.items()):
        csl = result.get("csl") or {}
        doi_rows.append(
            {
                "doi": doi,
                "status": result.get("status", ""),
                "http_status": result.get("http_status", ""),
                "resolved_url": result.get("resolved_url", ""),
                "csl_title": csl.get("title", ""),
                "csl_doi": csl.get("DOI", ""),
                "error": result.get("error", ""),
            }
        )

    original_rows: list[dict[str, Any]] = []
    for item in load_manifest(args.manifest):
        tex = repo / item["tex"]
        ref = Path(item["ref"])
        if not tex.exists() or not ref.exists():
            continue
        tex_dois, tex_urls = extract_dois_and_urls(tex_plain_text(tex))
        ref_dois, ref_urls = extract_dois_and_urls(pdf_plain_text(ref))
        original_rows.append(
            {
                "tex": item["tex"],
                "ref_rel": item.get("ref_rel", ref.name),
                "tex_doi_count": len(tex_dois),
                "ref_doi_count": len(ref_dois),
                "missing_from_tex_dois": "; ".join(sorted(ref_dois - tex_dois)),
                "extra_in_tex_dois": "; ".join(sorted(tex_dois - ref_dois)),
                "tex_url_count": len(tex_urls),
                "ref_url_count": len(ref_urls),
                "missing_from_tex_urls": "; ".join(sorted(ref_urls - tex_urls)),
                "extra_in_tex_urls": "; ".join(sorted(tex_urls - ref_urls)),
            }
        )

    write_csv(
        out / "interview_bib_doi_report.csv",
        bib_rows,
        [
            "key",
            "path",
            "doi",
            "doi_status",
            "resolved_url",
            "bib_title",
            "csl_title",
            "title_status",
            "title_similarity",
            "bib_authors",
            "csl_authors",
            "author_status",
            "missing_bib_families_in_csl",
            "error",
        ],
    )
    write_csv(out / "all_extracted_tex_citation_tokens.csv", tex_rows, ["tex", "kind", "value"])
    write_csv(out / "all_unique_doi_resolution.csv", doi_rows, ["doi", "status", "http_status", "resolved_url", "csl_title", "csl_doi", "error"])
    write_csv(
        out / "original_vs_tex_citation_tokens.csv",
        original_rows,
        [
            "tex",
            "ref_rel",
            "tex_doi_count",
            "ref_doi_count",
            "missing_from_tex_dois",
            "extra_in_tex_dois",
            "tex_url_count",
            "ref_url_count",
            "missing_from_tex_urls",
            "extra_in_tex_urls",
        ],
    )

    summary = {
        "bib_entries": len(bib_rows),
        "bib_doi_ok": sum(1 for r in bib_rows if r["doi_status"] == "OK"),
        "bib_title_warnings": sum(1 for r in bib_rows if r["title_status"] != "OK"),
        "bib_author_warnings": sum(1 for r in bib_rows if r["author_status"] != "OK"),
        "unique_dois": len(doi_rows),
        "unique_doi_ok": sum(1 for r in doi_rows if r["status"] == "OK"),
        "unique_doi_malformed": sum(1 for r in doi_rows if r["status"] == "MALFORMED"),
        "unique_doi_errors": sum(1 for r in doi_rows if r["status"] == "ERROR"),
        "original_tex_pairs": len(original_rows),
        "pairs_with_doi_deltas": sum(1 for r in original_rows if r["missing_from_tex_dois"] or r["extra_in_tex_dois"]),
        "pairs_with_url_deltas": sum(1 for r in original_rows if r["missing_from_tex_urls"] or r["extra_in_tex_urls"]),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
