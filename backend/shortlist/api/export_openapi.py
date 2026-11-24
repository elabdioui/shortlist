# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Export FastAPI OpenAPI schema to docs/openapi.json."""

import json
from pathlib import Path

from shortlist.api.app import app


def export_openapi(output_path: Path) -> None:
    """Write the OpenAPI 3.1 schema JSON to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parents[3]
    export_openapi(repo_root / "docs" / "openapi.json")
