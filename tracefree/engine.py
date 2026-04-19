from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .models import AppGroup, AppRecord
from .utils import dir_size_bytes, get_pretty_name


class MultiSourceEngine:
    SNAP_RUNTIME_BLACKLIST = {
        "core",
        "bare",
        "gtk-common-themes",
        "gnome-3-38",
        "snapd",
    }

    def __init__(self) -> None:
        self._desktop_index: Optional[List[Dict[str, str]]] = None
        self._grouped_cache: Dict[str, AppGroup] = {}

    def _desktop_dirs(self) -> List[Path]:
        return [
            Path("/usr/share/applications"),
            Path("/var/lib/snapd/desktop/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
        ]

    def _desktop_entries(self) -> List[Dict[str, str]]:
        if self._desktop_index is not None:
            return self._desktop_index

        entries: List[Dict[str, str]] = []
        for root in self._desktop_dirs():
            if not root.exists():
                continue
            for desktop_path in root.glob("*.desktop"):
                name = ""
                icon = ""
                exec_cmd = ""
                try:
                    for line in desktop_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.startswith("Name=") and not name:
                            name = line.split("=", 1)[1].strip()
                        elif line.startswith("Icon=") and not icon:
                            icon = line.split("=", 1)[1].strip()
                        elif line.startswith("Exec=") and not exec_cmd:
                            exec_cmd = line.split("=", 1)[1].strip()
                except OSError:
                    continue

                entries.append(
                    {
                        "path": str(desktop_path),
                        "stem": desktop_path.stem,
                        "name": name,
                        "icon": icon,
                        "exec": exec_cmd,
                    }
                )

        self._desktop_index = entries
        return entries

    def _find_desktop_for_id(self, app_id: str) -> Optional[Dict[str, str]]:
        needle = app_id.lower()
        for entry in self._desktop_entries():
            stem = entry.get("stem", "").lower()
            name = entry.get("name", "").lower()
            if needle in stem or needle in name:
                return entry
        return None

    @staticmethod
    def _sanitize_group_key(name: str) -> str:
        return "".join(ch for ch in name.lower() if ch.isalnum())

    @staticmethod
    def _apt_parent_name(package_name: str) -> str:
        return package_name.split("-", 1)[0]

    def _is_local_deb(self, pkg: object) -> bool:
        installed = getattr(pkg, "installed", None)
        if installed is None:
            return False
        origins = getattr(installed, "origins", None)
        if not origins:
            return True
        for origin in origins:
            archive = str(getattr(origin, "archive", "") or "").strip()
            site = str(getattr(origin, "site", "") or "").strip()
            origin_name = str(getattr(origin, "origin", "") or "").strip()
            if archive or site or origin_name:
                return False
        return True

    def _is_noise_package(self, package_name: str) -> bool:
        name = package_name.lower()
        if name.startswith("fonts-") or name.startswith("ttf-"):
            return True
        if "-l10n-" in name or "-langpack-" in name or "-i18n-" in name:
            return True
        return False

    def _is_technical_subpackage(self, package_name: str) -> bool:
        markers = (
            "-common",
            "-data",
            "-style",
            "-styles",
            "-dev",
            "-dbg",
            "-dbgsym",
            "-doc",
            "-headers",
            "-headless",
            "-tests",
            "-examples",
            "-locale",
            "-locales",
            "-l10n",
            "-langpack",
            "-i18n",
        )
        lower = package_name.lower()
        return any(marker in lower for marker in markers)

    def _source_by_mount(self, record: AppRecord) -> str:
        app_id = (record.app_id or record.name).lower()
        if Path(f"/snap/{app_id}").exists() or Path(f"/snap/bin/{app_id}").exists():
            return "Snap"
        if Path(f"/var/lib/flatpak/app/{app_id}").exists():
            return "Flatpak"
        if record.source in ("Apt", "DEB"):
            return record.source
        return record.source

    def _is_user_facing(self, record: AppRecord) -> bool:
        app_id = (record.app_id or record.name).lower()
        source = self._source_by_mount(record)

        if source == "Snap":
            direct_bin = Path(f"/snap/bin/{app_id}")
            direct_desktop = Path(f"/var/lib/snapd/desktop/applications/{app_id}_{app_id}.desktop")
            if direct_bin.exists() or direct_desktop.exists():
                return True
            return self._find_desktop_for_id(app_id) is not None

        if source == "Flatpak":
            flatpak_desktop = Path(f"/var/lib/flatpak/exports/share/applications/{app_id}.desktop")
            if flatpak_desktop.exists() or Path(f"/var/lib/flatpak/app/{app_id}").exists():
                return True
            return self._find_desktop_for_id(app_id) is not None

        if self._find_desktop_for_id(app_id) is not None:
            return True
        binary = Path(f"/usr/bin/{app_id}")
        return binary.exists() and os.access(binary, os.X_OK)

    def _category_for(self, record: AppRecord) -> str:
        pkg = (record.app_id or record.name).lower()
        if record.source == "Snap" and pkg in self.SNAP_RUNTIME_BLACKLIST:
            return "System Components"
        if self._is_noise_package(pkg):
            return "System Components"
        if pkg.startswith(("python3-", "lib", "xserver-")) and not self._is_user_facing(record):
            return "System Components"
        if self._is_technical_subpackage(pkg):
            return "System Components"
        return "User Applications" if self._is_user_facing(record) else "System Components"

    def _display_name_for(self, record: AppRecord) -> str:
        app_id = record.app_id or record.name
        if record.source in ("Apt", "DEB"):
            return get_pretty_name(self._apt_parent_name(app_id))
        return get_pretty_name(app_id)

    def list_apt_packages(self) -> List[AppRecord]:
        records: List[AppRecord] = []
        try:
            import apt  # type: ignore
        except Exception:
            return records

        cache = apt.Cache()
        for pkg in cache:
            if not pkg.is_installed:
                continue

            size_bytes = -1
            try:
                installed = pkg.installed
                if installed is not None:
                    size_bytes = int(installed.installed_size)
            except Exception:
                pass

            records.append(
                AppRecord(
                    icon="APT",
                    name=pkg.name,
                    source="DEB" if self._is_local_deb(pkg) else "Apt",
                    disk_space_bytes=size_bytes,
                    app_id=pkg.name,
                )
            )
        return records

    def _snap_name_from_desktop(self, stem: str) -> Optional[str]:
        lowered = stem.lower()
        if lowered.startswith("snap."):
            parts = lowered.split(".")
            if len(parts) >= 2 and parts[1]:
                return parts[1]
        if "_" in lowered:
            return lowered.split("_", 1)[0]
        if lowered:
            return lowered
        return None

    def _snap_desktop_fallback(self, seen: Set[str]) -> List[AppRecord]:
        records: List[AppRecord] = []
        desktop_dir = Path("/var/lib/snapd/desktop/applications")
        if not desktop_dir.exists():
            return records

        for desktop_file in desktop_dir.glob("*.desktop"):
            snap_name = self._snap_name_from_desktop(desktop_file.stem)
            if not snap_name or snap_name in seen:
                continue
            if snap_name in self.SNAP_RUNTIME_BLACKLIST:
                continue

            snap_mount = Path(f"/snap/{snap_name}")
            records.append(
                AppRecord(
                    icon="SNP",
                    name=snap_name,
                    source="Snap",
                    disk_space_bytes=dir_size_bytes(snap_mount) if snap_mount.exists() else -1,
                    app_id=snap_name,
                )
            )
            seen.add(snap_name)

        return records

    def list_snap_packages(self) -> List[AppRecord]:
        records: List[AppRecord] = []
        seen: Set[str] = set()
        cmd = ["snap", "list", "--json"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                payload = json.loads(proc.stdout)
                snaps = payload if isinstance(payload, list) else payload.get("snaps", [])
                for entry in snaps:
                    if not isinstance(entry, dict):
                        continue
                    name = str(entry.get("name", "")).strip().lower()
                    if not name or name in self.SNAP_RUNTIME_BLACKLIST:
                        continue
                    if name in seen:
                        continue
                    seen.add(name)

                    size_raw = entry.get("installed-size", -1)
                    try:
                        size_bytes = int(size_raw)
                    except (TypeError, ValueError):
                        size_bytes = -1

                    records.append(
                        AppRecord(
                            icon="SNP",
                            name=name,
                            source="Snap",
                            disk_space_bytes=size_bytes,
                            app_id=name,
                        )
                    )
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        records.extend(self._snap_desktop_fallback(seen))
        return records

    def list_flatpak_packages(self) -> List[AppRecord]:
        records: List[AppRecord] = []
        cmd = ["flatpak", "list", "--columns=application,name,origin"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return records

        if proc.returncode != 0 or not proc.stdout.strip():
            return records

        for line in [line for line in proc.stdout.splitlines() if line.strip()]:
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if len(parts) < 2:
                parts = [p.strip() for p in line.split() if p.strip()]
            if len(parts) < 2:
                continue
            app_id = parts[0]
            flatpak_dir = Path("/var/lib/flatpak/app") / app_id
            records.append(
                AppRecord(
                    icon="FLP",
                    name=parts[1],
                    source="Flatpak",
                    disk_space_bytes=dir_size_bytes(flatpak_dir),
                    app_id=app_id,
                )
            )
        return records

    def get_all(self) -> Dict[str, AppGroup]:
        all_records = self.list_apt_packages() + self.list_snap_packages() + self.list_flatpak_packages()
        grouped: Dict[str, AppGroup] = {}
        for record in all_records:
            record.source = self._source_by_mount(record)
            record.category = self._category_for(record)
            pretty_name = self._display_name_for(record)
            key = self._sanitize_group_key(pretty_name)

            group = grouped.get(key)
            if group is None:
                group = AppGroup(
                    key=key,
                    pretty_name=pretty_name,
                    source=record.source,
                    category=record.category,
                )
                grouped[key] = group

            group.add_package(record)
            if group.source != record.source:
                group.source = "Mixed"
            if group.category != "User Applications" and record.category == "User Applications":
                group.category = "User Applications"

        self._grouped_cache = grouped
        return grouped

    def categorized_groups(self) -> Tuple[Dict[str, AppGroup], Dict[str, AppGroup]]:
        grouped = self.get_all()
        user_apps: Dict[str, AppGroup] = {}
        system_components: Dict[str, AppGroup] = {}
        for group_key, group in grouped.items():
            if group.category == "User Applications":
                user_apps[group_key] = group
            else:
                system_components[group_key] = group
        return user_apps, system_components
