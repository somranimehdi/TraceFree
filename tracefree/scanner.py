from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .models import GhostMatch
from .utils import dir_size_bytes


def ghost_scan_roots() -> List[Path]:
    home = Path.home()
    return [
        home / ".config",
        home / ".local" / "share",
        home / ".cache",
        Path("/var/lib/flatpak/app"),
    ]


def package_match_tokens(package_name: str) -> List[str]:
    raw = package_name.lower().strip()
    tokens = {raw}
    normalized = raw.replace(".", "").replace("-", "").replace("_", "")
    if normalized:
        tokens.add(normalized)
    for chunk in raw.replace("_", "-").split("-"):
        if len(chunk) >= 4:
            tokens.add(chunk)
    return sorted(t for t in tokens if t)


def path_matches_tokens(path: str, tokens: Sequence[str]) -> bool:
    p = path.lower()
    compact = p.replace(".", "").replace("-", "").replace("_", "")
    for token in tokens:
        if token in p or token in compact:
            return True
    return False


def scan_ghost_files(package_name: str) -> Tuple[List[GhostMatch], int]:
    matches: List[GhostMatch] = []
    tokens = package_match_tokens(package_name)

    for root in ghost_scan_roots():
        if not root.exists():
            continue
        for walk_root, dirs, files in os.walk(root, topdown=True):
            current = Path(walk_root)
            dirs[:] = [d for d in dirs if not Path(current, d).is_symlink()]

            if path_matches_tokens(str(current), tokens):
                size = dir_size_bytes(current)
                matches.append(GhostMatch(str(current), size, str(current).startswith("/var/lib/")))
                dirs[:] = []
                continue

            for fname in files:
                fpath = current / fname
                if not path_matches_tokens(str(fpath), tokens):
                    continue
                try:
                    st = fpath.lstat()
                except OSError:
                    continue
                if not fpath.is_file():
                    continue
                matches.append(GhostMatch(str(fpath), st.st_size, str(fpath).startswith("/var/lib/")))

    dedup: Dict[str, GhostMatch] = {}
    for match in matches:
        current = dedup.get(match.path)
        if current is None or match.size_bytes > current.size_bytes:
            dedup[match.path] = match

    final = sorted(dedup.values(), key=lambda x: x.path)
    total = sum(m.size_bytes for m in final)
    return final, total
