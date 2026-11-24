# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""CV file ingestion: hashing, MIME/magic validation, size limits, and safe ZIP extraction."""

from __future__ import annotations

import hashlib
import io
import posixpath
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ZIP_FILES = 500
MAX_ZIP_COMPRESSION_RATIO = 100.0

MIME_PDF = "application/pdf"
MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_TXT = "text/plain"
MIME_ZIP = "application/zip"

SUPPORTED_CV_MIMES = frozenset({MIME_PDF, MIME_DOCX, MIME_TXT})

_BINARY_SIGNATURES = (
    b"%PDF-",
    b"PK\x03\x04",
    b"PK\x05\x06",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"MZ",
    b"\x7fELF",
    b"\xd0\xcf\x11\xe0",  # Legacy OLE2 (.doc / .xls)
)


class IngestError(ValueError):
    """Base exception for file ingestion failures."""


class FileTooLargeError(IngestError):
    """Raised when an uploaded or extracted file exceeds the 10 MB limit."""


class UnsupportedFileError(IngestError):
    """Raised when file extension or magic bytes are unsupported or mismatched."""


class ZipBombError(IngestError):
    """Raised when a ZIP archive violates size, count, or compression ratio limits."""


class PathTraversalError(IngestError):
    """Raised when a ZIP entry attempts directory traversal or uses unsafe paths."""


@dataclass(frozen=True, slots=True)
class IngestedFile:
    """Validated CV file ready for text extraction."""

    filename: str
    content: bytes
    sha256: str
    mime_type: str
    size_bytes: int


def compute_sha256(data: bytes) -> str:
    """Compute lowercase hexadecimal SHA-256 digest of raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def _is_valid_docx(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            return "[Content_Types].xml" in names and "word/document.xml" in names
    except zipfile.BadZipFile:
        return False


def _is_valid_plain_text(data: bytes) -> bool:
    if not data or b"\x00" in data:
        return False
    if any(data.startswith(sig) for sig in _BINARY_SIGNATURES):
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            data.decode("cp1252")
            return True
        except UnicodeDecodeError:
            return False


def detect_mime_type(data: bytes, filename: str) -> str:
    """Validate file extension against magic bytes and return canonical MIME type."""
    ext = PurePosixPath(filename.replace("\\", "/")).suffix.lower()

    if ext == ".pdf":
        if data[:1024].lstrip().startswith(b"%PDF-"):
            return MIME_PDF
        raise UnsupportedFileError(f"File '{filename}' has .pdf extension but invalid PDF magic.")

    if ext == ".docx":
        if _is_valid_docx(data):
            return MIME_DOCX
        raise UnsupportedFileError(f"File '{filename}' has .docx extension but invalid DOCX data.")

    if ext == ".txt":
        if _is_valid_plain_text(data):
            return MIME_TXT
        raise UnsupportedFileError(f"File '{filename}' has .txt extension but is not valid text.")

    if ext == ".zip":
        if data.startswith((b"PK\x03\x04", b"PK\x05\x06")) and zipfile.is_zipfile(io.BytesIO(data)):
            return MIME_ZIP
        raise UnsupportedFileError(f"File '{filename}' has .zip extension but invalid ZIP magic.")

    raise UnsupportedFileError(f"Unsupported file extension '{ext}' for '{filename}'.")


def _validate_zip_member_path(member_name: str) -> str:
    """Reject absolute paths, drive letters, and '..' traversal segments."""
    normalized = member_name.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[1] == ":")
    ):
        raise PathTraversalError(f"Unsafe absolute path in ZIP: '{member_name}'.")

    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        raise PathTraversalError(f"Path traversal detected in ZIP entry: '{member_name}'.")

    clean = posixpath.normpath(normalized)
    if clean.startswith("..") or clean.startswith("/"):
        raise PathTraversalError(f"Unsafe normalized path in ZIP: '{member_name}'.")
    return clean


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _should_skip_zip_entry(clean_path: str) -> bool:
    name = PurePosixPath(clean_path).name
    parts = PurePosixPath(clean_path).parts
    return "__MACOSX" in parts or name.startswith(".") or name == "Thumbs.db"


def extract_safe_zip(
    data: bytes,
    *,
    max_uncompressed_bytes: int = MAX_ZIP_UNCOMPRESSED_BYTES,
    max_files: int = MAX_ZIP_FILES,
    max_ratio: float = MAX_ZIP_COMPRESSION_RATIO,
    max_single_file_bytes: int = MAX_FILE_SIZE_BYTES,
) -> list[IngestedFile]:
    """Safely extract supported CV files from a ZIP archive with zip-bomb guards."""
    results: list[IngestedFile] = []
    total_uncompressed = 0
    entry_count = 0

    try:
        zf_ctx = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsupportedFileError("Invalid or corrupted ZIP archive.") from exc

    with zf_ctx as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue

            clean_path = _validate_zip_member_path(info.filename)
            if _is_symlink(info):
                raise PathTraversalError(f"Symlink entry rejected in ZIP: '{info.filename}'.")

            if _should_skip_zip_entry(clean_path):
                continue

            entry_count += 1
            if entry_count > max_files:
                raise ZipBombError(f"ZIP exceeds maximum file count ({max_files}).")

            if info.file_size > max_single_file_bytes:
                raise FileTooLargeError(
                    f"ZIP entry '{clean_path}' exceeds {max_single_file_bytes} bytes."
                )

            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_ratio:
                    raise ZipBombError(
                        f"ZIP entry '{clean_path}' ratio {ratio:.1f} exceeds {max_ratio}."
                    )
            elif info.file_size > 0:
                raise ZipBombError(
                    f"ZIP entry '{clean_path}' has non-zero size with zero compressed size."
                )

            total_uncompressed += info.file_size
            if total_uncompressed > max_uncompressed_bytes:
                raise ZipBombError(
                    f"ZIP total uncompressed size exceeds {max_uncompressed_bytes} bytes."
                )

            # Read bounded bytes to guard against spoofed ZipInfo headers.
            with zf.open(info, "r") as member_stream:
                content = member_stream.read(max_single_file_bytes + 1)

            if len(content) > max_single_file_bytes:
                raise FileTooLargeError(
                    f"ZIP entry '{clean_path}' actual size exceeds {max_single_file_bytes} bytes."
                )

            leaf_name = PurePosixPath(clean_path).name
            mime_type = detect_mime_type(content, leaf_name)
            if mime_type not in SUPPORTED_CV_MIMES:
                raise UnsupportedFileError(
                    f"Nested archive or unsupported file '{clean_path}' inside ZIP."
                )

            results.append(
                IngestedFile(
                    filename=leaf_name,
                    content=content,
                    sha256=compute_sha256(content),
                    mime_type=mime_type,
                    size_bytes=len(content),
                )
            )

    return results


def ingest_file(
    data: bytes,
    filename: str,
    *,
    max_file_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> list[IngestedFile]:
    """Validate and ingest a single uploaded file (PDF, DOCX, TXT, or ZIP)."""
    if len(data) == 0:
        raise UnsupportedFileError(f"File '{filename}' is empty.")

    if len(data) > max_file_size_bytes:
        raise FileTooLargeError(
            f"File '{filename}' ({len(data)} bytes) exceeds limit of {max_file_size_bytes} bytes."
        )

    mime_type = detect_mime_type(data, filename)
    if mime_type == MIME_ZIP:
        return extract_safe_zip(data, max_single_file_bytes=max_file_size_bytes)

    return [
        IngestedFile(
            filename=PurePosixPath(filename.replace("\\", "/")).name,
            content=data,
            sha256=compute_sha256(data),
            mime_type=mime_type,
            size_bytes=len(data),
        )
    ]
