from pathlib import Path

import pytest

from src.data.documents import discover_documents, read_document


def test_discovers_mineru_text_and_reads_it(tmp_path: Path) -> None:
    paper = tmp_path / "paper.md"
    paper.write_text("# Study\n\nA eats B.", encoding="utf-8")
    (tmp_path / "ignore.pdf").write_bytes(b"%PDF-1.7")

    assert discover_documents([tmp_path]) == [paper.resolve()]
    assert "A eats B" in read_document(paper).text


def test_pdf_input_is_rejected(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    with pytest.raises(ValueError, match="Unsupported document format"):
        discover_documents([pdf])
