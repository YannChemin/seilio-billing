"""Resolve per-function icon files, whether running from the repo checkout,
an installed Debian package (icons land in /usr/share/seilio-billing/icons
there), or a PyInstaller-frozen Windows .exe (icons land next to the
executable under sys._MEIPASS).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ICONS = Path(__file__).resolve().parent.parent / "resources" / "icons"
_INSTALLED_ICONS = Path("/usr/share/seilio-billing/icons")


def _frozen_icons() -> Path | None:
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) / "resources" / "icons" if meipass else None


def icon_path(name: str) -> Path:
    candidates = []
    frozen = _frozen_icons()
    if frozen is not None:
        candidates.append(frozen)
    candidates.append(_REPO_ICONS)
    candidates.append(_INSTALLED_ICONS)
    for base in candidates:
        candidate = base / f"{name}.png"
        if candidate.exists():
            return candidate
    return _REPO_ICONS / f"{name}.png"
