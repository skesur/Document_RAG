import os
import csv
import json
import logging
import unicodedata
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def clean_unicode_text(text: str) -> str:
    """Fast C-level Unicode normalization for text and ligatures."""
    if not text:
        return ""
    return unicodedata.normalize('NFKD', text)


class DocumentParser:
    """
    Ultra-Fast, multi-format document parser.
    Uses PyMuPDF (C engine) for sub-second PDF extraction with pypdf fallback.
    """

    @staticmethod
    def parse_file(file_path: str, file_type: str = None) -> List[Dict[str, Any]]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document file not found at: {file_path}")

        ext = (file_type or path.suffix).lower().lstrip('.')

        if ext == 'pdf':
            return DocumentParser._parse_pdf(path)
        elif ext in ['txt', 'md', 'markdown', 'log', 'py', 'js', 'html', 'css']:
            return DocumentParser._parse_plaintext(path)
        elif ext == 'csv':
            return DocumentParser._parse_csv(path)
        elif ext == 'json':
            return DocumentParser._parse_json(path)
        else:
            return DocumentParser._parse_plaintext(path)

    @staticmethod
    def _parse_pdf(path: Path) -> List[Dict[str, Any]]:
        pages_data = []

        # 1. Ultra-Fast PyMuPDF (0.1s for 500 pages)
        try:
            import pymupdf
            doc = pymupdf.open(str(path))
            for idx, page in enumerate(doc):
                text = page.get_text()
                if text:
                    clean = clean_unicode_text(text).strip()
                    if clean:
                        pages_data.append({
                            "content": clean,
                            "page_number": idx + 1
                        })
            if pages_data:
                return pages_data
        except Exception as e:
            logger.warning(f"PyMuPDF error ({e}), falling back to pypdf.")

        # 2. Fallback to pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            for idx, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    clean = clean_unicode_text(text).strip()
                    if clean:
                        pages_data.append({
                            "content": clean,
                            "page_number": idx + 1
                        })
        except Exception as e:
            logger.error(f"pypdf fallback error on {path}: {e}")
            raise ValueError(f"PDF extraction failure: {str(e)}")

        if not pages_data:
            raise ValueError("No readable text found in the uploaded PDF.")
        return pages_data

    @staticmethod
    def _parse_plaintext(path: Path) -> List[Dict[str, Any]]:
        encodings = ['utf-8', 'latin-1', 'cp1252', 'utf-16']
        content = None
        for enc in encodings:
            try:
                with open(path, 'r', encoding=enc) as f:
                    content = f.read()
                    break
            except (UnicodeDecodeError, UnicodeError):
                continue

        if content is None:
            raise ValueError(f"Unable to decode text file {path.name}.")

        text = clean_unicode_text(content).strip()
        if not text:
            raise ValueError("The uploaded text document is empty.")

        return [{
            "content": text,
            "page_number": 1
        }]

    @staticmethod
    def _parse_csv(path: Path) -> List[Dict[str, Any]]:
        lines = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            for row_idx, row in enumerate(reader):
                line = " | ".join([cell.strip() for cell in row if cell.strip()])
                if line:
                    lines.append(f"Row {row_idx + 1}: {clean_unicode_text(line)}")

        if not lines:
            raise ValueError("The uploaded CSV document contains no readable rows.")

        return [{
            "content": "\n".join(lines),
            "page_number": 1
        }]

    @staticmethod
    def _parse_json(path: Path) -> List[Dict[str, Any]]:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            try:
                data = json.load(f)
                formatted = json.dumps(data, indent=2)
            except Exception:
                f.seek(0)
                formatted = f.read()

        return [{
            "content": clean_unicode_text(formatted),
            "page_number": 1
        }]
