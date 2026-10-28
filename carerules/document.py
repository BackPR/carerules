"""Read an uploaded handbook (PDF, Word .docx, or plain text) into numbered pages for auditing and quote checking.
PDF pages are the PDF's own pages; Word and text files are split into pages of about 3,000 characters."""
from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_CHARS = 240_000  # about 60k tokens; longer handbooks are cut here


def _chunk(text: str, size: int = 3000) -> list[tuple[int, str]]:
    paras, pages, cur = re.split(r"\n\s*\n", text), [], ""
    for para in paras:
        if cur and len(cur) + len(para) > size:
            pages.append(cur)
            cur = ""
        cur += para.strip() + "\n\n"
    if cur.strip():
        pages.append(cur)
    return [(i + 1, t) for i, t in enumerate(pages)]


def _pdf(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader  # on the Space
        return [(i + 1, page.extract_text() or "") for i, page in enumerate(PdfReader(str(path)).pages)]
    except ImportError:
        exe = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
        out = subprocess.run([exe, "-enc", "UTF-8", str(path), "-"], capture_output=True, text=True, check=True).stdout
        return [(i + 1, t) for i, t in enumerate(out.split("\f")) if t.strip()]


def _docx(path: Path) -> list[tuple[int, str]]:
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    paras = ["".join(t.text or "" for t in p.iter(f"{ns}t")) for p in root.iter(f"{ns}p")]
    return _chunk("\n\n".join(p for p in paras if p.strip()))


def read(path: str | Path) -> list[tuple[int, str]]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        pages = _pdf(path)
    elif ext == ".docx":
        pages = _docx(path)
    elif ext in (".txt", ".md"):
        pages = _chunk(path.read_text(errors="replace"))
    else:
        raise ValueError("Upload a PDF, Word (.docx) or text file.")
    out, total = [], 0
    for number, text in pages:
        if total >= MAX_CHARS:
            break
        text = text[: MAX_CHARS - total]
        total += len(text)
        out.append((number, text))
    if sum(len(t.split()) for _, t in out) < 150:
        raise ValueError("Couldn't read enough text from this file. If it's a scanned PDF, upload the Word version.")
    return out
