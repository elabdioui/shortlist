# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for CV file ingestion, MIME validation, size limits, and safe ZIP extraction."""

from __future__ import annotations

import io
import zipfile

import pytest

from shortlist.core.ingest import (
    MIME_DOCX,
    MIME_PDF,
    MIME_TXT,
    FileTooLargeError,
    PathTraversalError,
    UnsupportedFileError,
    ZipBombError,
    compute_sha256,
    extract_safe_zip,
    ingest_file,
)


def _make_minimal_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"


def _make_minimal_docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types></Types>")
        zf.writestr("word/document.xml", "<w:document></w:document>")
    return buf.getvalue()


def test_ingest_valid_pdf_docx_txt() -> None:
    pdf = _make_minimal_pdf_bytes()
    res_pdf = ingest_file(pdf, "candidate.pdf")
    assert len(res_pdf) == 1
    assert res_pdf[0].mime_type == MIME_PDF
    assert res_pdf[0].sha256 == compute_sha256(pdf)

    docx = _make_minimal_docx_bytes()
    res_docx = ingest_file(docx, "candidate.docx")
    assert len(res_docx) == 1
    assert res_docx[0].mime_type == MIME_DOCX

    txt = b"Experience: 5 years in supply chain."
    res_txt = ingest_file(txt, "candidate.txt")
    assert len(res_txt) == 1
    assert res_txt[0].mime_type == MIME_TXT


def test_ingest_rejects_empty_and_oversized() -> None:
    with pytest.raises(UnsupportedFileError):
        ingest_file(b"", "empty.pdf")

    with pytest.raises(FileTooLargeError):
        ingest_file(b"%PDF-" + b"a" * 1024, "big.pdf", max_file_size_bytes=512)


def test_ingest_rejects_spoofed_magic_and_unsupported_ext() -> None:
    # PNG bytes renamed to .pdf
    with pytest.raises(UnsupportedFileError):
        ingest_file(b"\x89PNG\r\n\x1a\nfake", "not_a_pdf.pdf")

    # PE executable disguised as .txt
    with pytest.raises(UnsupportedFileError):
        ingest_file(b"MZ\x90\x00binary", "malware.txt")

    # Invalid DOCX (plain zip without word/document.xml)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "world")
    with pytest.raises(UnsupportedFileError):
        ingest_file(buf.getvalue(), "fake.docx")

    # Unsupported extension
    with pytest.raises(UnsupportedFileError):
        ingest_file(b"hello", "photo.jpg")


def test_safe_zip_extracts_supported_cvs_and_skips_macos_junk() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("cv1.pdf", _make_minimal_pdf_bytes())
        zf.writestr("nested/cv2.txt", b"Supply chain manager")
        zf.writestr("__MACOSX/._cv1.pdf", b"junk")
        zf.writestr(".DS_Store", b"junk")

    items = ingest_file(buf.getvalue(), "batch.zip")
    assert [i.filename for i in items] == ["cv1.pdf", "cv2.txt"]
    assert items[0].mime_type == MIME_PDF
    assert items[1].mime_type == MIME_TXT


def test_zip_rejects_path_traversal_and_symlinks() -> None:
    for bad_name in ("../evil.txt", "/etc/passwd", "C:\\Windows\\evil.txt"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(bad_name, b"evil")
        with pytest.raises(PathTraversalError):
            extract_safe_zip(buf.getvalue())

    # Symlink entry
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("link.txt")
        info.create_system = 3  # Unix
        info.external_attr = (0o120777) << 16
        zf.writestr(info, b"/etc/passwd")
    with pytest.raises(PathTraversalError):
        extract_safe_zip(buf.getvalue())


def test_zip_bomb_guards() -> None:
    # High compression ratio
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.txt", b"A" * 200_000)
    with pytest.raises(ZipBombError, match="ratio"):
        extract_safe_zip(buf.getvalue(), max_ratio=10.0)

    # Max file count
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        for i in range(5):
            zf.writestr(f"cv_{i}.txt", f"Candidate {i}".encode())
    with pytest.raises(ZipBombError, match="file count"):
        extract_safe_zip(buf2.getvalue(), max_files=3)

    # Max total uncompressed size
    buf3 = io.BytesIO()
    with zipfile.ZipFile(buf3, "w") as zf:
        zf.writestr("a.txt", b"x" * 600)
        zf.writestr("b.txt", b"y" * 600)
    with pytest.raises(ZipBombError, match="total uncompressed"):
        extract_safe_zip(buf3.getvalue(), max_uncompressed_bytes=1000)
