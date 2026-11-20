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

echo
echo "#### Part 2: the same package arrives as an update"

if command -v cargo >/dev/null 2>&1; then
    rm -f "$here/build_time_payload_ran.txt" "$here/exfiltrated.txt"
    mkdir -p "$work/rust"
    cp -R "$here/rust/app" "$work/rust/app"
    rm -rf "$work/rust/app/target" "$work/rust/app/Cargo.lock"
    cp -R "$here/rust/arrayref_clean" "$work/rust/arrayref"
    (cd "$work/rust/app" && cargo build -q --offline) || exit 1
    echo "== Rust: built against arrayref 0.3.9 (honest)"
    rm -rf "$work/rust/arrayref"
    cp -R "$here/rust/arrayref" "$work/rust/arrayref"
    echo "== Rust: arrayref 0.3.10 arrives; cargo build"
    (cd "$work/rust/app" && cargo build --offline 2>&1 | grep -v '^ *Finished' | sed 's/^/   /')
    "$work/rust/app/target/debug/app" >/dev/null
    [ -f "$here/build_time_payload_ran.txt" ] && echo "   no question asked; build.rs ran"
    [ -f "$here/exfiltrated.txt" ] && echo "   no question asked; the key was shipped out"
fi

mkdir -p "$work/ks"
cp -R "$here/koschei/update/app" "$work/ks/app"
cp -R "$here/koschei/update/arrayref-0.3.9" "$work/ks/arrayref"
echo "== Koschei: ks pkg sync with arrayref 0.3.9"
(cd "$work/ks/app" && ks pkg sync | sed 's/^/   /')
rm -rf "$work/ks/arrayref"
cp -R "$here/koschei/update/arrayref-0.3.10" "$work/ks/arrayref"
echo "== Koschei: arrayref 0.3.10 arrives; ks pkg sync"
(cd "$work/ks/app" && ks pkg sync 2>&1 | sed 's/^/   /')
echo "== Koschei: the app still builds against the locked 0.3.9"
(cd "$work/ks/app" && ks run src/main.ks | sed 's/^/   /')
