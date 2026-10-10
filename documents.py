"""Turn a downloaded document into text the model can read: HTML/CSV/TXT/JSON/XML as text, ZIP members one by one,
PDF text when pypdf is available. Used only on documents a model chose to open."""
import io
import re
import zipfile
from html.parser import HTMLParser

TEXT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


class _HTMLText(HTMLParser):
    """Small dependency-free HTML reader that keeps paragraphs and table rows useful to the model."""

    BLOCKS = {"address", "article", "aside", "blockquote", "div", "dl", "dt", "dd", "fieldset", "figcaption",
              "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main",
              "nav", "ol", "p", "pre", "section", "table", "tr", "ul"}
    HIDDEN = {"script", "style", "template", "noscript", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.HIDDEN:
            self.hidden += 1
            return
        if self.hidden:
            return
        if tag in self.BLOCKS or tag == "br":
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        if tag == "img":
            alt = next((value for key, value in attrs if key.lower() in ("alt", "aria-label") and value), None)
            if alt:
                self.parts.append(f"[image: {alt}]")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.HIDDEN:
            self.hidden = max(0, self.hidden - 1)
            return
        if self.hidden:
            return
        if tag in ("td", "th"):
            self.parts.append("\t")
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)

    def text(self) -> str:
        lines = []
        for line in "".join(self.parts).replace("\r", "").split("\n"):
            line = re.sub(r"[^\S\t]+", " ", line).strip(" \t")
            line = re.sub(r"\t+", "\t", line)
            if line:
                lines.append(line)
        return "\n".join(lines)


def decode(data: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def html_to_text(data: bytes) -> str:
    parser = _HTMLText()
    parser.feed(decode(data))
    parser.close()
    return parser.text()


def to_text(name: str, data: bytes, depth: int = 0, content_type: str = "") -> str:
    lower = name.lower()
    if data[:2] == b"PK" or lower.endswith(".zip"):
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            return decode(data)
        parts = [f"ZIP with {len(archive.namelist())} files: {', '.join(archive.namelist())}"]
        for member in archive.namelist():
            if member.endswith("/") or depth > 2:
                continue
            parts.append(f"\n--- {member} ---\n" + to_text(member, archive.read(member), depth + 1))
        return "\n".join(parts)
    if data[:4] == b"%PDF" or lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
        except Exception as error:  # pypdf missing or unreadable PDF
            return f"[PDF could not be read as text: {error}]"
    head = data[:512].lstrip().lower()
    if "html" in content_type.lower() or lower.endswith((".html", ".htm")) \
            or head.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return html_to_text(data)
    return decode(data)
