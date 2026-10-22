"""Text extraction from uploaded resumes."""

import io

from docx import Document
from pypdf import PdfReader


class UnsupportedResume(ValueError):
    pass


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf") or data[:4] == b"%PDF":
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if name.endswith(".docx"):
        doc = Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(p for p in parts if p.strip()).strip()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="replace").strip()
    raise UnsupportedResume(f"{filename}: only PDF and DOCX resumes are supported")
