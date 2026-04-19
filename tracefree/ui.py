from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional, Sequence, Tuple

from .cleanup import build_cleanup_commands, delete_unprivileged_paths, run_pkexec_script
from .engine import MultiSourceEngine
from .models import AppGroup, AppRecord, GhostMatch
from .scanner import scan_ghost_files
from .utils import format_size


class TraceFreeGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TraceFree")
        self.root.geometry("980x620")

        self.engine = MultiSourceEngine()
        self.user_groups: Dict[str, AppGroup] = {}
        self.system_groups: Dict[str, AppGroup] = {}
        self.ghost_cache: Dict[str, Tuple[List[GhostMatch], int]] = {}
        self.tree_item_payload: Dict[str, Dict[str, object]] = {}

        self.simulation_mode = tk.BooleanVar(value=True)
        self.show_technical_details = tk.BooleanVar(value=False)
        self.search_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self.load_apps()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill=tk.BOTH, expand=True)

        search_row = ttk.Frame(top)
        search_row.pack(fill=tk.X)
        ttk.Label(search_row, text="Search:").pack(side=tk.LEFT, padx=(0, 8))
        search_entry = ttk.Entry(search_row, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_var.trace_add("write", lambda *_: self.apply_search_filter())

        controls = ttk.Frame(top)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Refresh", command=self.load_apps).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="Scan Ghost Files", command=self.scan_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(controls, text="Deep Purge", command=self.deep_purge_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Checkbutton(controls, text="Simulation Mode", variable=self.simulation_mode).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(
            controls,
            text="Show Technical Details",
            variable=self.show_technical_details,
            command=self.apply_search_filter,
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.notebook = ttk.Notebook(top)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(10, 10))

        self.user_tab = ttk.Frame(self.notebook)
        self.system_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.user_tab, text="User Applications")
        self.notebook.add(self.system_tab, text="System Components")

        self.user_tree = self._create_tree(self.user_tab)
        self.system_tree = self._create_tree(self.system_tab)

        ghost_frame = ttk.LabelFrame(self.root, text="Ghost Scan Results", padding=10)
        ghost_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.ghost_text = tk.Text(ghost_frame, height=10, wrap=tk.NONE)
        self.ghost_text.pack(fill=tk.BOTH, expand=True)

        status = ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W)
        status.pack(fill=tk.X, padx=12, pady=(0, 12))

    def _create_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        columns = ("icon", "name", "source", "size")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        tree.heading("icon", text="Icon")
        tree.heading("name", text="App Name")
        tree.heading("source", text="Source")
        tree.heading("size", text="Disk Space")

        tree.column("icon", width=90, anchor=tk.CENTER)
        tree.column("name", width=460)
        tree.column("source", width=120, anchor=tk.CENTER)
        tree.column("size", width=140, anchor=tk.E)

        yscroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=yscroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.LEFT, fill=tk.Y)
        return tree

    def load_apps(self) -> None:
        self.status_var.set("Loading installed applications...")
        self.root.update_idletasks()

        self.user_groups, self.system_groups = self.engine.categorized_groups()
        self.ghost_cache.clear()
        self.apply_search_filter()
        self.ghost_text.delete("1.0", tk.END)

    def update_treeview(self, tree: ttk.Treeview, grouped_data: Dict[str, AppGroup], prefix: str) -> None:
        for item in tree.get_children():
            tree.delete(item)

        show_details = self.show_technical_details.get()
        idx = 0
        for group_key in sorted(grouped_data.keys(), key=lambda x: grouped_data[x].pretty_name.lower()):
            group = grouped_data[group_key]
            app_name = group.pretty_name
            source = group.source
            size_bytes = group.get_total_size()
            records = list(group.packages)
            packages = group.package_names()

            if not show_details:
                iid = f"{prefix}-{idx}"
                idx += 1
                tree.insert("", tk.END, iid=iid, values=("APP", app_name, source, format_size(size_bytes)))
                self.tree_item_payload[iid] = {
                    "display_name": app_name,
                    "source": source,
                    "records": records,
                    "packages": packages,
                    "category": group.category,
                }
                continue

            for rec in records:
                if not isinstance(rec, AppRecord):
                    continue
                pkg_name = rec.app_id or rec.name
                iid = f"{prefix}-{idx}"
                idx += 1
                tree.insert(
                    "",
                    tk.END,
                    iid=iid,
                    values=(rec.icon, f"{app_name} - {pkg_name}", rec.source, format_size(rec.disk_space_bytes)),
                )
                self.tree_item_payload[iid] = {
                    "display_name": app_name,
                    "source": rec.source,
                    "records": [rec],
                    "packages": [pkg_name],
                    "category": group.category,
                }

    def apply_search_filter(self) -> None:
        query = self.search_var.get().strip().lower()

        def filtered(groups: Dict[str, AppGroup]) -> Dict[str, AppGroup]:
            if not query:
                return dict(groups)

            result: Dict[str, AppGroup] = {}
            for group_key, group in groups.items():
                app_name = group.pretty_name
                source = group.source.lower()
                package_names = [name.lower() for name in group.package_names()]
                if query in app_name.lower() or query in source or any(query in pkg for pkg in package_names):
                    result[group_key] = group
            return result

        self.tree_item_payload.clear()
        self.update_treeview(self.user_tree, filtered(self.user_groups), "user")
        self.update_treeview(self.system_tree, filtered(self.system_groups), "system")

        mode = "detailed" if self.show_technical_details.get() else "grouped"
        self.status_var.set(
            f"Loaded {len(self.user_groups)} user applications and {len(self.system_groups)} system components ({mode})"
        )

    def _selected_payload(self) -> Tuple[Optional[Dict[str, object]], bool]:
        active_tab = self.notebook.select()
        in_system_tab = active_tab == str(self.system_tab)
        tree = self.system_tree if in_system_tab else self.user_tree
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an application first.")
            return None, in_system_tab
        return self.tree_item_payload.get(selected[0]), in_system_tab

    def _scan_payload_ghosts(self, payload: Dict[str, object]) -> Tuple[List[GhostMatch], int]:
        dedup: Dict[str, GhostMatch] = {}
        for member in payload.get("records", []):
            if not isinstance(member, AppRecord):
                continue
            target = member.app_id or member.name
            matches, _ = scan_ghost_files(target)
            for match in matches:
                current = dedup.get(match.path)
                if current is None or match.size_bytes > current.size_bytes:
                    dedup[match.path] = match

        final = sorted(dedup.values(), key=lambda x: x.path)
        total = sum(m.size_bytes for m in final)
        return final, total

    def scan_selected(self) -> None:
        payload, _ = self._selected_payload()
        if payload is None:
            return

        display_name = str(payload.get("display_name", "Unknown"))
        source = str(payload.get("source", "Unknown"))
        cache_key = f"{source}:{display_name}"

        self.status_var.set(f"Scanning for ghost files: {display_name}...")
        self.root.update_idletasks()

        def worker() -> None:
            matches, total = self._scan_payload_ghosts(payload)
            self.ghost_cache[cache_key] = (matches, total)
            self.root.after(0, lambda: self._show_scan_result(payload, matches, total))

        threading.Thread(target=worker, daemon=True).start()

    def _show_scan_result(self, payload: Dict[str, object], matches: Sequence[GhostMatch], total: int) -> None:
        self.ghost_text.delete("1.0", tk.END)
        display_name = str(payload.get("display_name", "Unknown"))
        source = str(payload.get("source", "Unknown"))
        category = str(payload.get("category", "Unknown"))

        self.ghost_text.insert(
            tk.END,
            (
                f"Ghost scan for: {display_name} ({source}, {category})\n"
                f"Matches: {len(matches)}\n"
                f"Estimated reclaimable size: {format_size(total)}\n\n"
            ),
        )

        if not matches:
            self.ghost_text.insert(tk.END, "No residual files found in configured scan roots.\n")
        else:
            for match in matches:
                flag = " [root]" if match.requires_root else ""
                self.ghost_text.insert(tk.END, f"- {match.path} ({format_size(match.size_bytes)}){flag}\n")

        self.status_var.set(f"Ghost scan done for {display_name}: {format_size(total)} potential junk")

    def deep_purge_selected(self) -> None:
        payload, in_system_tab = self._selected_payload()
        if payload is None:
            return

        if in_system_tab:
            proceed = messagebox.askyesno(
                "System Component Warning",
                "This item is in System Components. Purging it may break essential system behavior. Continue?",
                icon=messagebox.WARNING,
            )
            if not proceed:
                self.status_var.set("System component purge cancelled")
                return

        display_name = str(payload.get("display_name", "Unknown"))
        source = str(payload.get("source", "Unknown"))
        cache_key = f"{source}:{display_name}"
        matches, total = self.ghost_cache.get(cache_key, ([], 0))
        if not matches:
            matches, total = self._scan_payload_ghosts(payload)
            self.ghost_cache[cache_key] = (matches, total)

        if self.simulation_mode.get():
            preview_lines = [
                "Simulation only. Nothing will be deleted.",
                f"Target app: {display_name} ({source})",
                f"Ghost candidates: {len(matches)}",
                f"Estimated reclaimable: {format_size(total)}",
                "",
                "Actions that would run:",
            ]
            for member in payload.get("records", []):
                if not isinstance(member, AppRecord):
                    continue
                preview_lines.extend(build_cleanup_commands(member.name, member.source, member.app_id, matches))
            self.ghost_text.delete("1.0", tk.END)
            self.ghost_text.insert(tk.END, "\n".join(preview_lines) + "\n")
            self.status_var.set("Simulation complete")
            return

        confirm = messagebox.askyesno(
            "Confirm Deep Purge",
            (
                f"Deep purge {display_name}?\n\n"
                "This will remove package data and matched residual files.\n"
                f"Estimated reclaimable size: {format_size(total)}"
            ),
        )
        if not confirm:
            return

        script_lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
        for member in payload.get("records", []):
            if not isinstance(member, AppRecord):
                continue
            script_lines.extend(build_cleanup_commands(member.name, member.source, member.app_id, matches))

        code, out, err = run_pkexec_script("\n".join(script_lines) + "\n")
        deleted = delete_unprivileged_paths(matches)

        report = [
            f"Deep purge target: {display_name} ({source})",
            f"Privileged command exit code: {code}",
            "",
            "Privileged stdout:",
            out.strip() or "(none)",
            "",
            "Privileged stderr:",
            err.strip() or "(none)",
            "",
            f"Deleted user-scope paths: {len(deleted)}",
        ]
        self.ghost_text.delete("1.0", tk.END)
        self.ghost_text.insert(tk.END, "\n".join(report) + "\n")

        if code == 0:
            self.status_var.set("Deep purge completed")
            self.load_apps()
        else:
            self.status_var.set("Deep purge finished with errors")
            messagebox.showerror(
                "Deep Purge Error",
                "Privileged operations failed or were cancelled. See details in Ghost Scan Results.",
            )
