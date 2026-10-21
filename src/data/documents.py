"""Read MinerU-produced Markdown or plain text for LLM extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".txt"}


@dataclass(frozen=True)
class TextDocument:
    """A text document supplied to the extraction model."""

    path: Path
    text: str


def discover_documents(paths: list[Path], *, recursive: bool = False) -> list[Path]:
    """Expand files/directories into a stable, deduplicated Markdown/text list."""
    discovered: set[Path] = set()
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_file():
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                raise ValueError(f"Unsupported document format: {path}")
            discovered.add(path)
            continue
        iterator = path.rglob("*") if recursive else path.glob("*")
        discovered.update(
            candidate.resolve()
            for candidate in iterator
            if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES
        )
    return sorted(discovered)


def read_document(path: Path) -> TextDocument:
    """Read a complete MinerU Markdown or text document without truncation."""
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported document format: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"No text found in {path}")
    return TextDocument(path=path, text=text)
