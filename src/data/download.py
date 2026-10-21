"""Resumable downloader for papers listed in the Jantzen source CSV."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv

DEFAULT_INPUT = Path("data/source/Jantzen_species_interaction/papers_searched.csv")
DEFAULT_PDF_DIR = Path("data/papers/jantzen")
DEFAULT_REPORT_DIR = Path("outputs/paper_downloads")
DEFAULT_OVERRIDE_CSV = Path("data/ready/jantzen_pdf_urls.csv")
STATUS_FIELDS = [
    "paper_id",
    "doi",
    "source_link",
    "citation",
    "status",
    "pdf_path",
    "download_url",
    "download_source",
    "attempted_urls",
    "error",
]
PDF_HEADER = b"%PDF-"


class NonPdfResponse(ValueError):
    """A URL resolved successfully but served something other than a PDF."""

    def __init__(self, url: str, content_type: str) -> None:
        self.url = url
        super().__init__(f"response is not a PDF (Content-Type: {content_type})")


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    doi: str
    source_link: str
    citation: str
    used: str


@dataclass(frozen=True)
class DownloadCandidate:
    source: str
    url: str


@dataclass(frozen=True)
class DownloadConfig:
    pdf_dir: Path = DEFAULT_PDF_DIR
    report_dir: Path = DEFAULT_REPORT_DIR
    override_csv: Path | None = DEFAULT_OVERRIDE_CSV
    unpaywall_email: str | None = None
    semantic_scholar_api_key: str | None = None
    timeout_seconds: float = 45.0
    max_file_bytes: int = 100 * 1024 * 1024
    delay_seconds: float = 0.25
    overwrite: bool = False


@dataclass(frozen=True)
class DownloadSummary:
    total: int
    downloaded: int
    already_downloaded: int
    failed: int
    status_path: Path
    not_downloaded_path: Path


def _clean(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value.upper() == "NA" else value


def normalize_doi(value: str | None) -> str:
    """Normalize a DOI stored as a bare identifier, URL, or doi: value."""
    doi = _clean(value)
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def read_paper_records(
    csv_path: Path, *, only_used: bool = True, limit: int | None = None
) -> list[PaperRecord]:
    """Read the Jantzen paper inventory and validate its required columns."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Paper ID", "Reference DOI", "Link to paper", "Used", "Full Reference (APA)"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required CSV columns: {', '.join(sorted(missing))}")
        records = [
            PaperRecord(
                paper_id=_clean(row["Paper ID"]),
                doi=normalize_doi(row["Reference DOI"]),
                source_link=_clean(row["Link to paper"]),
                citation=_clean(row["Full Reference (APA)"]),
                used=_clean(row["Used"]),
            )
            for row in reader
            if not only_used or _clean(row["Used"]).lower() in {"y", "yes", "true", "1"}
        ]
    if any(not record.paper_id for record in records):
        raise ValueError("Every selected row must have a Paper ID")
    if len({record.paper_id for record in records}) != len(records):
        raise ValueError("Selected rows contain duplicate Paper IDs")
    return records[:limit] if limit is not None else records


def read_pdf_overrides(
    csv_path: Path | None, records: list[PaperRecord]
) -> dict[str, list[DownloadCandidate]]:
    """Load hand-verified PDF URLs and ensure they match the source inventory."""
    if csv_path is None or not csv_path.exists():
        return {}
    by_id = {record.paper_id: record for record in records}
    overrides: dict[str, list[DownloadCandidate]] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Paper ID", "Reference DOI", "PDF URL"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing override CSV columns: {', '.join(sorted(missing))}")
        for row in reader:
            paper_id = _clean(row["Paper ID"])
            if paper_id not in by_id:
                continue
            doi = normalize_doi(row["Reference DOI"])
            if doi.casefold() != by_id[paper_id].doi.casefold():
                raise ValueError(f"Override DOI does not match paper {paper_id}")
            url = _clean(row["PDF URL"])
            if not url.lower().startswith(("https://", "http://")):
                raise ValueError(f"Override URL for paper {paper_id} must be HTTP(S)")
            overrides.setdefault(paper_id, []).append(DownloadCandidate("verified_url", url))
    return overrides


def _safe_paper_id(paper_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", paper_id).strip("._")
    if not safe:
        raise ValueError(f"Paper ID cannot be used as a filename: {paper_id!r}")
    return safe


def pdf_path_for(record: PaperRecord, pdf_dir: Path) -> Path:
    return pdf_dir / f"paper_{_safe_paper_id(record.paper_id)}.pdf"


def is_pdf(path: Path) -> bool:
    """Check the PDF magic bytes rather than trusting a filename or content type."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as handle:
        return PDF_HEADER in handle.read(1024)


class PaperDownloader:
    """Discover public PDF locations and download verified PDF bytes."""

    def __init__(
        self,
        config: DownloadConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        override_urls: dict[str, list[DownloadCandidate]] | None = None,
    ) -> None:
        self.config = config
        self._semantic_scholar_rate_limited = False
        self.override_urls = override_urls or {}
        contact = f" (mailto:{config.unpaywall_email})" if config.unpaywall_email else ""
        self.client = httpx.Client(
            follow_redirects=True,
            timeout=config.timeout_seconds,
            transport=transport,
            headers={"User-Agent": f"Data-extraction-post-training/0.1{contact}"},
        )

    def __enter__(self) -> PaperDownloader:
        return self

    def __exit__(self, *_: object) -> None:
        self.client.close()

    def _json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.get(url, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("API response was not a JSON object")
        return payload

    def _unpaywall_candidates(self, doi: str) -> list[DownloadCandidate]:
        if not self.config.unpaywall_email:
            return []
        payload = self._json(
            f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
            params={"email": self.config.unpaywall_email},
        )
        locations = [payload.get("best_oa_location"), *(payload.get("oa_locations") or [])]
        return [
            DownloadCandidate("unpaywall", location["url_for_pdf"])
            for location in locations
            if isinstance(location, dict) and location.get("url_for_pdf")
        ]

    def _openalex_candidates(self, doi: str) -> list[DownloadCandidate]:
        payload = self._json(f"https://api.openalex.org/works/{quote(f'doi:{doi}', safe=':/')}")
        if normalize_doi(payload.get("doi")).casefold() != doi.casefold():
            raise ValueError("OpenAlex returned a work with a different DOI")
        locations = payload.get("locations") or []
        # Repository copies often work when the publisher website rejects automated requests.
        locations = sorted(
            (location for location in locations if isinstance(location, dict)),
            key=lambda location: (location.get("source") or {}).get("type") != "repository",
        )
        return [
            DownloadCandidate("openalex", location["pdf_url"])
            for location in locations
            if location.get("pdf_url")
        ]

    def _semantic_scholar_candidates(self, doi: str) -> list[DownloadCandidate]:
        headers = {}
        if self.config.semantic_scholar_api_key:
            headers["x-api-key"] = self.config.semantic_scholar_api_key
        try:
            payload = self._json(
                f"https://api.semanticscholar.org/graph/v1/paper/{quote(f'DOI:{doi}', safe='')}",
                params={"fields": "openAccessPdf"},
                headers=headers,
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._semantic_scholar_rate_limited = True
            raise
        location = payload.get("openAccessPdf") or {}
        if isinstance(location, dict) and location.get("url"):
            return [DownloadCandidate("semantic_scholar", location["url"])]
        return []

    def _crossref_candidates(self, doi: str) -> list[DownloadCandidate]:
        payload = self._json(f"https://api.crossref.org/works/{quote(doi, safe='')}")
        message = payload.get("message") or {}
        links = message.get("link") or [] if isinstance(message, dict) else []
        return [
            DownloadCandidate("crossref", link["URL"])
            for link in links
            if isinstance(link, dict)
            and link.get("URL")
            and str(link.get("content-type", "")).lower() == "application/pdf"
        ]

    def candidates(self, record: PaperRecord) -> tuple[list[DownloadCandidate], list[str]]:
        """Collect candidates without allowing one metadata API failure to stop the paper."""
        candidates: list[DownloadCandidate] = []
        errors: list[str] = []
        if record.doi:
            lookups = [
                ("openalex", self._openalex_candidates),
                ("unpaywall", self._unpaywall_candidates),
                ("crossref", self._crossref_candidates),
            ]
            if not self._semantic_scholar_rate_limited:
                lookups.append(("semantic_scholar", self._semantic_scholar_candidates))
            for name, lookup in lookups:
                try:
                    candidates.extend(lookup(record.doi))
                except Exception as exc:
                    errors.append(f"{name}: {type(exc).__name__}: {exc}")
        if record.source_link:
            candidates.append(DownloadCandidate("source_csv", record.source_link))
        if record.doi:
            candidates.append(DownloadCandidate("doi_resolver", f"https://doi.org/{record.doi}"))

        unique: list[DownloadCandidate] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate.url.lower().startswith(("http://", "https://")):
                errors.append(f"{candidate.source}: unsupported URL scheme")
            elif candidate.url not in seen:
                seen.add(candidate.url)
                unique.append(candidate)
        return unique, errors

    def _figshare_candidates(
        self, redirected_url: str, record: PaperRecord
    ) -> list[DownloadCandidate]:
        """Resolve a public Figshare article reached through a repository redirect."""
        path = urlparse(redirected_url).path
        match = re.search(r"/articles/(?:[^/]+/)*(\d+)(?:/|$)", path)
        if not match:
            return []
        payload = self._json(f"https://api.figshare.com/v2/articles/{match.group(1)}")
        resource_doi = normalize_doi(payload.get("resource_doi"))
        if resource_doi and resource_doi.casefold() != record.doi.casefold():
            raise ValueError("Figshare article DOI differs from the requested paper")
        if not resource_doi:
            title = re.sub(r"\W+", " ", str(payload.get("title") or "").casefold()).strip()
            citation = re.sub(r"\W+", " ", record.citation.casefold())
            if len(title) < 20 or title not in citation:
                raise ValueError("Figshare article title does not match the requested paper")
        return [
            DownloadCandidate("figshare", file["download_url"])
            for file in payload.get("files") or []
            if isinstance(file, dict)
            and str(file.get("name", "")).lower().endswith(".pdf")
            and file.get("download_url")
        ]

    def _download_candidate(self, candidate: DownloadCandidate, destination: Path) -> str:
        part_path = destination.with_suffix(destination.suffix + ".part")
        part_path.unlink(missing_ok=True)
        try:
            with self.client.stream(
                "GET",
                candidate.url,
                headers={"Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1"},
            ) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.config.max_file_bytes:
                    raise ValueError(f"Content-Length exceeds {self.config.max_file_bytes} bytes")
                size = 0
                with part_path.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.config.max_file_bytes:
                            raise ValueError(f"Download exceeds {self.config.max_file_bytes} bytes")
                        handle.write(chunk)
                final_url = str(response.url)
            if not is_pdf(part_path):
                content_type = response.headers.get("content-type", "unknown")
                raise NonPdfResponse(final_url, content_type)
            os.replace(part_path, destination)
            return final_url
        except Exception:
            part_path.unlink(missing_ok=True)
            raise

    def download(self, record: PaperRecord) -> dict[str, str]:
        destination = pdf_path_for(record, self.config.pdf_dir)
        base = {
            "paper_id": record.paper_id,
            "doi": record.doi,
            "source_link": record.source_link,
            "citation": record.citation,
            "pdf_path": str(destination),
        }
        if is_pdf(destination) and not self.config.overwrite:
            return {
                **base,
                "status": "already_downloaded",
                "download_url": "",
                "download_source": "existing_file",
                "attempted_urls": "",
                "error": "",
            }

        candidates = list(self.override_urls.get(record.paper_id, []))
        discovery_errors: list[str] = []
        discovery_done = not candidates
        if discovery_done:
            candidates, discovery_errors = self.candidates(record)
        attempts: list[str] = []
        seen = {candidate.url for candidate in candidates}
        index = 0
        while index < len(candidates) or not discovery_done:
            if index == len(candidates):
                discovered, errors = self.candidates(record)
                discovery_errors.extend(errors)
                for candidate in discovered:
                    if candidate.url not in seen:
                        seen.add(candidate.url)
                        candidates.append(candidate)
                discovery_done = True
                continue
            candidate = candidates[index]
            index += 1
            try:
                final_url = self._download_candidate(candidate, destination)
                attempts.append(f"{candidate.source}: {candidate.url}")
                return {
                    **base,
                    "status": "downloaded",
                    "download_url": final_url,
                    "download_source": candidate.source,
                    "attempted_urls": json.dumps(attempts, ensure_ascii=False),
                    "error": " | ".join(discovery_errors),
                }
            except Exception as exc:
                attempts.append(
                    f"{candidate.source}: {candidate.url} -> {type(exc).__name__}: {exc}"
                )
                if isinstance(exc, NonPdfResponse):
                    try:
                        for fallback in self._figshare_candidates(exc.url, record):
                            if fallback.url not in seen:
                                seen.add(fallback.url)
                                candidates.append(fallback)
                    except Exception as lookup_exc:
                        discovery_errors.append(
                            f"figshare: {type(lookup_exc).__name__}: {lookup_exc}"
                        )
        errors = [*discovery_errors]
        if not candidates:
            errors.append("No candidate PDF URL was found")
        else:
            errors.append("No candidate returned a valid PDF")
        return {
            **base,
            "status": "failed",
            "download_url": "",
            "download_source": "",
            "attempted_urls": json.dumps(attempts, ensure_ascii=False),
            "error": " | ".join(errors),
        }


def _read_existing_status(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["paper_id"]: row for row in csv.DictReader(handle)}


def _write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STATUS_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def _checkpoint_reports(
    status_path: Path,
    not_downloaded_path: Path,
    statuses: dict[str, dict[str, str]],
) -> None:
    rows = list(statuses.values())
    _write_csv(status_path, rows)
    _write_csv(
        not_downloaded_path,
        (row for row in rows if row.get("status") == "failed"),
    )


def download_papers(
    records: list[PaperRecord],
    config: DownloadConfig,
    *,
    transport: httpx.BaseTransport | None = None,
) -> DownloadSummary:
    """Download a batch, checkpointing status and failures after every paper."""
    config.pdf_dir.mkdir(parents=True, exist_ok=True)
    config.report_dir.mkdir(parents=True, exist_ok=True)
    status_path = config.report_dir / "download_status.csv"
    not_downloaded_path = config.report_dir / "not_downloaded.csv"
    statuses = _read_existing_status(status_path)
    overrides = read_pdf_overrides(config.override_csv, records)

    with PaperDownloader(config, transport=transport, override_urls=overrides) as downloader:
        for index, record in enumerate(records, start=1):
            result = downloader.download(record)
            previous = statuses.get(record.paper_id)
            if result["status"] == "already_downloaded" and previous:
                if previous.get("status") in {"downloaded", "already_downloaded"}:
                    for field in ("download_url", "attempted_urls"):
                        result[field] = previous.get(field, "")
                    if previous.get("download_source") not in {"", "existing_file"}:
                        result["download_source"] = previous["download_source"]
            statuses[record.paper_id] = result
            _checkpoint_reports(status_path, not_downloaded_path, statuses)
            print(f"[{index}/{len(records)}] paper {record.paper_id}: {result['status']}")
            if index < len(records) and config.delay_seconds:
                time.sleep(config.delay_seconds)

    selected = [statuses[record.paper_id] for record in records]
    return DownloadSummary(
        total=len(records),
        downloaded=sum(row["status"] == "downloaded" for row in selected),
        already_downloaded=sum(row["status"] == "already_downloaded" for row in selected),
        failed=sum(row["status"] == "failed" for row in selected),
        status_path=status_path,
        not_downloaded_path=not_downloaded_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="download-papers",
        description="Download verified PDFs from the Jantzen paper inventory.",
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--override-csv", type=Path, default=DEFAULT_OVERRIDE_CSV)
    parser.add_argument("--email", default=os.getenv("UNPAYWALL_EMAIL"))
    parser.add_argument("--semantic-scholar-api-key", default=os.getenv("SEMANTIC_SCHOLAR_API_KEY"))
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-file-mb", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--paper-id", action="append", dest="paper_ids", help="Select a Paper ID")
    parser.add_argument("--include-unused", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.max_file_mb < 1 or args.timeout <= 0 or args.delay < 0:
        raise SystemExit("Timeout and maximum size must be positive; delay cannot be negative")
    records = read_paper_records(
        args.input,
        only_used=not args.include_unused,
    )
    if args.paper_ids:
        selected_ids = set(args.paper_ids)
        available_ids = {record.paper_id for record in records}
        missing_ids = selected_ids - available_ids
        if missing_ids:
            raise SystemExit(f"Unknown Paper IDs: {', '.join(sorted(missing_ids))}")
        records = [record for record in records if record.paper_id in selected_ids]
    if args.limit is not None:
        records = records[: args.limit]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "input": str(args.input),
                    "selected_papers": len(records),
                    "with_doi": sum(bool(record.doi) for record in records),
                    "pdf_dir": str(args.pdf_dir),
                    "report_dir": str(args.report_dir),
                    "unpaywall_enabled": bool(args.email),
                },
                indent=2,
            )
        )
        return 0

    config = DownloadConfig(
        pdf_dir=args.pdf_dir,
        report_dir=args.report_dir,
        override_csv=args.override_csv,
        unpaywall_email=args.email,
        semantic_scholar_api_key=args.semantic_scholar_api_key,
        timeout_seconds=args.timeout,
        max_file_bytes=args.max_file_mb * 1024 * 1024,
        delay_seconds=args.delay,
        overwrite=args.overwrite,
    )
    summary = download_papers(records, config)
    print(
        json.dumps(
            {
                **asdict(summary),
                "status_path": str(summary.status_path),
                "not_downloaded_path": str(summary.not_downloaded_path),
            },
            indent=2,
        )
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
