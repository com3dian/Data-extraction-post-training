import csv
from pathlib import Path

import httpx

from src.data.download import (
    DownloadConfig,
    PaperRecord,
    download_papers,
    is_pdf,
    read_paper_records,
)


def _write_inventory(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Paper ID",
                "Reference DOI",
                "Link to paper",
                "Used",
                "Full Reference (APA)",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Paper ID": "1",
                "Reference DOI": "NA",
                "Link to paper": "https://example.test/good",
                "Used": "y",
                "Full Reference (APA)": "Good paper",
            }
        )
        writer.writerow(
            {
                "Paper ID": "2",
                "Reference DOI": "NA",
                "Link to paper": "https://example.test/login",
                "Used": "y",
                "Full Reference (APA)": "Unavailable paper",
            }
        )


def test_downloads_pdf_and_reports_non_pdf(tmp_path: Path) -> None:
    inventory = tmp_path / "papers.csv"
    _write_inventory(inventory)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/good":
            return httpx.Response(
                200, content=b"%PDF-1.7\nvalid", headers={"content-type": "application/pdf"}
            )
        return httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"})

    config = DownloadConfig(
        pdf_dir=tmp_path / "pdfs",
        report_dir=tmp_path / "reports",
        delay_seconds=0,
    )
    summary = download_papers(
        read_paper_records(inventory),
        config,
        transport=httpx.MockTransport(handler),
    )

    assert summary.downloaded == 1
    assert summary.failed == 1
    assert is_pdf(config.pdf_dir / "paper_1.pdf")
    with summary.not_downloaded_path.open(encoding="utf-8", newline="") as handle:
        failures = list(csv.DictReader(handle))
    assert [row["paper_id"] for row in failures] == ["2"]
    assert "not a PDF" in failures[0]["attempted_urls"]


def test_existing_valid_pdf_is_resumed(tmp_path: Path) -> None:
    inventory = tmp_path / "papers.csv"
    _write_inventory(inventory)
    records = read_paper_records(inventory, limit=1)
    config = DownloadConfig(
        pdf_dir=tmp_path / "pdfs",
        report_dir=tmp_path / "reports",
        delay_seconds=0,
    )
    config.pdf_dir.mkdir()
    (config.pdf_dir / "paper_1.pdf").write_bytes(b"%PDF-1.7\nexisting")

    summary = download_papers(records, config)

    assert summary.already_downloaded == 1
    assert summary.failed == 0


def test_openalex_repository_redirect_resolves_public_figshare_pdf(tmp_path: Path) -> None:
    paper_title = "Climate Change Strengthens Selection for Mast Seeding in European Beech"
    record = PaperRecord(
        paper_id="5",
        doi="10.1016/j.cub.2020.06.056",
        source_link="",
        citation=(
            "Bogdziewicz (2020). Climate Change Strengthens Selection "
            "for Mast Seeding in European Beech."
        ),
        used="y",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.openalex.org" in url:
            return httpx.Response(
                200,
                json={
                    "doi": "https://doi.org/10.1016/j.cub.2020.06.056",
                    "locations": [
                        {
                            "source": {"type": "repository"},
                            "pdf_url": "https://e-space.example.test/629194/paper.pdf",
                        }
                    ],
                },
            )
        if "api.crossref.org" in url:
            return httpx.Response(404)
        if "api.semanticscholar.org" in url:
            return httpx.Response(429)
        if "e-space.example.test" in url:
            return httpx.Response(
                302,
                headers={
                    "location": "https://repository.example.test/articles/journal_contribution/Climate_Change/32464773"
                },
            )
        if "repository.example.test" in url:
            return httpx.Response(202, headers={"content-type": "text/html"})
        if "api.figshare.com" in url:
            return httpx.Response(
                200,
                json={
                    "title": paper_title,
                    "files": [
                        {
                            "name": "paper.pdf",
                            "download_url": "https://ndownloader.figshare.com/files/65033877",
                        }
                    ],
                },
            )
        if "ndownloader.figshare.com" in url:
            return httpx.Response(
                200,
                content=b"%PDF-1.7\nrepository copy",
                headers={"content-type": "application/pdf"},
            )
        raise AssertionError(f"Unexpected request: {url}")

    config = DownloadConfig(
        pdf_dir=tmp_path / "pdfs", report_dir=tmp_path / "reports", delay_seconds=0
    )
    summary = download_papers([record], config, transport=httpx.MockTransport(handler))

    assert summary.downloaded == 1
    assert is_pdf(config.pdf_dir / "paper_5.pdf")
    with summary.status_path.open(encoding="utf-8", newline="") as handle:
        status = next(csv.DictReader(handle))
    assert status["download_source"] == "figshare"

    resumed = download_papers([record], config, transport=httpx.MockTransport(handler))
    assert resumed.already_downloaded == 1
    with resumed.status_path.open(encoding="utf-8", newline="") as handle:
        resumed_status = next(csv.DictReader(handle))
    assert resumed_status["download_source"] == "figshare"
    assert resumed_status["download_url"].endswith("/65033877")


def test_verified_url_downloads_when_metadata_services_have_no_pdf(tmp_path: Path) -> None:
    override_csv = tmp_path / "overrides.csv"
    with override_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Paper ID", "Reference DOI", "PDF URL"])
        writer.writerow(["17", "10.1007/s10342-011-0536-y", "https://author.test/paper.pdf"])

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://author.test/paper.pdf"
        return httpx.Response(200, content=b"%PDF-1.7\nauthor copy")

    record = PaperRecord(
        paper_id="17",
        doi="10.1007/s10342-011-0536-y",
        source_link="",
        citation="Effects of seed quality and seed location",
        used="y",
    )
    config = DownloadConfig(
        pdf_dir=tmp_path / "pdfs",
        report_dir=tmp_path / "reports",
        override_csv=override_csv,
        delay_seconds=0,
    )
    summary = download_papers([record], config, transport=httpx.MockTransport(handler))

    assert summary.downloaded == 1
    with summary.status_path.open(encoding="utf-8", newline="") as handle:
        status = next(csv.DictReader(handle))
    assert status["download_source"] == "verified_url"
