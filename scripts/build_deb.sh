#!/usr/bin/env bash
set -euo pipefail

APP_NAME="tracefree"
VERSION="${1:-1.0.0}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT_DIR/dist"
ARCH="$(dpkg --print-architecture)"
PKG_ROOT="$DIST_DIR/${APP_NAME}_${VERSION}_${ARCH}"
DEBIAN_DIR="$PKG_ROOT/DEBIAN"

rm -rf "$PKG_ROOT"
mkdir -p \
  "$DEBIAN_DIR" \
  "$PKG_ROOT/usr/bin" \
  "$PKG_ROOT/usr/lib/tracefree" \
  "$PKG_ROOT/usr/share/applications" \
  "$PKG_ROOT/usr/share/doc/tracefree"

cp -r "$ROOT_DIR/tracefree" "$PKG_ROOT/usr/lib/tracefree/"
cp "$ROOT_DIR/tracefree.py" "$PKG_ROOT/usr/lib/tracefree/"
cp "$ROOT_DIR/README.md" "$PKG_ROOT/usr/share/doc/tracefree/README.md"

cat > "$PKG_ROOT/usr/bin/tracefree" <<'EOF'
#!/usr/bin/env bash
exec python3 /usr/lib/tracefree/tracefree.py "$@"
EOF
chmod 755 "$PKG_ROOT/usr/bin/tracefree"

cat > "$PKG_ROOT/usr/share/applications/tracefree.desktop" <<'EOF'
[Desktop Entry]
Name=TraceFree
Comment=Deep cleaner for residual app data
Exec=tracefree
Icon=utilities-terminal
Terminal=false
Type=Application
Categories=System;Utility;
EOF
chmod 644 "$PKG_ROOT/usr/share/applications/tracefree.desktop"

cat > "$DEBIAN_DIR/control" <<EOF
Package: tracefree
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: TraceFree Maintainers <maintainers@example.com>
Depends: python3 (>= 3.8), python3-tk, python3-apt, policykit-1, snapd, flatpak
Description: TraceFree system cleanup utility
 TraceFree scans Apt, Snap, and Flatpak app residues,
 groups user-facing apps, and supports simulation-first deep purge.
EOF

chmod 755 "$DEBIAN_DIR"
chmod 644 "$DEBIAN_DIR/control"

mkdir -p "$DIST_DIR"
OUTPUT_DEB="$DIST_DIR/${APP_NAME}_${VERSION}_${ARCH}.deb"
dpkg-deb --build "$PKG_ROOT" "$OUTPUT_DEB"

echo "Built package: $OUTPUT_DEB"
