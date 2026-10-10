"""Turn a downloaded document into text the model can read: CSV/TXT/JSON/XML as text, ZIP members one by one,
PDF text when pypdf is available. Used only on documents a model chose to open."""
import io
import zipfile

TEXT_ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def decode(data: bytes) -> str:
    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def to_text(name: str, data: bytes, depth: int = 0) -> str:
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
    return decode(data)
