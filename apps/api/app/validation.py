"""Shared request validation helpers."""

from __future__ import annotations

import re

# project_id is a soft-isolation key (no existence check); we only guard the
# format so it stays a safe filesystem path segment and metadata value.
_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_valid_project_id(project_id: str) -> bool:
    return bool(_PROJECT_ID_RE.match(project_id))
