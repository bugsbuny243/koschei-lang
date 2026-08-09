#!/usr/bin/env bash
#
# verify.sh — Koschei release gate.
#
# Answers four questions before a release:
#   1. Does every example still produce the output it produced last time?
#   2. Do representative programs match between interpreter and native binary?
#   3. Does every code block in the docs actually compile?
#   4. Does the malicious supply-chain package still fail to compile?
#
# No dependencies. Run from the repository root:
#
#   ./verify.sh                  full check, exits non-zero on failure
#   ./verify.sh --update-golden  record current example output as expected
#   ./verify.sh --soft-docs      report doc failures but do not fail the build
#
set -uo pipefail

cd "$(dirname "$0")"

KS="python3 -m koschei"
GOLDEN_DIR="tests/golden"
UPDATE_GOLDEN=0
SOFT_DOCS=0
FAILED=0
WARNED=0

for arg in "$@"; do
  case "$arg" in
    --update-golden) UPDATE_GOLDEN=1 ;;
    --soft-docs)     SOFT_DOCS=1 ;;
    -h|--help)       sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 64 ;;
  esac
done

if [ -t 1 ]; then
  G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; N=$'\033[0m'
else
  G=""; R=""; Y=""; D=""; N=""
fi

pass() { printf "  ${G}PASS${N}  %s\n" "$1"; }
fail() { printf "  ${R}FAIL${N}  %s\n" "$1"; FAILED=$((FAILED + 1)); }
warn() { printf "  ${Y}WARN${N}  %s\n" "$1"; WARNED=$((WARNED + 1)); }
skip() { printf "  ${D}skip${N}  %s\n" "$1"; }
head_() { printf "\n${D}==>${N} %s\n" "$1"; }

# ---------------------------------------------------------------- preflight

command -v python3 >/dev/null 2>&1 || { echo "python3 not found"; exit 1; }
$KS version >/dev/null 2>&1 || { echo "cannot run 'python3 -m koschei' from $(pwd)"; exit 1; }

printf "Koschei verify — %s\n" "$($KS version 2>/dev/null)"

# ------------------------------------------------------------- 1. test suite

head_ "Test suite"
if out=$(python3 -m unittest discover -s tests 2>&1); then
  pass "$(printf '%s' "$out" | grep -oE 'Ran [0-9]+ tests' | head -1) — $(printf '%s' "$out" | tail -1)"
else
  fail "unit tests failed"
  printf '%s\n' "$out" | tail -15 | sed 's/^/        /'
fi

# --------------------------------------------------------- 2. sealed MIR identity

head_ "Sealed MIR"
mir_json=$($KS mir examples/hello.ks 2>&1)
mir_status=$?
check_json=$($KS check --json examples/hello.ks 2>&1)
check_status=$?
if [ $mir_status -ne 0 ] || [ $check_status -ne 0 ]; then
  fail "MIR/check JSON generation failed"
else
  if python3 - "$mir_json" "$check_json" <<'PY_MIR'
import json, re, sys
mir = json.loads(sys.argv[1])
checked = json.loads(sys.argv[2])
fingerprint = mir.get("fingerprint", "")
assert mir.get("version") == 3
assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
assert checked.get("mir_version") == mir["version"]
assert checked.get("mir_fingerprint") == fingerprint
assert mir.get("root") == "hello"
functions = mir["modules"][0]["functions"]
assert functions and functions[0]["basic_blocks"] >= 1
assert functions[0]["instructions"] >= 1
assert functions[0]["ast_fallbacks"] == 0
assert all(block.get("terminator") for block in functions[0]["blocks"])
resources = functions[0]["resources"]
assert resources["basic_blocks"] == functions[0]["basic_blocks"]
assert resources["instructions"] == functions[0]["instructions"]
assert resources["ast_fallbacks"] == functions[0]["ast_fallbacks"]
assert resources["backward_edges"] >= 0
assert isinstance(resources["self_recursive"], bool)
PY_MIR
  then
    pass "check and backend input share one sealed MIR fingerprint"
  else
    fail "MIR identity is missing, malformed, or inconsistent"
  fi
fi

# ----------------------------------------------- 3. interpreter/native parity

head_ "Interpreter/native parity"
PARITY_CASES=(
  "examples/hello.ks"
  "examples/control_flow.ks"
  "examples/daily.ks"
  "examples/holders.ks"
  "examples/maps.ks"
  "examples/v08_types.ks"
  "examples/app.ks"
)
PARITY_TMP=$(mktemp -d)
PARITY_EVIDENCE="$PARITY_TMP/evidence.tsv"
: > "$PARITY_EVIDENCE"
parity_failures=0

for path in "${PARITY_CASES[@]}"; do
  interpreted=$($KS run "$path" 2>&1)
  interpreted_status=$?
  binary="$PARITY_TMP/$(basename "${path%.ks}")"
  build_output=$($KS build "$path" --output "$binary" 2>&1)
  build_status=$?
  if [ $interpreted_status -ne 0 ] || [ $build_status -ne 0 ]; then
    fail "$path — interpreter/native parity setup failed"
    parity_failures=$((parity_failures + 1))
    if [ $build_status -ne 0 ]; then
      printf '%s\n' "$build_output" | head -3 | sed 's/^/        /'
    fi
    continue
  fi
  native=$($binary 2>&1)
  native_status=$?
  if [ $native_status -ne 0 ] || [ "$interpreted" != "$native" ]; then
    fail "$path — interpreter/native output mismatch"
    parity_failures=$((parity_failures + 1))
    continue
  fi
  output_sha=$(printf '%s' "$interpreted" | python3 -c \
    'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())')
  printf '%s\t%s\n' "$path" "$output_sha" >> "$PARITY_EVIDENCE"
done

if [ $parity_failures -eq 0 ]; then
  parity_sha=$(python3 - "$PARITY_EVIDENCE" <<'PY_PARITY'
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY_PARITY
  )
  pass "interpreter/native parity: ${#PARITY_CASES[@]} cases — PARITY SHA256: $parity_sha"
fi
rm -rf "$PARITY_TMP"

# ----------------------------------------------- 4. examples vs golden output
#
# Each entry: <path>|<mode>
#   run   — must run successfully; stdout is compared against the golden file
#   check — must pass `ks check` (library module with no main)
#   deny  — must FAIL, and the failure must mention the given code

EXAMPLES=(
  "examples/app.ks|run"
  "examples/capability.ks|run"
  "examples/control_flow.ks|run"
  "examples/daily.ks|run"
  "examples/hello.ks|run"
  "examples/holders.ks|run"
  "examples/maps.ks|run"
  "examples/runtime_demo.ks|run"
  "examples/showcase.ks|run"
  "examples/v08_types.ks|run"
  "examples/risk.ks|check"
  "examples/supply_chain/main.ks|deny:KS2401"
)

head_ "Examples"
mkdir -p "$GOLDEN_DIR"

for entry in "${EXAMPLES[@]}"; do
  path="${entry%%|*}"
  mode="${entry##*|}"

  if [ ! -f "$path" ]; then
    fail "$path — file is missing"
    continue
  fi

  case "$mode" in
    run)
      golden="$GOLDEN_DIR/$(printf '%s' "$path" | tr '/' '_').txt"
      actual=$($KS run "$path" 2>&1)
      status=$?
      if [ $status -ne 0 ]; then
        fail "$path — expected to run, exited $status"
        printf '%s\n' "$actual" | head -3 | sed 's/^/        /'
        continue
      fi
      if [ $UPDATE_GOLDEN -eq 1 ]; then
        printf '%s\n' "$actual" > "$golden"
        pass "$path — golden recorded"
      elif [ ! -f "$golden" ]; then
        warn "$path — no golden file yet (run with --update-golden)"
      elif [ "$actual" = "$(cat "$golden")" ]; then
        pass "$path"
      else
        fail "$path — output changed"
        diff <(cat "$golden") <(printf '%s\n' "$actual") | head -10 | sed 's/^/        /'
      fi
      ;;
    check)
      if $KS check "$path" >/dev/null 2>&1; then
        pass "$path (check only)"
      else
        fail "$path — check failed"
      fi
      ;;
    deny:*)
      want="${mode#deny:}"
      actual=$($KS check "$path" 2>&1)
      if printf '%s' "$actual" | grep -q "$want"; then
        pass "$path — correctly rejected with $want"
      else
        fail "$path — SECURITY: expected rejection with $want"
        printf '%s\n' "$actual" | head -3 | sed 's/^/        /'
      fi
      ;;
  esac
done

# ------------------------------------------------------ 5. documentation code
#
# Every ```ks block that contains a top-level declaration (fn / struct / enum /
# import) must compile. Blocks without one are treated as illustrative
# fragments and skipped. To skip a full block deliberately, put this line
# immediately before it in the markdown:
#
#   <!-- verify: skip -->
#
# To compile a runnable block without executing host/network effects:
#
#   <!-- verify: compile -->

head_ "Documentation code blocks"

DOC_TMP=$(mktemp -d)
trap 'rm -rf "$DOC_TMP"' EXIT

python3 - "$DOC_TMP" <<'PY'
import pathlib, sys

out = pathlib.Path(sys.argv[1])
roots = ["README.md", "README.tr.md"]
for directory in ("docs", "design"):
    root = pathlib.Path(directory)
    if root.is_dir():
        roots.extend(sorted(str(p) for p in root.glob("*.md")))

index = []
for name in roots:
    path = pathlib.Path(name)
    if not path.is_file():
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    inside = False
    skip_next = False
    compile_next = False
    expect_next = ""
    buffer, start = [], 0
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        low = stripped.lower()
        if not inside and low.startswith("<!-- verify: skip"):
            skip_next = True
            continue
        if not inside and low.startswith("<!-- verify: compile"):
            compile_next = True
            continue
        if not inside and low.startswith("<!-- verify: future"):
            expect_next = "FUTURE"
            continue
        if not inside and low.startswith("<!-- verify: expect"):
            parts = stripped.replace("-->", "").split()
            expect_next = parts[-1] if parts else ""
            continue
        if not inside and stripped.startswith("```ks"):
            inside, buffer, start = True, [], number
            continue
        if inside and stripped.startswith("```"):
            inside = False
            body = "\n".join(buffer)
            if skip_next:
                index.append(f"{name}\t{start}\tSKIPMARK\t")
                skip_next = False
                compile_next = False
                expect_next = ""
                continue
            if expect_next:
                target = out / f"{name.replace('/', '_')}__{start}.ks"
                target.write_text(body + "\n", encoding="utf-8")
                index.append(f"{name}\t{start}\tEXPECT:{expect_next}\t{target}")
                expect_next = ""
                compile_next = False
                continue
            if compile_next:
                target = out / f"{name.replace('/', '_')}__{start}.ks"
                target.write_text(body + "\n", encoding="utf-8")
                index.append(f"{name}\t{start}\tCOMPILE\t{target}")
                compile_next = False
                continue
            skip_next = False
            has_decl = any(
                b.startswith(("fn ", "struct ", "enum ", "import "))
                for b in (l.rstrip() for l in buffer)
            )
            if not has_decl:
                index.append(f"{name}\t{start}\tFRAGMENT\t")
                continue
            target = out / f"{name.replace('/', '_')}__{start}.ks"
            target.write_text(body + "\n", encoding="utf-8")
            runnable = any(
                l.rstrip().startswith("fn main(") for l in buffer
            )
            index.append(
                f"{name}\t{start}\t{'RUN' if runnable else 'COMPILE'}\t{target}"
            )
            continue
        if inside:
            buffer.append(line)
        elif stripped and not stripped.startswith("```"):
            skip_next = False
            compile_next = False

(out / "index.tsv").write_text("\n".join(index) + "\n", encoding="utf-8")
PY

doc_failures=0
while IFS=$'\t' read -r doc line kind target; do
  [ -z "${doc:-}" ] && continue
  case "$kind" in
    FRAGMENT)  skip "$doc:$line — fragment" ;;
    SKIPMARK)  skip "$doc:$line — marked verify: skip" ;;
    EXPECT:FUTURE)
      landed=0
      if $KS check "$target" >/dev/null 2>&1; then
        if grep -q '^fn main(' "$target"; then
          $KS run "$target" >/dev/null 2>&1 && landed=1
        else
          landed=1
        fi
      fi
      if [ $landed -eq 1 ]; then
        printf "  ${G}NEW!${N}  %s — this v5 feature now compiles. Update the guide.\n" "$doc:$line"
        WARNED=$((WARNED + 1))
      else
        skip "$doc:$line — v5 design, not implemented yet"
      fi
      ;;
    EXPECT:*)
      want="${kind#EXPECT:}"
      out=$($KS check "$target" 2>&1)
      if printf '%s' "$out" | grep -q "$want"; then
        pass "$doc:$line — correctly rejected with $want"
      else
        fail "$doc:$line — expected rejection with $want, did not get it"
        doc_failures=$((doc_failures + 1))
      fi
      ;;
    RUN)
      if out=$($KS check "$target" 2>&1); then
        if out=$($KS run "$target" 2>&1); then
          pass "$doc:$line (compiles and runs)"
        else
          code=$(printf '%s' "$out" | grep -oE 'KS[0-9]{4}' | head -1)
          if [ $SOFT_DOCS -eq 1 ]; then
            warn "$doc:$line — check passes but RUN fails ${code:+($code)}"
          else
            fail "$doc:$line — check passes but RUN fails ${code:+($code)}"
          fi
          doc_failures=$((doc_failures + 1))
          printf '%s\n' "$out" | head -2 | sed 's/^/        /'
        fi
      else
        code=$(printf '%s' "$out" | grep -oE 'KS[0-9]{4}' | head -1)
        if [ $SOFT_DOCS -eq 1 ]; then
          warn "$doc:$line — does not compile ${code:+($code)}"
        else
          fail "$doc:$line — does not compile ${code:+($code)}"
        fi
        doc_failures=$((doc_failures + 1))
        printf '%s\n' "$out" | head -2 | sed 's/^/        /'
      fi
      ;;
    COMPILE)
      if out=$($KS check "$target" 2>&1); then
        pass "$doc:$line ${D}(check only — add 'fn main' to verify at runtime)${N}"
      else
        code=$(printf '%s' "$out" | grep -oE 'KS[0-9]{4}' | head -1)
        if [ $SOFT_DOCS -eq 1 ]; then
          warn "$doc:$line — does not compile ${code:+($code)}"
        else
          fail "$doc:$line — does not compile ${code:+($code)}"
        fi
        doc_failures=$((doc_failures + 1))
        printf '%s\n' "$out" | head -2 | sed 's/^/        /'
      fi
      ;;
  esac
done < "$DOC_TMP/index.tsv"

if [ $doc_failures -gt 0 ]; then
  printf "\n  ${D}A documented example that does not compile is a promise the\n"
  printf "  project is not keeping. Fix the code, fix the doc, or mark the\n"
  printf "  block with <!-- verify: skip --> and say why, or use\n"
  printf "  <!-- verify: compile --> for host/network-dependent runtime code.${N}\n"
fi

# ------------------------------------------------------------------- summary

head_ "Summary"
if [ $FAILED -eq 0 ] && [ $WARNED -eq 0 ]; then
  printf "  ${G}Everything the repository claims is true.${N}\n\n"
  exit 0
elif [ $FAILED -eq 0 ]; then
  printf "  ${Y}%d warning(s), no failures.${N}\n\n" "$WARNED"
  exit 0
else
  printf "  ${R}%d failure(s)${N}, %d warning(s).\n\n" "$FAILED" "$WARNED"
  exit 1
fi