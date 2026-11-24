# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""CV file ingestion package."""

from shortlist.core.ingest.ingestor import (
    MAX_FILE_SIZE_BYTES,
    MAX_ZIP_COMPRESSION_RATIO,
    MAX_ZIP_FILES,
    MAX_ZIP_UNCOMPRESSED_BYTES,
    MIME_DOCX,
    MIME_PDF,
    MIME_TXT,
    MIME_ZIP,
    FileTooLargeError,
    IngestedFile,
    IngestError,
    PathTraversalError,
    UnsupportedFileError,
    ZipBombError,
    compute_sha256,
    detect_mime_type,
    extract_safe_zip,
    ingest_file,
)

__all__ = [
    "MAX_FILE_SIZE_BYTES",
    "MAX_ZIP_COMPRESSION_RATIO",
    "MAX_ZIP_FILES",
    "MAX_ZIP_UNCOMPRESSED_BYTES",
    "MIME_DOCX",
    "MIME_PDF",
    "MIME_TXT",
    "MIME_ZIP",
    "FileTooLargeError",
    "IngestError",
    "IngestedFile",
    "PathTraversalError",
    "UnsupportedFileError",
    "ZipBombError",
    "compute_sha256",
    "detect_mime_type",
    "extract_safe_zip",
    "ingest_file",
]
