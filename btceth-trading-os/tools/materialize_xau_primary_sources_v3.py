"""Restore pinned Binance source snapshots or fetch official URLs, then rehash evidence."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "xau_primary_sources_v3.json"
PARSER_VERSION = "xau-source-extraction-3.0.0"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def clean(text: str) -> str:
    return " ".join(text.split())


class ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id") == "support_article":
            self.depth = 1
        elif self.depth:
            self.depth += 1
        if tag == "h1":
            self.in_title = True
        if tag == "meta" and values.get("name") == "description":
            self.description = values.get("content") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self.in_title = False
        if self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)
        if self.in_title:
            self.title_parts.append(data)


def extract(spec: dict[str, object], raw: bytes) -> dict[str, object]:
    source_id = str(spec["source_id"])
    if spec["source_type"] == "REST_API_SNAPSHOT":
        payload = json.loads(raw)
        symbol = next((s for s in payload["symbols"] if s["symbol"] == "XAUUSDT"), None)
        if symbol is None:
            raise ValueError("XAUUSDT absent from official exchangeInfo")
        relevant = {k: symbol.get(k) for k in ("symbol", "pair", "contractType", "status", "onboardDate", "filters")}
        text = clean(json.dumps(relevant, sort_keys=True, ensure_ascii=False))
        title = "Binance USD-M exchangeInfo XAUUSDT"
        published = None
    else:
        html = raw.decode("utf-8")
        if source_id not in html or "binance.com" not in html:
            raise ValueError("Announcement identity absent")
        parser = ArticleParser()
        parser.feed(html)
        text = clean(" ".join(parser.parts) or parser.description)
        title = clean(" ".join(parser.title_parts))
        if not title:
            match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
            title = clean(re.sub(r"<[^>]+>", "", match.group(1))) if match else ""
        pub_match = re.search(r"Published on (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", html)
        published = pub_match.group(1).replace(" ", "T") + ":00Z" if pub_match else None
        if spec["source_type"] == "EXCHANGE_ANNOUNCEMENT" and "/square/" in str(spec["canonical_url"]):
            ld_match = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
            if ld_match:
                ld = json.loads(ld_match.group(1))
                text = clean(ld.get("text", text))
                title = clean(ld.get("headline", title))
                published = ld.get("datePublished")
        if not text or not title:
            raise ValueError("Announcement body or title absent")
    claims = spec.get("claims", {})
    effective_at = spec.get("effective_at")
    if effective_at and str(effective_at)[:16].replace("T", " ") not in text:
        raise ValueError(f"Effective timestamp missing from source {source_id}")
    for claim_id, fragment in claims.items():
        if clean(str(fragment)).casefold() not in text.casefold():
            raise ValueError(f"Claim {claim_id} missing from source {source_id}")
    return {
        "source_id": source_id,
        "canonical_url": spec["canonical_url"],
        "source_type": spec["source_type"],
        "title": title,
        "published_at": published,
        "effective_at": spec.get("effective_at"),
        "affected_symbols": spec["affected_symbols"],
        "claims": claims,
        "extracted_text": text,
        "parser_version": PARSER_VERSION,
        "extraction_schema_version": "3.0.0",
    }


def materialize(manifest_path: Path = MANIFEST, source: str = "snapshot", report_path: Path | None = None) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text())
    results: dict[str, object] = {"manifest_version": manifest["manifest_version"], "source_mode": source,
                                  "sources_requested": len(manifest["sources"]), "sources_fetched": 0,
                                  "sources_restored_from_committed_snapshot": 0, "sources": {}, "source_failures": []}
    for source_id, spec in manifest["sources"].items():
        entry: dict[str, object] = {"canonical_url": spec["canonical_url"], "parser_version": PARSER_VERSION}
        try:
            if source == "network":
                request = urllib.request.Request(spec["canonical_url"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                if not raw:
                    raise ValueError("PRIMARY_SOURCE_FETCH_UNAVAILABLE: empty response")
                results["sources_fetched"] += 1
            else:
                snapshot = ROOT / spec["snapshot_path"]
                raw = snapshot.read_bytes()
                if digest(raw) != spec["snapshot_physical_sha256"]:
                    raise ValueError("Committed snapshot SHA mismatch")
                results["sources_restored_from_committed_snapshot"] += 1
            extracted = extract(spec, raw)
            if extracted["published_at"] != spec.get("published_at"):
                raise ValueError("Publication timestamp changed")
            logical_sha = digest(canonical(extracted))
            entry.update({"physical_sha256": digest(raw), "logical_sha256": logical_sha,
                          "logical_sha_match": logical_sha == spec["expected_logical_sha256"],
                          "published_at": extracted["published_at"], "title": extracted["title"]})
            entry["status"] = "PASS" if entry["logical_sha_match"] else "LOGICAL_SHA_MISMATCH"
            if entry["status"] == "PASS":
                destination = ROOT / spec["artifact_path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            else:
                results["source_failures"].append(source_id)
        except Exception as exc:
            entry["status"] = "PRIMARY_SOURCE_FETCH_UNAVAILABLE" if source == "network" else "SOURCE_INVALID"
            entry["error"] = str(exc)
            results["source_failures"].append(source_id)
        results["sources"][source_id] = entry
    results["all_passed"] = not results["source_failures"]
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(results, indent=2) + "\n")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("snapshot", "network"), default="snapshot")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "XAU_PRIMARY_SOURCE_REPRODUCIBILITY_V16.json")
    args = parser.parse_args()
    result = materialize(source=args.source, report_path=args.report)
    print(json.dumps(result, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
