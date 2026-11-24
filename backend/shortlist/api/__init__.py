# Copyright (C) 2026 Shortlist Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""FastAPI REST & SSE server for Shortlist."""

from shortlist.api.app import app, create_app

__all__ = ["app", "create_app"]
