"""Resolve per-function icon files, whether running from the repo checkout
or from an installed Debian package (icons land in
/usr/share/seilio-billing/icons there).
"""
from __future__ import annotations

from pathlib import Path

_REPO_ICONS = Path(__file__).resolve().parent.parent / "resources" / "icons"
_INSTALLED_ICONS = Path("/usr/share/seilio-billing/icons")


def icon_path(name: str) -> Path:
    for base in (_REPO_ICONS, _INSTALLED_ICONS):
        candidate = base / f"{name}.png"
        if candidate.exists():
            return candidate
    return _REPO_ICONS / f"{name}.png"
