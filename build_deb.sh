#!/bin/bash
# Build seilio-billing_<version>_<arch>.deb from the current source tree.
#
# Assumes ./.venv (created with `python3 -m venv --system-site-packages .venv`
# and `pip install factur-x reportlab`) holds the pure-Python runtime deps
# that aren't available as Debian packages; PyQt6/SQLAlchemy/lxml are taken
# from apt (python3-pyqt6, python3-sqlalchemy, python3-lxml) via Depends,
# not vendored.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
ARCH="$(dpkg --print-architecture)"
PKG_NAME="seilio-billing"
STAGE="$ROOT/packaging/build/${PKG_NAME}"
VENV_SITE_PACKAGES="$ROOT/.venv/lib/python3.$(python3 -c 'import sys;print(sys.version_info.minor)')/site-packages"

echo "==> Building ${PKG_NAME} ${VERSION} (${ARCH})"

rm -rf "$STAGE"
mkdir -p \
    "$STAGE/DEBIAN" \
    "$STAGE/usr/bin" \
    "$STAGE/usr/lib/seilio-billing/vendor" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/seilio-billing/icons" \
    "$STAGE/usr/share/icons/hicolor/128x128/apps" \
    "$STAGE/usr/share/doc/${PKG_NAME}"

echo "==> Copying application source"
cp -r seilio_billing "$STAGE/usr/lib/seilio-billing/"
find "$STAGE/usr/lib/seilio-billing" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "==> Copying icons"
cp resources/icons/*.png "$STAGE/usr/share/seilio-billing/icons/"
cp resources/icons/app.png "$STAGE/usr/share/icons/hicolor/128x128/apps/seilio-billing.png"

echo "==> Vendoring pure-Python runtime deps not packaged in Debian"
if [ ! -d "$VENV_SITE_PACKAGES" ]; then
    echo "Missing $VENV_SITE_PACKAGES — run: python3 -m venv --system-site-packages .venv && ./.venv/bin/pip install factur-x reportlab" >&2
    exit 1
fi
for pkg in facturx pypdf stdnum reportlab; do
    if [ -d "$VENV_SITE_PACKAGES/$pkg" ]; then
        cp -r "$VENV_SITE_PACKAGES/$pkg" "$STAGE/usr/lib/seilio-billing/vendor/"
    fi
done
# importlib.metadata lookups (e.g. facturx reading its own version) need the
# *.dist-info directories alongside the packages, not just the package code.
for dist_info in "$VENV_SITE_PACKAGES"/*.dist-info; do
    name="$(basename "$dist_info")"
    case "$name" in
        factur_x-*|pypdf-*|python_stdnum-*|reportlab-*)
            cp -r "$dist_info" "$STAGE/usr/lib/seilio-billing/vendor/"
            ;;
    esac
done

echo "==> Installing launcher and desktop entry"
install -m 0755 packaging/seilio-billing.wrapper "$STAGE/usr/bin/seilio-billing"
install -m 0644 packaging/seilio-billing.desktop "$STAGE/usr/share/applications/seilio-billing.desktop"

INSTALLED_SIZE="$(du -sk "$STAGE/usr" | cut -f1)"

echo "==> Writing control file"
sed -e "s/@VERSION@/${VERSION}/" \
    -e "s/@ARCH@/${ARCH}/" \
    -e "s/@INSTALLED_SIZE@/${INSTALLED_SIZE}/" \
    packaging/control.template > "$STAGE/DEBIAN/control"

DEB_FILE="$ROOT/${PKG_NAME}_${VERSION}_${ARCH}.deb"
echo "==> Building ${DEB_FILE}"
dpkg-deb --root-owner-group --build "$STAGE" "$DEB_FILE"

echo "==> Done: ${DEB_FILE}"
echo "    Install with: sudo apt install ${DEB_FILE}"
