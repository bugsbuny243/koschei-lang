#!/bin/sh
# Install Koschei into its own virtual environment and put `ks` on PATH.
#
#   ./install.sh                 # installs into ~/.koschei, links ~/.local/bin/ks
#   KOSCHEI_HOME=/opt/koschei ./install.sh
#
# Needs Python 3.12+. Go 1.24+ is optional and only needed for `ks build`.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
home=${KOSCHEI_HOME:-"$HOME/.koschei"}
bin=${KOSCHEI_BIN:-"$HOME/.local/bin"}
python=${PYTHON:-python3}

if ! "$python" -c 'import sys; raise SystemExit(sys.version_info < (3, 12))'; then
    echo "koschei: Python 3.12 or newer is required ($python is $("$python" -V 2>&1))" >&2
    exit 1
fi

"$python" -m venv "$home"
"$home/bin/python" -m pip install --quiet "$here"
mkdir -p "$bin"
ln -sf "$home/bin/ks" "$bin/ks"
ln -sf "$home/bin/ks-mcp" "$bin/ks-mcp"

echo "koschei: installed into $home"
echo "koschei: 'ks' is linked at $bin/ks"
case ":$PATH:" in
    *":$bin:"*) ;;
    *) echo "koschei: add $bin to PATH to use 'ks' directly" ;;
esac
if ! command -v go >/dev/null 2>&1; then
    echo "koschei: Go was not found; 'ks run' works, 'ks build' needs Go 1.24+"
fi
