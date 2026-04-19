from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class AppRecord:
    icon: str
    name: str
    source: str
    disk_space_bytes: int
    app_id: Optional[str] = None
    category: str = ""


@dataclass
class GhostMatch:
    path: str
    size_bytes: int
    requires_root: bool


class AppGroup:
    def __init__(self, key: str, pretty_name: str, source: str, category: str) -> None:
        self.key = key
        self.pretty_name = pretty_name
        self.source = source
        self.category = category
        self.packages: List[AppRecord] = []

    def add_package(self, record: AppRecord) -> None:
        for existing in self.packages:
            if (existing.app_id or existing.name) == (record.app_id or record.name) and existing.source == record.source:
                return
        self.packages.append(record)

    def get_total_size(self) -> int:
        return sum(max(0, pkg.disk_space_bytes) for pkg in self.packages)

    def package_names(self) -> List[str]:
        names: List[str] = []
        seen: Set[str] = set()
        for pkg in self.packages:
            pkg_name = pkg.app_id or pkg.name
            if pkg_name in seen:
                continue
            seen.add(pkg_name)
            names.append(pkg_name)
        return names
