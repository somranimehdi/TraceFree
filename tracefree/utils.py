from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional


def format_size(size_bytes: int) -> str:
    if size_bytes < 0:
        return "Unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return "Unknown"


def dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0

    for root, dirs, files in os.walk(path, topdown=True):
        dirs[:] = [d for d in dirs if not Path(root, d).is_symlink()]
        for filename in files:
            fpath = Path(root, filename)
            try:
                st = fpath.lstat()
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total


def get_pretty_name(package_name: str) -> str:
    """Return a launcher-friendly app name using desktop metadata when possible."""
    desktop_dirs = [
        Path("/usr/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
    ]

    needle = package_name.lower().strip()
    desktop_name: Optional[str] = None
    for directory in desktop_dirs:
        if not directory.exists():
            continue
        for desktop_path in directory.glob("*.desktop"):
            stem = desktop_path.stem.lower()
            if needle not in stem and needle.split("-", 1)[0] not in stem:
                continue
            try:
                for line in desktop_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("Name="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            desktop_name = value
                            break
            except OSError:
                continue
            if desktop_name:
                break
        if desktop_name:
            break

    if desktop_name:
        cleaned = desktop_name.strip()
        if cleaned:
            return cleaned

    raw = package_name.strip()
    if not raw:
        return "Unknown Application"

    suffixes = (
        "-gtk",
        "-gtk3",
        "-gtk4",
        "-bin",
        "-common",
        "-data",
        "-style",
        "-styles",
    )

    base = raw.lower()
    for suffix in suffixes:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    words = [part for part in base.replace("_", "-").split("-") if part]
    if not words:
        words = [raw]
    pretty = " ".join(word.capitalize() for word in words)
    if not pretty:
        return "Unknown Application"
    return pretty[0].upper() + pretty[1:]
