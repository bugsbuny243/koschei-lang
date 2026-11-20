#!/bin/sh
# The same compromised dependency, in Rust and in Koschei. Harmless: the
# "key" is a fake file in fixture/, and "exfiltration" writes a local file.
set -u
here=$(cd "$(dirname "$0")" && pwd)
export SUPPLY_CHAIN_DEMO_DIR="$here"
rm -f "$here/build_time_payload_ran.txt" "$here/exfiltrated.txt"

echo "== Rust: cargo build"
if command -v cargo >/dev/null 2>&1; then
    (cd "$here/rust/app" && cargo clean -q && cargo build -q --offline) || exit 1
    [ -f "$here/build_time_payload_ran.txt" ] && echo "   build.rs ran during the build (the August 2026 attack started here)"
    echo "== Rust: run the app"
    "$here/rust/app/target/debug/app"
    [ -f "$here/exfiltrated.txt" ] && echo "   the helper read fixture/id_ed25519 and shipped it out"
else
    echo "   cargo not installed; skipping"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$here/koschei/main.ks" "$work/main.ks"
for variant in arrayref arrayref_asks arrayref_clean; do
    cp "$here/koschei/$variant.ks" "$work/arrayref.ks"
    echo "== Koschei: $variant.ks"
    if ks check "$work/main.ks" >"$work/out" 2>&1; then
        ks caps "$work/main.ks" | sed -n '3,4p'
    else
        sed 's/^/   /' "$work/out" | head -1
    fi
done
