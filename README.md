# TraceFree (Ubuntu 20.04)

Native Python utility for identifying and purging leftover files across Apt, Snap, and Flatpak application ecosystems.

## Features

- Multi-source installed app inventory:
  - Apt via `python3-apt`
  - Snap via `snap list --json`
  - Flatpak via `flatpak list --columns=application,name,origin`
- Ghost file scan roots:
  - `~/.config/`
  - `~/.local/share/`
  - `~/.cache/`
  - `/var/lib/flatpak/app/`
- GUI table columns:
  - Icon
  - App Name
  - Source
  - Disk Space
- Simulation mode previews all removal actions before deletion.
- Privileged package operations are executed through `pkexec`.

## Requirements (Ubuntu 20.04)

Install required packages:

```bash
sudo apt update
sudo apt install -y python3-apt python3-tk policykit-1 snapd flatpak
```

## Run

```bash
python3 tracefree.py
```

Alternative module launch:

```bash
python3 -m tracefree
```

## Project Layout

- `tracefree/engine.py`: package aggregation and grouping
- `tracefree/scanner.py`: ghost-file discovery
- `tracefree/cleanup.py`: purge command construction and privileged execution
- `tracefree/ui.py`: Tkinter interface
- `tracefree/app.py`: app bootstrap
- `tracefree.py`: main launcher
- `deep_cleaner.py`: backward-compatible launcher

## Build Installable .deb

Build package:

```bash
./scripts/build_deb.sh 1.0.0
```

Output:

- `dist/tracefree_1.0.0_amd64.deb` (architecture suffix depends on your system)

Install package:

```bash
sudo apt install ./dist/tracefree_1.0.0_amd64.deb
```

Launch after install:

```bash
tracefree
```

## Notes on Privileged Operations

`Deep Purge` uses:

- `pkexec apt-get purge -y <pkg>` and `apt-get autoremove -y` for Apt
- `pkexec snap remove <pkg>` for Snap
- `pkexec flatpak uninstall -y --delete-data <app-id>` for Flatpak

Root-owned residual paths (such as `/var/lib/flatpak/app/...`) are removed via `pkexec` inside a temporary cleanup script.
User-owned residual paths are removed directly without elevation.

## Safety Model

- Simulation mode is enabled by default.
- Actual deletion only occurs after explicit confirmation.
- Symlinks are not followed when scanning/deleting directories.
