"""Document loaders used by ingestion (app.rag.ingestion._load_one)."""
import zipfile

import pytest

from app.rag.ingestion import SUPPORTED_EXTENSIONS, _load_one

_DOCX_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body><w:p><w:r><w:t>Hello from a docx file</w:t></w:r></w:p></w:body></w:document>"
)


def _make_docx(path):
    # Minimal .docx: docx2txt only needs word/document.xml inside the zip.
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", _DOCX_XML)
    return path


def test_docx_is_supported_and_loads(tmp_path):
    assert ".docx" in SUPPORTED_EXTENSIONS
    docs = _load_one(_make_docx(tmp_path / "sample.docx"))
    assert "Hello from a docx file" in docs[0].page_content


@pytest.mark.parametrize("ext", [".txt", ".md"])
def test_text_files_load(tmp_path, ext):
    f = tmp_path / f"note{ext}"
    f.write_text("plain text content", encoding="utf-8")
    assert _load_one(f)[0].page_content == "plain text content"


def test_unsupported_extension_rejected(tmp_path):
    f = tmp_path / "data.xlsx"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        _load_one(f)
