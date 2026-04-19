from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .models import GhostMatch


def build_cleanup_commands(
    app_name: str,
    source: str,
    app_id: Optional[str],
    ghost_matches: Sequence[GhostMatch],
) -> List[str]:
    lines: List[str] = []
    if source in ("Apt", "DEB", "Local DEB"):
        target = app_id or app_name
        lines.append(f"apt-get purge -y {shlex.quote(target)}")
        lines.append("apt-get autoremove -y")
    elif source == "Snap":
        target = app_id or app_name
        lines.append(f"snap remove {shlex.quote(target)}")
    elif source == "Flatpak":
        target = app_id or app_name
        lines.append(f"flatpak uninstall -y --delete-data {shlex.quote(target)}")

    for match in ghost_matches:
        if match.requires_root:
            lines.append(f"rm -rf -- {shlex.quote(match.path)}")
    return lines


def run_pkexec_script(script_text: str) -> Tuple[int, str, str]:
    with tempfile.NamedTemporaryFile("w", delete=False, prefix="tracefree_", suffix=".sh") as tmp:
        tmp.write(script_text)
        tmp_path = tmp.name
    os.chmod(tmp_path, 0o700)
    try:
        proc = subprocess.run(["pkexec", "/bin/bash", tmp_path], capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def delete_unprivileged_paths(ghost_matches: Sequence[GhostMatch]) -> List[str]:
    deleted: List[str] = []
    for match in ghost_matches:
        if match.requires_root:
            continue
        path = Path(match.path)
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            elif path.exists() or path.is_symlink():
                path.unlink()
            else:
                continue
            deleted.append(match.path)
        except OSError:
            continue
    return deleted
